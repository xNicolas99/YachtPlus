from fastapi import HTTPException
from fastapi.responses import StreamingResponse
import subprocess

import os
import yaml
import pathlib
import shutil
import docker
import io
import zipfile
import asyncio
import functools
import logging
import tempfile
import difflib
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from api.utils.yaml_loader import load_yaml

from api.settings import get_settings
settings = get_settings()
from api.utils.compose import find_yml_files, validate_compose_project_name, validate_app_name

logger = logging.getLogger(__name__)
_compose_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="compose")

"""
Helper for running blocking I/O in thread pool
"""
async def run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_compose_executor, functools.partial(func, *args, **kwargs))

"""
Runs an action on the specified compose project.
"""

def _run_compose_command(command_args, cwd, env_vars):
    """
    Executes a docker-compose command using subprocess.
    """
    # Compose v2 ships as a Docker CLI plugin invoked via `docker compose`.
    # The standalone `docker-compose` v1 binary has been deprecated since
    # 2023 and is not installed on most modern hosts (Docker Desktop, the
    # docker.io / docker-ce packages on current Ubuntu/Debian, etc.). Using
    # the plugin form keeps us compatible with every supported runtime; on
    # the few v1-only legacy hosts the operator can symlink `docker-compose`
    # into a wrapper, but the inverse (assuming v1 exists) was guaranteed
    # to fail with ENOENT on a clean install.
    directory = pathlib.Path(cwd)
    filenames = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
    if any((directory / name).is_symlink() for name in filenames):
        raise HTTPException(400, "Compose file cannot be a symlink")
    selected = find_yml_files(str(directory)).get(directory.name)
    cmd = ["docker", "compose"] + (["-f", selected] if selected else []) + command_args
    logger.info(f"Executing: {' '.join(cmd)} in {cwd}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env_vars,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,  # cap long-running compose ops (pull, build)
        )
        return result.stdout.strip() if result.stdout else (result.stderr.strip() if result.stderr else "No Output")
    except subprocess.CalledProcessError as e:
        logger.error(
            "Command failed in %r (exit %s): stderr=%s",
            cwd,
            e.returncode,
            e.stderr,
        )
        # Don't echo stderr to the client: it may contain host paths,
        # internal hostnames, env values, or other sensitive details.
        raise HTTPException(
            status_code=400,
            detail="Compose command failed. Check server logs for details.",
        )
    except Exception as e:
        logger.exception("Unexpected error running compose command in %r", cwd)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while running the compose command.",
        )

# Whitelist of docker-compose subcommands we ever pass through. The router
# already validates the same set, but enforcing it again here gives us
# defense in depth for any future internal caller and makes it explicit
# that arbitrary strings must never reach subprocess.run as the first arg
# (even though we use the array form, a typo could turn into a no-op or a
# silently-different docker-compose subcommand).
_ALLOWED_PROJECT_ACTIONS = frozenset({
    "up", "down", "start", "stop", "restart", "create", "delete", "pull", "kill", "rm",
})
_ALLOWED_APP_ACTIONS = frozenset({
    "up", "down", "start", "stop", "restart", "create", "rm", "pull", "kill",
})


def _compose_action_sync(name, action):
    validate_compose_project_name(name)
    if action not in _ALLOWED_PROJECT_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid compose action: {action!r}")
    files = find_yml_files(get_settings().COMPOSE_DIR)
    # We call the sync version of get_compose here
    compose = _get_compose_sync(name)
    env = _compose_environment()

    # Check docker host
    _env_vars = check_dockerhost(env)
    # Merge env vars
    full_env = env.copy()
    full_env.update(_env_vars)
    if full_env.get("clear_env") == "true":
         del full_env["clear_env"]

    _cwd = os.path.dirname(compose["path"])

    if action == "up":
        output = _run_compose_command([action, "-d"], _cwd, full_env)
    elif action == "create":
        output = _run_compose_command(["up", "--no-start"], _cwd, full_env)
    elif action == "rm":
        output = _run_compose_command(["rm", "--force", "--stop"], _cwd, full_env)
    else:
        output = _run_compose_command([action], _cwd, full_env)

    logger.info("Project %s %s successful.", compose['name'], action)
    logger.debug("Compose output: %s", output)
    return _get_compose_projects_sync()

