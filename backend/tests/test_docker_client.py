"""Pin the docker SDK construction to settings.DOCKER_HOST so the few
sync helpers that previously called docker.from_env() can't bypass an
operator-configured TCP proxy.
"""
from unittest.mock import patch, MagicMock

from api.utils import docker_client


def test_get_sync_docker_client_uses_settings_when_configured():
    fake_settings = MagicMock()
    fake_settings.DOCKER_HOST = "tcp://10.0.0.50:2375"

    with patch.object(docker_client, "_settings", fake_settings), \
         patch.object(docker_client.docker, "DockerClient") as docker_client_ctor, \
         patch.object(docker_client.docker, "from_env") as from_env:
        docker_client.get_sync_docker_client()

    docker_client_ctor.assert_called_once_with(base_url="tcp://10.0.0.50:2375")
    from_env.assert_not_called()


def test_get_sync_docker_client_falls_back_to_from_env_when_unset():
    fake_settings = MagicMock()
    fake_settings.DOCKER_HOST = None

    with patch.object(docker_client, "_settings", fake_settings), \
         patch.object(docker_client.docker, "DockerClient") as docker_client_ctor, \
         patch.object(docker_client.docker, "from_env") as from_env:
        docker_client.get_sync_docker_client()

    from_env.assert_called_once()
    docker_client_ctor.assert_not_called()


def test_get_sync_docker_client_falls_back_when_empty_string():
    """An empty DOCKER_HOST string is equivalent to "not set" — fall back
    to from_env so we don't try to dial `base_url=""`."""
    fake_settings = MagicMock()
    fake_settings.DOCKER_HOST = ""

    with patch.object(docker_client, "_settings", fake_settings), \
         patch.object(docker_client.docker, "DockerClient") as docker_client_ctor, \
         patch.object(docker_client.docker, "from_env") as from_env:
        docker_client.get_sync_docker_client()

    from_env.assert_called_once()
    docker_client_ctor.assert_not_called()
