from fastapi import APIRouter, Depends, status, Request, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse
from api.auth.jwt import get_auth_wrapper
from api.auth.auth import auth_check
import api.actions.containers as actions
import asyncio
import aiodocker

router = APIRouter()

@router.get("/{container_id}/logs")
async def get_container_logs(
    request: Request,
    container_id: str,
    tail: int = 100,
    follow: bool = True,
    timestamps: bool = False,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    Streams container logs using Docker API
    """
    auth_check(Authorize)
    return EventSourceResponse(
        actions.get_logs_generator(container_id, tail, follow, timestamps)
    )

@router.get("/{container_id}/stats")
async def get_container_stats(
    container_id: str,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    Returns current CPU/RAM usage
    """
    auth_check(Authorize)
    return await actions.get_stats(container_id)

from fastapi import Query
import jwt
from api.auth.jwt import get_secret_key

@router.websocket("/{container_id}/exec")
async def container_exec(
    websocket: WebSocket,
    container_id: str,
    token: str = Query(None),
    shell: str = Query("/bin/sh"),
    cols: int = Query(80),
    rows: int = Query(24)
):
    """
    WebSocket endpoint for container exec (terminal)
    """
    await websocket.accept()

    # Check Auth
    try:
        if not token:
             raise Exception("No token")
        jwt.decode(token, get_secret_key(), algorithms=["HS256"])
    except Exception as e:
        print(f"WebSocket Auth Error: {e}")
        await websocket.send_json({"error": "Unauthorized"})
        await websocket.close(code=1008)
        return

    docker = aiodocker.Docker()
    exec_id = None
    stream = None

    try:
        # Create exec instance
        # Ensure container exists
        try:
            container = await docker.containers.get(container_id)
        except Exception as e:
            await websocket.close(code=1008, reason="Container not found")
            return

        exec_create_resp = await docker.exec.create(
            container_id,
            Cmd=[shell],
            AttachStdin=True,
            AttachStdout=True,
            AttachStderr=True,
            Tty=True,
            Env=["TERM=xterm"]
        )

        exec_id = exec_create_resp["Id"]

        # Now start it. We need a stream.
        # The `start` method in aiodocker returns a `Stream` object if detach=False.
        stream = await docker.exec.start(exec_id, tty=True, detach=False)

        # We need to handle resizing.
        # aiodocker `exec.resize(exec_id, w, h)`
        await docker.exec.resize(exec_id, width=cols, height=rows)

        # Task to read from docker and send to websocket
        async def read_from_docker():
            try:
                # stream.read_out() yields data
                while True:
                    msg = await stream.read_out()
                    if msg is None:
                        break
                    # msg is bytes?
                    # xterm expects string or bytes.
                    if msg.data:
                         await websocket.send_bytes(msg.data)
            except Exception as e:
                pass

        # Task to read from websocket and write to docker
        async def write_to_docker():
            try:
                while True:
                    data = await websocket.receive()
                    # data can be bytes or text.

                    if "text" in data:
                        input_data = data["text"]

                        try:
                            cmd = None
                            if input_data.startswith("{"):
                                import json
                                cmd = json.loads(input_data)

                            if cmd and cmd.get("type") == "resize":
                                await docker.exec.resize(exec_id, width=cmd["cols"], height=cmd["rows"])
                                continue
                        except:
                            pass

                        # Send to docker
                        await stream.write_in(input_data.encode())

                    elif "bytes" in data:
                        await stream.write_in(data["bytes"])

                    if data.get("type") == "websocket.disconnect":
                        break

            except WebSocketDisconnect:
                pass
            except Exception as e:
                pass

        # Run tasks
        reader = asyncio.create_task(read_from_docker())
        writer = asyncio.create_task(write_to_docker())

        await asyncio.wait([reader, writer], return_when=asyncio.FIRST_COMPLETED)

        reader.cancel()
        writer.cancel()

    except Exception as e:
        await websocket.close(code=1011)
    finally:
        await docker.close()
