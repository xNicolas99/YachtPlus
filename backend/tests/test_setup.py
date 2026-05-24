import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock, ANY
from api.main import app
from api.db.database import Base
from api.utils.auth import get_db
from api.auth.jwt import get_auth_wrapper
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

# bypass_setup is now dev-mode-only (DISABLE_AUTH=True). The success-path
# tests below open the gate via a Settings patch; an additional production-
# mode regression test lives in test_setup_bypass_guard.py.
@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
def test_bypass_setup(mock_is_setup_completed, mock_exists):
    db = MagicMock()
    def mock_query(model):
        q = MagicMock()
        if model.__name__ == "User":
            q.count.return_value = 0
        else:
            q.first.return_value = None
        return q
    db.query.side_effect = mock_query

    app.dependency_overrides[get_db] = lambda: db

    with patch("api.settings.Settings") as fake_settings_cls:
        fake_settings_cls.return_value.DISABLE_AUTH = True
        response = client.post("/api/setup/bypass")
    assert response.status_code == 200
    assert response.json() == {"message": "Setup bypassed"}
    db.add.assert_called()
    db.commit.assert_called()

    app.dependency_overrides.clear()


from api.routers.setup.setup import is_setup_completed, mark_setup_completed
import os

def test_is_setup_completed_no_db():
    with patch("api.routers.setup.setup.os.path.exists", return_value=True):
        assert is_setup_completed(None) == True
    with patch("api.routers.setup.setup.os.path.exists", return_value=False):
        assert is_setup_completed(None) == False

def test_is_setup_completed_with_db_complete():
    db = MagicMock()
    status_mock = SetupStatus(is_complete=True, is_bypassed=False)
    db.query().first.return_value = status_mock
    assert is_setup_completed(db) == True

def test_is_setup_completed_with_db_bypassed():
    db = MagicMock()
    status_mock = SetupStatus(is_complete=False, is_bypassed=True)
    db.query().first.return_value = status_mock
    assert is_setup_completed(db) == True

def test_is_setup_completed_with_db_incomplete_file_fallback():
    db = MagicMock()
    status_mock = SetupStatus(is_complete=False, is_bypassed=False)
    db.query().first.return_value = status_mock
    with patch("api.routers.setup.setup.os.path.exists", return_value=True):
        assert is_setup_completed(db) == True

def test_is_setup_completed_with_db_incomplete_no_file():
    db = MagicMock()
    status_mock = SetupStatus(is_complete=False, is_bypassed=False)
    db.query().first.return_value = status_mock
    with patch("api.routers.setup.setup.os.path.exists", return_value=False):
        assert is_setup_completed(db) == False

def test_is_setup_completed_no_status_no_file():
    db = MagicMock()
    db.query().first.return_value = None
    with patch("api.routers.setup.setup.os.path.exists", return_value=False):
        assert is_setup_completed(db) == False

@patch("api.routers.setup.setup.os.makedirs")
@patch("api.routers.setup.setup.open")
def test_mark_setup_completed_existing_status(mock_open, mock_makedirs):
    db = MagicMock()
    status_mock = MagicMock()
    status_mock.is_complete = False
    db.query().first.return_value = status_mock

    mark_setup_completed(db)

    assert status_mock.is_complete == True
    db.commit.assert_called_once()
    mock_makedirs.assert_called_once()
    mock_open.assert_called_once()

@patch("api.routers.setup.setup.os.makedirs")
@patch("api.routers.setup.setup.open")
def test_mark_setup_completed_new_status(mock_open, mock_makedirs):
    db = MagicMock()
    db.query().first.return_value = None

    mark_setup_completed(db)

    db.add.assert_called_once()
    added_status = db.add.call_args[0][0]
    assert isinstance(added_status, SetupStatus)
    assert added_status.is_complete == True
    db.commit.assert_called_once()
    mock_makedirs.assert_called_once()
    mock_open.assert_called_once()

@patch("api.routers.setup.setup.os.makedirs", side_effect=Exception("Read-only FS"))
def test_mark_setup_completed_file_error(mock_makedirs):
    db = MagicMock()
    db.query().first.return_value = None

    # Should not raise
    mark_setup_completed(db)

    db.add.assert_called_once()
    db.commit.assert_called_once()



@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
def test_bypass_setup_already_completed(mock_is_setup_completed, mock_exists):
    db = MagicMock()
    # Mocking is_setup_completed return True inside the route handler
    with patch("api.routers.setup.setup.is_setup_completed", return_value=True), \
         patch("api.settings.Settings") as fake_settings_cls:
        fake_settings_cls.return_value.DISABLE_AUTH = True
        app.dependency_overrides[get_db] = lambda: db
        response = client.post("/api/setup/bypass")
        assert response.status_code == 200
        assert response.json() == {"message": "Setup already completed or bypassed."}
        db.add.assert_not_called()
        db.commit.assert_not_called()
        app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
