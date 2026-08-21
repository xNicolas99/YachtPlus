"""Single source of truth for constructing the synchronous docker SDK client.

Several code paths previously called ``docker.from_env()`` directly. That
function only reads ``DOCKER_HOST`` from the OS environment and otherwise
falls back to ``/var/run/docker.sock``. The rest of the codebase honours
``settings.DOCKER_HOST``, so when an operator fronts the daemon with a TCP
proxy (e.g. tecnativa/docker-socket-proxy) the ``from_env`` paths silently
bypassed the proxy and either failed or talked to the host socket directly.

Always use :func:`get_sync_docker_client` for the sync SDK.
"""

from contextlib import contextmanager
import docker

from api.settings import Settings

_settings = Settings()


def get_sync_docker_client() -> docker.DockerClient:
    """Return a sync docker client bound to settings.DOCKER_HOST when set.

    Falls back to docker.from_env() (which itself honours DOCKER_HOST env
    + DOCKER_CERT_PATH/DOCKER_TLS_VERIFY) only when no explicit URL is
    configured. Callers must close the returned client (or use it as a
    short-lived local variable) — there is no global instance.
    """
    if _settings.DOCKER_HOST:
        return docker.DockerClient(base_url=_settings.DOCKER_HOST)
    return docker.from_env()


@contextmanager
def sync_docker_client():
    """Context-managed variant of get_sync_docker_client().

    Guarantees .close() is called even if an exception is raised, preventing
    connection leaks in sync helpers that run inside the async thread pool.
    """
    client = get_sync_docker_client()
    try:
        yield client
    finally:
        client.close()