async def compose_action(name, action):
    return await run_in_thread(_compose_action_sync, name, action)

"""
Used to include the DOCKER_HOST in the shell env
"""
def check_dockerhost(environment):
    if environment.get("DOCKER_HOST"):
        return {"DOCKER_HOST": environment["DOCKER_HOST"]}

    if os.path.exists('/var/run/docker.sock'):
        try:
            from api.utils.docker_client import sync_docker_client
            with sync_docker_client() as client:
                client.ping()
            return {}
        except Exception:
            pass

    return {"clear_env": "true"}


"""
Used to run docker-compose commands on specific 
apps in compose projects.
"""
def _compose_app_action_sync(name, action, app):
    validate_compose_project_name(name)
    validate_app_name(app)
    if action not in _ALLOWED_APP_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid compose action: {action!r}")
    files = find_yml_files(get_settings().COMPOSE_DIR)
    compose = _get_compose_sync(name)
    env = _compose_environment()

    _cwd = os.path.dirname(compose["path"])
    _env_vars = check_dockerhost(env)
    full_env = env.copy()
    full_env.update(_env_vars)
    if full_env.get("clear_env") == "true":
         del full_env["clear_env"]


    logger.debug("RUNNING: %s docker-compose %s %s", compose["path"], action, app)

    if action == "up":
        output = _run_compose_command(["up", "-d", app], _cwd, full_env)
    elif action == "create":
        output = _run_compose_command(["up", "--no-start", app], _cwd, full_env)
    elif action == "rm":
        output = _run_compose_command(["rm", "--force", "--stop", app], _cwd, full_env)
    else:
        output = _run_compose_command([action, app], _cwd, full_env)

    logger.info("Project %s App %s %s successful.", compose['name'], name, action)
    logger.debug("Compose output: %s", output)
    return _get_compose_projects_sync()

async def compose_app_action(name, action, app):
    return await run_in_thread(_compose_app_action_sync, name, action, app)

"""
Checks for compose projects in the COMPOSE_DIR and
returns most of the info inside them.
"""
def _get_compose_projects_sync():
    files = find_yml_files(get_settings().COMPOSE_DIR)

    projects = []
    for project, file in files.items():
        volumes = []
        networks = []
        services = {}
        try:
            with open(file, 'r') as compose:
                loaded_compose = load_yaml(compose.read(_COMPOSE_MAX_BYTES + 1))
        except Exception:
            logger.warning("%s is invalid or empty!", file)
            continue

        if isinstance(loaded_compose, dict) and isinstance(loaded_compose.get("services"), dict):
            if any(loaded_compose.get(key) is not None and not isinstance(loaded_compose[key], dict) for key in ("volumes", "networks")):
                logger.warning("%s contains invalid volumes or networks", file)
                continue
            if loaded_compose.get("volumes"):
                for volume in loaded_compose.get("volumes"):
                    volumes.append(volume)
            if loaded_compose.get("networks"):
                for network in loaded_compose.get("networks"):
                    networks.append(network)
            if loaded_compose.get("services"):
                for service in loaded_compose.get("services"):
                    data = loaded_compose["services"][service]
                    if isinstance(data, dict):
                        services[service] = {key: value for key, value in data.items() if key in {"image", "container_name", "ports", "restart", "depends_on"}}
            _project = {
                "name": project,
                "path": file,
                "version": loaded_compose.get("version", "3.9"),
                "services": services,
                "volumes": volumes,
                "networks": networks,
            }
            projects.append(_project)
        else:
            logger.warning("%s is invalid or empty!", file)
    return projects

