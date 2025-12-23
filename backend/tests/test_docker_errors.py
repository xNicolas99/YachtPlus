import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import docker.errors
import requests.exceptions
import sys
import os

# Add backend to path so we can import api
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from api.main import app

# We need to bypass authentication for these tests
from api.auth.jwt import get_auth_wrapper

# Mock AuthWrapper
class MockAuthWrapper:
    def __init__(self, request):
        pass
    def jwt_required(self):
        return MagicMock(username="test", id=1)
    def get_jwt_subject(self):
        return "test"

app.dependency_overrides[get_auth_wrapper] = lambda: MockAuthWrapper(None)

client = TestClient(app)

@pytest.fixture
def mock_docker():
    with patch("docker.from_env") as mock:
        yield mock

def test_docker_permission_denied(mock_docker):
    """
    Test that a PermissionError (e.g. wrong GID) returns 503 and clear message.
    """
    # Simulate PermissionError
    # docker.errors.DockerException: Error while fetching server API version: ('Connection aborted.', PermissionError(13, 'Permission denied'))
    mock_docker.side_effect = docker.errors.DockerException("Error while fetching server API version: Permission denied")

    response = client.get("/api/apps/")

    assert response.status_code == 503
    data = response.json()
    assert "Permission denied while accessing Docker socket" in data["detail"]
    assert "DOCKER_GID" in data["detail"]

def test_docker_socket_missing(mock_docker):
    """
    Test that a FileNotFoundError (missing socket) returns 503 and clear message.
    """
    # docker.errors.DockerException: Error while fetching server API version: ('Connection aborted.', FileNotFoundError(2, 'No such file or directory'))
    mock_docker.side_effect = docker.errors.DockerException("Error while fetching server API version: FileNotFoundError")

    response = client.get("/api/apps/")

    assert response.status_code == 503
    data = response.json()
    assert "Docker connection failed" in data["detail"]
    assert "/var/run/docker.sock is mounted" in data["detail"]

def test_docker_connection_refused(mock_docker):
    """
    Test that Connection Refused returns 503.
    """
    mock_docker.side_effect = docker.errors.DockerException("Error while fetching server API version: Connection refused")

    response = client.get("/api/apps/")

    assert response.status_code == 503
    data = response.json()
    assert "Docker connection failed" in data["detail"]
