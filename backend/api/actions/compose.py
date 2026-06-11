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

from api.settings import get_settings


from api.utils.compose import find_yml_files, validate_compose_project_name, validate_app_name

logger = logging.getLogger(__name__)


"""
Helper for running blocking I/O in thread pool
"""
async def run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

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
    cmd = ["docker", "compose"] + command_args
    logger.info(f"Executing: {' '.join(cmd)} in {cwd}")

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=env_vars,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip() if result.stdout else (result.stderr.strip() if result.stderr else "No Output")
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr}")
        raise HTTPException(400, e.stderr.strip() if e.stderr else str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(500, str(e))

# Whitelist of docker-compose subcommands we ever pass through. The router
# already validates the same set, but enforcing it again here gives us
# defense in depth for any future internal caller and makes it explicit
# that arbitrary strings must never reach subprocess.run as the first arg
# (even though we use the array form, a typo could turn into a no-op or a
# silently-different docker-compose subcommand).
_ALLOWED_PROJECT_ACTIONS = frozenset({
    "up", "down", "start", "stop", "restart", "create", "delete", "pull",
})
_ALLOWED_APP_ACTIONS = frozenset({
    "up", "down", "start", "stop", "restart", "create", "rm", "pull",
})


def _compose_action_sync(name, action):
    validate_compose_project_name(name)
    if action not in _ALLOWED_PROJECT_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid compose action: {action!r}")
    files = find_yml_files(settings.COMPOSE_DIR)
    # We call the sync version of get_compose here
    compose = _get_compose_sync(name)
    env = os.environ.copy()

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
    else:
        output = _run_compose_command([action], _cwd, full_env)

    print(f"""Project {compose['name']} {action} successful.""")
    print(f"""Output: """)
    print(output)
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
            from api.utils.docker_client import get_sync_docker_client
            client = get_sync_docker_client()
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
    files = find_yml_files(settings.COMPOSE_DIR)
    compose = _get_compose_sync(name)
    env = os.environ.copy()

    _cwd = os.path.dirname(compose["path"])
    _env_vars = check_dockerhost(env)
    full_env = env.copy()
    full_env.update(_env_vars)
    if full_env.get("clear_env") == "true":
         del full_env["clear_env"]


    print("RUNNING: " + compose["path"] + " docker-compose " + " " + action + " " + app)

    if action == "up":
        output = _run_compose_command(["up", "-d", app], _cwd, full_env)
    elif action == "create":
        output = _run_compose_command(["up", "--no-start", app], _cwd, full_env)
    elif action == "rm":
        output = _run_compose_command(["rm", "--force", "--stop", app], _cwd, full_env)
    else:
        output = _run_compose_command([action, app], _cwd, full_env)

    print(f"""Project {compose['name']} App {name} {action} successful.""")
    print(f"""Output: """)
    print(output)
    return _get_compose_projects_sync()

async def compose_app_action(name, action, app):
    return await run_in_thread(_compose_app_action_sync, name, action, app)

"""
Checks for compose projects in the COMPOSE_DIR and
returns most of the info inside them.
"""
def _get_compose_projects_sync():
    files = find_yml_files(settings.COMPOSE_DIR)

    projects = []
    for project, file in files.items():
        volumes = []
        networks = []
        services = {}
        try:
            with open(file, 'r') as compose:
                loaded_compose = yaml.load(compose, Loader=yaml.SafeLoader)
        except Exception:
            print("ERROR: " + file + " is invalid or empty!")
            continue

        if loaded_compose:
            if loaded_compose.get("volumes"):
                for volume in loaded_compose.get("volumes"):
                    volumes.append(volume)
            if loaded_compose.get("networks"):
                for network in loaded_compose.get("networks"):
                    networks.append(network)
            if loaded_compose.get("services"):
                for service in loaded_compose.get("services"):
                    services[service] = loaded_compose["services"][service]
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
            print("ERROR: " + file + " is invalid or empty!")
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
        files = find_yml_files(settings.COMPOSE_DIR + name)
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
                    loaded_compose = yaml.load(compose, Loader=yaml.SafeLoader)
                except yaml.scanner.ScannerError as exc:
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

"""
Creates a compose directory and writes content
"""
_COMPOSE_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB — well past any real compose


def _write_compose_sync(compose):
    validate_compose_project_name(compose.name)

    # Bound the payload BEFORE we touch the disk. The previous code wrote
    # `compose.content` straight to a YAML file with no length check, so
    # an authenticated `perm_restart` user could trivially fill the
    # compose volume by POSTing a multi-GB string.
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

    if not os.path.exists(settings.COMPOSE_DIR + compose.name):
        try:
            pathlib.Path(settings.COMPOSE_DIR + compose.name).mkdir(parents=True)
        except Exception as exc:
            raise HTTPException(500, str(exc))

    with open(settings.COMPOSE_DIR + compose.name + "/docker-compose.yml", "w") as f:
        try:
            f.write(content)
        except TypeError as exc:
            if "write() argument must be str" in str(exc):
                raise HTTPException(
                    status_code=422, detail="Compose file cannot be empty."
                )
            raise HTTPException(500, str(exc))
        except Exception as exc:
            raise HTTPException(500, str(exc))

    return _get_compose_sync(name=compose.name)

async def write_compose(compose):
    return await run_in_thread(_write_compose_sync, compose)

"""
Deletes a compose project
"""
def _delete_compose_sync(project_name):
    validate_compose_project_name(project_name)
    if not os.path.exists("/" + settings.COMPOSE_DIR + project_name):
        raise HTTPException(404, "Project directory not found.")
    elif not os.path.exists(
        "/" + settings.COMPOSE_DIR + project_name + "/docker-compose.yml"
    ):
        raise HTTPException(404, "Project docker-compose.yml not found.")
    else:
        pass

    try:
        shutil.rmtree("/" + settings.COMPOSE_DIR + project_name)
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return _get_compose_projects_sync()

async def delete_compose(project_name):
    return await run_in_thread(_delete_compose_sync, project_name)


def _generate_support_bundle_sync(project_name):
    validate_compose_project_name(project_name)
    files = find_yml_files(settings.COMPOSE_DIR + project_name)
    if project_name in files:
        from api.utils.docker_client import get_sync_docker_client
        dclient = get_sync_docker_client()
        stream = io.BytesIO()
        try:
            with zipfile.ZipFile(stream, "w") as zf, open(files[project_name], "r") as fp:
                # yaml.load returns None for an empty or whitespace-only file;
                # coerce to {} so the .get below doesn't blow up the bundle.
                compose = yaml.load(fp, Loader=yaml.SafeLoader) or {}

                services_list = compose.get("services", {})
                for _service in services_list:
                    service = None
                    try:
                        container_name = services_list[_service].get("container_name")
                        if container_name:
                            service = dclient.containers.get(container_name)
                        else:
                            # Fallback logic for default naming
                            if len(services_list.keys()) < 2:
                                service = dclient.containers.get(_service)
                            else:
                                service = dclient.containers.get(
                                    project_name.lower() + "_" + _service + "_1"
                                )
                    except docker.errors.NotFound:
                        # Log missing container but continue?
                        # The original code raised HTTPException immediately.
                        pass

                    if service:
                        service_log = service.logs()
                        zf.writestr(f"{_service}.log", service_log)

                fp.seek(0)
                zf.writestr("docker-compose.yml", fp.read())
        except Exception as exc:
             # Make sure we don't leak connection if zip fails
             raise exc
        finally:
            # Explicitly close the client we created
            dclient.close()

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