async def get_compose_projects():
    return await run_in_thread(_get_compose_projects_sync)

"""
Returns detailed information on a specific compose
project.
"""
def _get_compose_sync(name):
    validate_compose_project_name(name)
    try:
        files = find_yml_files(str(pathlib.Path(get_settings().COMPOSE_DIR) / name))
    except Exception as exc:
        # Re-raise exceptions properly
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(500, str(exc))

    for project, file in files.items():
        if name == project:
            networks = []
            volumes = []
            services = {}
            with open(file, 'r') as compose:
                try:
                    content = compose.read(_COMPOSE_MAX_BYTES + 1)
                    if len(content.encode()) > _COMPOSE_MAX_BYTES:
                        raise HTTPException(413, "Compose file is too large")
                    loaded_compose = load_yaml(content)
                    if not isinstance(loaded_compose, dict) or not isinstance(loaded_compose.get("services"), dict):
                        raise HTTPException(422, "Compose must contain a services mapping")
                except yaml.YAMLError as exc:
                    raise HTTPException(422, f"{exc.problem_mark.line}:{exc.problem_mark.column} - {exc.problem}")

            if loaded_compose:
                if loaded_compose.get("volumes"):
                    volumes.extend(loaded_compose["volumes"])
                if loaded_compose.get("networks"):
                    networks.extend(loaded_compose["networks"])
                if loaded_compose.get("services"):
                    services.update(loaded_compose["services"])

            with open(file, 'r') as _content:
                content = _content.read()

            compose_object = {
                "name": project,
                "path": file,
                "version": loaded_compose.get("version", "-") if loaded_compose else "-",
                "services": services,
                "volumes": volumes,
                "networks": networks,
                "content": content,
            }
            return compose_object
    else:
        raise HTTPException(404, "Project " + name + " not found")

async def get_compose(name):
    return await run_in_thread(_get_compose_sync, name)

# Shared normalization keeps read-only previews identical to atomic saves.
_COMPOSE_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB — well past any real compose


def _normalize_compose_content(compose):
    validate_compose_project_name(compose.name)

    # Bound the payload before parsing it or touching the destination.
    content = compose.content
    if content is None or content == "":
        raise HTTPException(status_code=422, detail="Compose file cannot be empty.")
    if not isinstance(content, str):
        raise HTTPException(status_code=422, detail="Compose content must be text.")
    if len(content.encode("utf-8", errors="ignore")) > _COMPOSE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Compose file exceeds {_COMPOSE_MAX_BYTES} bytes",
        )
    # Reject control bytes (NUL would corrupt the YAML parser; the rest
    # are common log-injection / parser-confusion characters).
    if "\x00" in content:
        raise HTTPException(status_code=422, detail="Compose file contains NUL bytes.")

    from api.utils.container_security import secure_compose_content
    content = secure_compose_content(content)
    if len(content.encode("utf-8")) > _COMPOSE_MAX_BYTES:
        raise HTTPException(413, "Normalized Compose file is too large")
    load_yaml(content)  # Check the final document before changing any file.
    return content