def test_bypass_setup_users_exist(mock_is_setup_completed, mock_exists):
    db = MagicMock()

    def mock_query(model):
        q = MagicMock()
        if model.__name__ == "User":
            q.count.return_value = 1  # User exists!
        else:
            q.first.return_value = None
        return q
    db.query.side_effect = mock_query

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False), \
         patch("api.settings.Settings") as fake_settings_cls:
        fake_settings_cls.return_value.DISABLE_AUTH = True
        app.dependency_overrides[get_db] = lambda: db
        response = client.post("/api/setup/bypass")
        assert response.status_code == 400
        assert response.json() == {"detail": "Cannot bypass setup after a user has been registered."}
        db.add.assert_not_called()
        db.commit.assert_not_called()
        app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
def test_bypass_setup_existing_status(mock_is_setup_completed, mock_exists):
    db = MagicMock()
    status_mock = MagicMock()
    status_mock.is_bypassed = False

    def mock_query(model):
        q = MagicMock()
        if model.__name__ == "User":
            q.count.return_value = 0
        else:
            q.first.return_value = status_mock
        return q
    db.query.side_effect = mock_query

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False), \
         patch("api.settings.Settings") as fake_settings_cls:
        fake_settings_cls.return_value.DISABLE_AUTH = True
        app.dependency_overrides[get_db] = lambda: db
        response = client.post("/api/setup/bypass")
        assert response.status_code == 200
        assert response.json() == {"message": "Setup bypassed"}
        assert status_mock.is_bypassed == True
        db.commit.assert_called_once()
        app.dependency_overrides.clear()


@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
def test_register_first_user_setup_already_completed(mock_is_setup_completed, mock_exists):
    db = MagicMock()
    with patch("api.routers.setup.setup.is_setup_completed", return_value=True):
        app.dependency_overrides[get_db] = lambda: db
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
        assert response.status_code == 403
        assert response.json() == {"detail": "Setup already completed."}
        app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_user_by_name")
@patch("api.routers.setup.setup.create_user")
@patch("api.routers.setup.setup.create_access_token", return_value="fake_token")
@patch("api.routers.setup.setup.get_auth_wrapper")
def test_register_first_user_success_new_user(mock_get_auth_wrapper, mock_create_access_token, mock_create_user, mock_get_user, mock_is_setup_completed, mock_exists):
    db = MagicMock()
    mock_get_user.return_value = None

    mock_new_user = MagicMock()
    mock_new_user.username = "admin"
    mock_create_user.return_value = mock_new_user

    auth_wrapper_mock = MagicMock()

    # We must patch get_auth_wrapper as a dependency correctly
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
        assert response.status_code == 200
        assert response.json() == {"login": "successful", "username": "admin"}

        # Check create_user call
        mock_create_user.assert_called_once()
        user_arg = mock_create_user.call_args[1]['user']
        assert user_arg.username == "admin"
        assert user_arg.is_superuser == True
        assert user_arg.is_active == False

        # Check cookie (now includes a 15-minute max_age for the setup-pending token)
        auth_wrapper_mock.set_access_cookies.assert_called_once_with("fake_token", ANY, max_age=900)

    app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_user_by_name")
@patch("api.routers.setup.setup.create_user")
@patch("api.routers.setup.setup.create_access_token", return_value="fake_token")
@patch("api.routers.setup.setup.get_auth_wrapper")
def test_register_first_user_error_creating_user(mock_get_auth_wrapper, mock_create_access_token, mock_create_user, mock_get_user, mock_is_setup_completed, mock_exists):
    db = MagicMock()
    mock_get_user.return_value = None

    mock_create_user.side_effect = Exception("DB error")

    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
        assert response.status_code == 400
        assert response.json() == {"detail": "Error creating user: DB error"}

    app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_user_by_name")
@patch("api.routers.setup.setup.update_user_by_id")
@patch("api.routers.setup.setup.create_access_token", return_value="fake_token")
@patch("api.routers.setup.setup.get_auth_wrapper")
def test_register_first_user_success_existing_user(mock_get_auth_wrapper, mock_create_access_token, mock_update_user, mock_get_user, mock_is_setup_completed, mock_exists):
    db = MagicMock()
    existing_user_mock = MagicMock()
    existing_user_mock.id = 1
    mock_get_user.return_value = existing_user_mock

    updated_user_mock = MagicMock()
    updated_user_mock.username = "admin"
    mock_update_user.return_value = updated_user_mock

    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
        assert response.status_code == 200
        assert response.json() == {"login": "successful", "username": "admin"}

        # Check update_user call
        mock_update_user.assert_called_once()
        id_arg = mock_update_user.call_args[0][1]
        user_update_arg = mock_update_user.call_args[0][2]
        assert id_arg == 1
        assert user_update_arg.username == "admin"
        assert user_update_arg.is_superuser == True
        assert user_update_arg.is_active == False

    app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_user_by_name")
