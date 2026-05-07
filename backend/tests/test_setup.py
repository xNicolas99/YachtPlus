import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock
from api.main import app
from api.db.database import Base
from api.utils.auth import get_db
from api.db.models.setup import SetupStatus

client = TestClient(app)

# We will mock the get_db dependency to return a specific state
def mock_get_db_factory(status_mock=None):
    def mock_get_db():
        db = MagicMock()
        # Mocking db.query(SetupStatus).first()
        query_mock = MagicMock()
        query_mock.first.return_value = status_mock
        db.query.return_value = query_mock
        yield db
    return mock_get_db

@pytest.fixture
def override_db(request):
    # Determine what status_mock we want based on indirect parameter
    status_mock = request.param if hasattr(request, 'param') else None
    app.dependency_overrides[get_db] = mock_get_db_factory(status_mock)
    yield
    app.dependency_overrides.clear()

@pytest.mark.parametrize("override_db, expected_is_setup", [
    (None, False), # pending
    (SetupStatus(is_complete=True, is_bypassed=False), True), # complete
    (SetupStatus(is_complete=False, is_bypassed=True), True), # bypassed
], indirect=["override_db"])
@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware check for these tests
def test_get_setup_status(mock_is_setup_completed, mock_exists, override_db, expected_is_setup):
    response = client.get("/api/setup/status")
    assert response.status_code == 200
    assert response.json() == {"is_setup": expected_is_setup}

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
def test_bypass_setup(mock_is_setup_completed, mock_exists):
    # Using a fake DB with real query/add/commit mock
    db = MagicMock()
    query_mock = MagicMock()
    # first call returns None, meaning setup not started
    query_mock.first.return_value = None
    db.query.return_value = query_mock

    app.dependency_overrides[get_db] = lambda: db

    response = client.post("/api/setup/bypass")
    assert response.status_code == 200
    assert response.json() == {"message": "Setup bypassed"}
    db.add.assert_called()
    db.commit.assert_called()

    app.dependency_overrides.clear()