def _compose_write_target(name):
    """Resolve a permitted destination without creating a directory or file."""
    base_dir = pathlib.Path(get_settings().COMPOSE_DIR).resolve()
    project_dir = base_dir / name
    if project_dir.is_symlink():
        raise HTTPException(400, "Compose project directory cannot be a symlink")
    target_dir = project_dir.resolve()
    if not target_dir.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Invalid compose project name.")
    if target_dir.exists() and not target_dir.is_dir():
        raise HTTPException(422, "Compose project path must be a directory")
    if any((target_dir / name).is_symlink() for name in ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")):
        raise HTTPException(400, "Compose file cannot be a symlink")

    selected = find_yml_files(str(target_dir)).get(name)
    target_file = pathlib.Path(selected) if selected else target_dir / "docker-compose.yml"
    if target_file.is_symlink():
        raise HTTPException(400, "Compose file cannot be a symlink")
    return target_dir, target_file


def _compose_source(target_file):
    if not target_file.exists():
        return "", "missing"
    try:
        with target_file.open("rb") as stream:
            original = stream.read(_COMPOSE_MAX_BYTES + 1)
        if len(original) > _COMPOSE_MAX_BYTES:
            raise HTTPException(413, "Existing Compose file is too large")
        return original.decode("utf-8"), hashlib.sha256(original).hexdigest()
    except (OSError, UnicodeError):
        raise HTTPException(422, "Existing Compose file could not be read as UTF-8") from None


def _compose_preview_token(compose, normalized, source_digest):
    from api.auth.jwt import get_secret_key

    payload = json.dumps(
        [compose.name, compose.content, normalized, source_digest],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(get_secret_key().encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _preview_compose_sync(compose):
    normalized = _normalize_compose_content(compose)
    _, target_file = _compose_write_target(compose.name)
    original, source_digest = _compose_source(target_file)
    submitted_document = load_yaml(compose.content)
    normalized_document = load_yaml(normalized)
    warnings = []
    previous_document = {}
    previous_services = {}
    if original:
        try:
            previous_document = load_yaml(original)
            if isinstance(previous_document, dict) and isinstance(previous_document.get("services"), dict):
                previous_services = previous_document["services"]
            else:
                warnings.append("The existing file has no services mapping and will be replaced.")
        except HTTPException:
            warnings.append("The existing file is invalid YAML and will be replaced.")
            previous_document = {}

    submitted_services = submitted_document["services"]
    services = normalized_document["services"]
    shared_settings_changed = isinstance(previous_document, dict) and {
        key: value for key, value in previous_document.items() if key != "services"
    } != {key: value for key, value in normalized_document.items() if key != "services"}
    affected = []
    for name in sorted(previous_services.keys() | services.keys(), key=str):
        if name not in previous_services:
            affected.append({"name": str(name), "change": "added"})
        elif name not in services:
            affected.append({"name": str(name), "change": "removed"})
        elif previous_services[name] != services[name] or shared_settings_changed:
            affected.append({"name": str(name), "change": "changed"})

    security_fields = {"user", "read_only", "cap_drop", "tmpfs", "security_opt", "pids_limit", "x-yachtplus-security"}
    security_changes = []
    for name, service in services.items():
        changes = sorted(field for field in security_fields if submitted_services[name].get(field) != service.get(field))
        if changes:
            security_changes.append({"service": str(name), "fields": changes})
        if service.get("x-yachtplus-security") == "image-default":
            warnings.append(f"Service {name} uses explicitly selected image compatibility settings.")

    return {
        "name": compose.name,
        "normalized_content": normalized,
        "diff": "".join(
            line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
            for line in difflib.unified_diff(
                original.splitlines(keepends=True), normalized.splitlines(keepends=True),
                fromfile="Saved Compose", tofile="Compose after saving",
            )
        ),
        "affected_services": affected,
        "security_changes": security_changes,
        "warnings": warnings,
        "preview_token": _compose_preview_token(compose, normalized, source_digest),
    }


async def preview_compose(compose):
    return await run_in_thread(_preview_compose_sync, compose)


@contextmanager
def _compose_save_lock(name):
    """Serialize preview validation and replacement across API workers."""
    resource = str(pathlib.Path(get_settings().COMPOSE_DIR).resolve() / name)
    key = hashlib.sha256(resource.encode("utf-8")).hexdigest()
    path = pathlib.Path(tempfile.gettempdir()) / f"yachtplus-compose-save-{key}.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise HTTPException(409, "Another save is already in progress for this stack.") from None
        yield
    finally:
        os.close(descriptor)


def _write_compose_sync(compose):
    content = _normalize_compose_content(compose)
    with _compose_save_lock(compose.name):
        return _write_compose_locked(compose, content)


def _write_compose_locked(compose, content):
    target_dir, target_file = _compose_write_target(compose.name)
    preview_token = getattr(compose, "preview_token", None)
    if isinstance(preview_token, str):
        _, source_digest = _compose_source(target_file)
        expected = _compose_preview_token(compose, content, source_digest)
        if not hmac.compare_digest(preview_token, expected):
            raise HTTPException(409, "Compose content or saved file changed. Generate and confirm a new preview.")
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target_dir, delete=False) as stream:
            temporary = pathlib.Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target_file)
    except OSError:
        raise HTTPException(500, "Could not save Compose file") from None
    finally:
        if temporary and temporary.exists():
            temporary.unlink()

    return _get_compose_sync(name=compose.name)

async def write_compose(compose):
    return await run_in_thread(_write_compose_sync, compose)

"""
Deletes a compose project
"""
def _delete_compose_sync(project_name):
    validate_compose_project_name(project_name)

    base_dir = pathlib.Path(get_settings().COMPOSE_DIR).resolve()
    target_dir = (base_dir / project_name).resolve()
    if not target_dir.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Invalid compose project name.")

    compose_file = find_yml_files(str(target_dir)).get(project_name)
    if not target_dir.exists():
        raise HTTPException(404, "Project directory not found.")
    if not compose_file:
        raise HTTPException(404, "Project docker-compose.yml not found.")

    try:
        _run_compose_command(["down"], str(target_dir), _compose_environment())
        shutil.rmtree(target_dir)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return _get_compose_projects_sync()

async def delete_compose(project_name):
    return await run_in_thread(_delete_compose_sync, project_name)

def _compose_environment():
    # Compose interpolation must not inherit signing keys or server secrets.
    env = {key: os.environ[key] for key in ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "TEMP", "TMP", "LANG", "DOCKER_HOST", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH") if key in os.environ}
    if get_settings().DOCKER_HOST:
        env["DOCKER_HOST"] = get_settings().DOCKER_HOST
    return env


def _generate_support_bundle_sync(project_name):
    validate_compose_project_name(project_name)
    files = find_yml_files(str(pathlib.Path(get_settings().COMPOSE_DIR) / project_name))
    if project_name in files:
        from api.utils.docker_client import sync_docker_client
        stream = io.BytesIO()
        with sync_docker_client() as dclient, zipfile.ZipFile(stream, "w") as zf, open(files[project_name], "r") as fp:
            # yaml.load returns None for an empty or whitespace-only file;
            # coerce to {} so the .get below doesn't blow up the bundle.
            compose = load_yaml(fp.read(_COMPOSE_MAX_BYTES + 1))
            if not isinstance(compose, dict) or not isinstance(compose.get("services"), dict):
                raise HTTPException(422, "Compose must contain a services mapping")

            services_list = compose.get("services", {})
            for _service in services_list:
                service = None
                try:
                    container_name = services_list[_service].get("container_name")
                    if container_name:
                        service = dclient.containers.get(container_name)
                    else:
                        matches = dclient.containers.list(all=True, filters={"label": [
                            f"com.docker.compose.project={project_name.lower()}",
                            f"com.docker.compose.service={_service}",
                        ]})
                        service = matches[0] if matches else None
                except docker.errors.NotFound:
                    # Log missing container but continue?
                    # The original code raised HTTPException immediately.
                    pass

                if service:
                    service_log = service.logs(tail=10000)
                    zf.writestr(f"{_service}.log", service_log)

            fp.seek(0)
            zf.writestr("docker-compose.yml", fp.read())

        stream.seek(0)
        return stream
    else:
        raise HTTPException(404, f"Project {project_name} not found.")

async def generate_support_bundle(project_name):
    stream = await run_in_thread(_generate_support_bundle_sync, project_name)
    return StreamingResponse(
            stream,
            media_type="application/x-zip-compressed",
            headers={
                "Content-Disposition": f"attachment;filename={project_name}_bundle.zip"
            },
        )