@patch("api.routers.setup.setup.update_user_by_id", return_value=None)
@patch("api.routers.setup.setup.get_auth_wrapper")
def test_register_first_user_error_updating_user(mock_get_auth_wrapper, mock_update_user, mock_get_user, mock_is_setup_completed, mock_exists):
    db = MagicMock()
    existing_user_mock = MagicMock()
    existing_user_mock.id = 1
    mock_get_user.return_value = existing_user_mock

    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
        assert response.status_code == 500
        assert response.json() == {"detail": "Failed to update user."}

    app.dependency_overrides.clear()



@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_auth_wrapper")
@patch("api.routers.setup.setup.auth_check")
def test_finalize_setup_already_completed(mock_auth_check, mock_get_auth_wrapper, mock_is_setup_completed, mock_exists):
    db = MagicMock()

    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    with patch("api.routers.setup.setup.is_setup_completed", return_value=True):
        response = client.post("/api/setup/finalize")
        assert response.status_code == 200
        assert response.json() == {"message": "Setup already completed"}

    app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_auth_wrapper")
@patch("api.routers.setup.setup.auth_check")
@patch("api.routers.setup.setup.get_user_by_name")
def test_finalize_setup_user_not_found(mock_get_user, mock_auth_check, mock_get_auth_wrapper, mock_is_setup_completed, mock_exists):
    db = MagicMock()

    auth_wrapper_mock = MagicMock()
    auth_wrapper_mock.get_jwt_subject.return_value = "admin"
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    mock_get_user.return_value = None

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False):
        response = client.post("/api/setup/finalize")
        assert response.status_code == 403
        assert response.json() == {"detail": "Not authorized"}

    app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_auth_wrapper")
@patch("api.routers.setup.setup.auth_check")
@patch("api.routers.setup.setup.get_user_by_name")
def test_finalize_setup_not_superuser(mock_get_user, mock_auth_check, mock_get_auth_wrapper, mock_is_setup_completed, mock_exists):
    db = MagicMock()

    auth_wrapper_mock = MagicMock()
    auth_wrapper_mock.get_jwt_subject.return_value = "user"
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    mock_user = MagicMock()
    mock_user.is_superuser = False
    mock_get_user.return_value = mock_user

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False):
        response = client.post("/api/setup/finalize")
        assert response.status_code == 403
        assert response.json() == {"detail": "Not authorized"}

    app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_auth_wrapper")
@patch("api.routers.setup.setup.auth_check")
@patch("api.routers.setup.setup.get_user_by_name")
def test_finalize_setup_2fa_not_enabled(mock_get_user, mock_auth_check, mock_get_auth_wrapper, mock_is_setup_completed, mock_exists):
    db = MagicMock()

    auth_wrapper_mock = MagicMock()
    auth_wrapper_mock.get_jwt_subject.return_value = "admin"
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    mock_user = MagicMock()
    mock_user.is_superuser = True
    mock_user.is_2fa_enabled = False
    mock_get_user.return_value = mock_user

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False):
        response = client.post("/api/setup/finalize")
        assert response.status_code == 400
        assert response.json() == {"detail": "2FA must be enabled to finalize setup."}

    app.dependency_overrides.clear()

@patch("api.routers.setup.setup.os.path.exists", return_value=False)
@patch("api.main.is_setup_completed", return_value=True) # Bypass main's middleware
@patch("api.routers.setup.setup.get_auth_wrapper")
@patch("api.routers.setup.setup.auth_check")
@patch("api.routers.setup.setup.get_user_by_name")
@patch("api.routers.setup.setup.mark_setup_completed")
def test_finalize_setup_success(mock_mark_setup_completed, mock_get_user, mock_auth_check, mock_get_auth_wrapper, mock_is_setup_completed, mock_exists):
    db = MagicMock()

    auth_wrapper_mock = MagicMock()
    auth_wrapper_mock.get_jwt_subject.return_value = "admin"
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    app.dependency_overrides[get_db] = lambda: db

    mock_user = MagicMock()
    mock_user.username = "admin"
    mock_user.is_superuser = True
    mock_user.is_2fa_enabled = True
    mock_get_user.return_value = mock_user

    with patch("api.routers.setup.setup.is_setup_completed", return_value=False):
        response = client.post("/api/setup/finalize")
        assert response.status_code == 200
        assert response.json() == {"message": "Setup finalized"}

        assert mock_user.is_active == True
        db.commit.assert_called_once()
        mock_mark_setup_completed.assert_called_once_with(db)

    app.dependency_overrides.clear()
