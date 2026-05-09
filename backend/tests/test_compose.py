import pytest
from unittest.mock import patch, MagicMock
from api.actions.compose import check_dockerhost

def test_check_dockerhost_with_env_var():
    # If DOCKER_HOST is in environment, it should return it
    env = {"DOCKER_HOST": "tcp://192.168.1.100:2375"}
    result = check_dockerhost(env)
    assert result == {"DOCKER_HOST": "tcp://192.168.1.100:2375"}

@patch('os.path.exists')
@patch('docker.from_env')
def test_check_dockerhost_socket_exists_and_ping_succeeds(mock_from_env, mock_path_exists):
    # Test that if socket exists and ping succeeds, it returns an empty dict
    mock_path_exists.return_value = True
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_from_env.return_value = mock_client

    env = {}
    result = check_dockerhost(env)
    assert result == {}
    mock_path_exists.assert_called_once_with('/var/run/docker.sock')
    mock_from_env.assert_called_once()
    mock_client.ping.assert_called_once()

@patch('os.path.exists')
@patch('docker.from_env')
def test_check_dockerhost_socket_exists_ping_fails(mock_from_env, mock_path_exists):
    # Test that if socket exists but ping fails, it returns {"clear_env": "true"}
    mock_path_exists.return_value = True
    mock_client = MagicMock()
    mock_client.ping.side_effect = Exception("Docker daemon unreachable")
    mock_from_env.return_value = mock_client

    env = {}
    result = check_dockerhost(env)
    assert result == {"clear_env": "true"}
    mock_path_exists.assert_called_once_with('/var/run/docker.sock')
    mock_from_env.assert_called_once()
    mock_client.ping.assert_called_once()

@patch('os.path.exists')
def test_check_dockerhost_socket_does_not_exist(mock_path_exists):
    # Test that if socket does not exist, it returns {"clear_env": "true"}
    mock_path_exists.return_value = False

    env = {}
    result = check_dockerhost(env)
    assert result == {"clear_env": "true"}
    mock_path_exists.assert_called_once_with('/var/run/docker.sock')

from api.actions.compose import _get_compose_sync
from unittest.mock import mock_open

@patch('api.actions.compose.settings')
@patch('api.actions.compose.find_yml_files')
def test_get_compose_sync_no_content(mock_find, mock_settings):
    mock_settings.COMPOSE_DIR = "/fake/dir/"
    mock_find.return_value = {"proj1": "proj1.yml"}
    with patch('builtins.open', mock_open(read_data="")):
        res = _get_compose_sync("proj1")
        assert res['version'] == '-'
        assert res['services'] == {}
        assert res['volumes'] == []
        assert res['networks'] == []
        assert res['content'] == ''
