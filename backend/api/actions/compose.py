from fastapi import HTTPException
from fastapi.responses import StreamingResponse
try:
    from sh import docker_compose
except ImportError:
    docker_compose = None

import os
import yaml
import pathlib
import shutil
import docker
import io
import zipfile
import asyncio
import functools

from api.settings import Settings
from api.utils.compose import find_yml_files, validate_compose_project_name

settings = Settings()

"""
Helper for running blocking I/O in thread pool
"""
async def run_in_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

"""
Runs an action on the specified compose project.
"""

def _compose_action_sync(name, action):
    validate_compose_project_name(name)
    files = find_yml_files(settings.COMPOSE_DIR)
    # We call the sync version of get_compose here
    compose = _get_compose_sync(name)
    env = os.environ.copy()

    # Check docker host
    _env_vars = check_dockerhost(env)

    _cwd = os.path.dirname(compose["path"])

    if action == "up":
        try:
            _action = docker_compose(
                action,
                "-d",
                _cwd=_cwd,
                _env=_env_vars,
            )
        except Exception as exc:
            if hasattr(exc, "stderr"):
                raise HTTPException(400, exc.stderr.decode("UTF-8").rstrip())
            else:
                raise HTTPException(400, str(exc))
    elif action == "create":
        try:
            _action = docker_compose(
                "up",
                "--no-start",
                _cwd=_cwd,
                _env=_env_vars,
            )
        except Exception as exc:
            if hasattr(exc, "stderr"):
                raise HTTPException(400, exc.stderr.decode("UTF-8").rstrip())
            else:
                raise HTTPException(400, str(exc))
    else:
        try:
            _action = docker_compose(
                action,
                _cwd=_cwd,
                _env=_env_vars,
            )
        except Exception as exc:
            if hasattr(exc, "stderr"):
                raise HTTPException(400, exc.stderr.decode("UTF-8").rstrip())
            else:
                raise HTTPException(400, str(exc))

    if _action.stdout.decode("UTF-8").rstrip():
        _output = _action.stdout.decode("UTF-8").rstrip()
    elif _action.stderr.decode("UTF-8").rstrip():
        _output = _action.stderr.decode("UTF-8").rstrip()
    else:
        _output = "No Output"
    print(f"""Project {compose['name']} {action} successful.""")
    print(f"""Output: """)
    print(_output)
    return _get_compose_projects_sync()

async def compose_action(name, action):
    return await run_in_thread(_compose_action_sync, name, action)

"""
Used to include the DOCKER_HOST in the shell env
"""
def check_dockerhost(environment):
    if environment.get("DOCKER_HOST"):
        return {"DOCKER_HOST": environment["DOCKER_HOST"]}
    else:
        return {"clear_env": "true"}


"""
Used to run docker-compose commands on specific 
apps in compose projects.
"""
def _compose_app_action_sync(name, action, app):
    validate_compose_project_name(name)
    files = find_yml_files(settings.COMPOSE_DIR)
    compose = _get_compose_sync(name)
    env = os.environ.copy()

    _cwd = os.path.dirname(compose["path"])
    _env_vars = check_dockerhost(env)

    print("RUNNING: " + compose["path"] + " docker-compose " + " " + action + " " + app)

    try:
        if action == "up":
            _action = docker_compose("up", "-d", app, _cwd=_cwd, _env=_env_vars)
        elif action == "create":
            _action = docker_compose("up", "--no-start", app, _cwd=_cwd, _env=_env_vars)
        elif action == "rm":
            _action = docker_compose("rm", "--force", "--stop", app, _cwd=_cwd, _env=_env_vars)
        else:
            _action = docker_compose(action, app, _cwd=_cwd, _env=_env_vars)
    except Exception as exc:
        if hasattr(exc, "stderr"):
            raise HTTPException(400, exc.stderr.decode("UTF-8").rstrip())
        else:
            raise HTTPException(400, str(exc))

    if _action.stdout.decode("UTF-8").rstrip():
        output = _action.stdout.decode("UTF-8").rstrip()
    elif _action.stderr.decode("UTF-8").rstrip():
        output = _action.stderr.decode("UTF-8").rstrip()
    else:
        output = "No Output"
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

            if loaded_compose.get("volumes"):
                for volume in loaded_compose.get("volumes"):
                    volumes.append(volume)
            if loaded_compose.get("networks"):
                for network in loaded_compose.get("networks"):
                    networks.append(network)
            if loaded_compose.get("services"):
                for service in loaded_compose.get("services"):
                    services[service] = loaded_compose["services"][service]

            with open(file, 'r') as _content:
                content = _content.read()

            compose_object = {
                "name": project,
                "path": file,
                "version": loaded_compose.get("version", "-"),
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
def _write_compose_sync(compose):
    validate_compose_project_name(compose.name)
    if not os.path.exists(settings.COMPOSE_DIR + compose.name):
        try:
            pathlib.Path(settings.COMPOSE_DIR + compose.name).mkdir(parents=True)
        except Exception as exc:
            raise HTTPException(500, str(exc))

    with open(settings.COMPOSE_DIR + compose.name + "/docker-compose.yml", "w") as f:
        try:
            f.write(compose.content)
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
        dclient = docker.from_env()
        stream = io.BytesIO()
        try:
            with zipfile.ZipFile(stream, "w") as zf, open(files[project_name], "r") as fp:
                compose = yaml.load(fp, Loader=yaml.SafeLoader)

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
