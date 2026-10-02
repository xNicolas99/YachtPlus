import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch, MagicMock, AsyncMock, ANY
from api.main import app
from api.db.database import Base
from api.utils.auth import get_db
from api.auth.jwt import get_auth_wrapper
from api.db.models.setup import SetupStatus

client = TestClient(app)


@pytest.fixture(autouse=True)
def _bypass_middleware(monkeypatch):
    """The 428 setup middleware in api.main reads the real DB on every
    request. Bypass it so these router tests can exercise the handlers
    in isolation."""
    monkeypatch.setattr(
        "api.main.is_setup_completed_async", AsyncMock(return_value=True)
    )

# --- DB-backed helpers (async) ---------------------------------------------

# We use a real in-memory async engine via the shared conftest pattern, but
# the router tests below need a DB object that supports `await db.execute(...)`.
# The simplest robust approach: an AsyncMock-based db whose execute() returns
# awaitable scalars/first.
def _async_db(status_row=None, user_count=0):
    db = AsyncMock()
    # db.execute(select(...)).scalars().first()
    execute_result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.first.return_value = status_row
    execute_result.scalars.return_value = scalars_result
    execute_result.first.return_value = None
    # db.execute(select(func.count())).scalar()
    count_result = MagicMock()
    count_result.scalar.return_value = user_count
    db.execute.side_effect = lambda stmt: (
        count_result if "func" in str(stmt) else execute_result
    )
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def override_db(request):
    # The handlers now call await db.execute(...); provide an async-mocked db.
    db = _async_db()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.clear()


# --- get_setup_status -------------------------------------------------------

@pytest.mark.parametrize("complete,bypassed,expected", [
    (False, False, False),
    (True, False, True),
    (False, True, True),
])
def test_get_setup_status(complete, bypassed, expected):
    status = SetupStatus(is_complete=complete, is_bypassed=bypassed)
    db = _async_db(status_row=status)
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.get("/api/setup/status")
        assert response.status_code == 200
        assert response.json() == {"is_setup": expected}
    finally:
        app.dependency_overrides.clear()


# --- bypass_setup (dev-mode only) -------------------------------------------

def test_bypass_setup(override_db):
    db = override_db
    # user count = 0 so the bypass is allowed
    db.execute.side_effect = lambda stmt: MagicMock(scalar=lambda: 0)
    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.get_settings") as fake_get_settings:
        fake_get_settings.return_value = MagicMock(DISABLE_AUTH=True)
        response = client.post("/api/setup/bypass")
    assert response.status_code == 200
    assert response.json() == {"message": "Setup bypassed"}


def test_bypass_setup_already_completed(override_db):
    db = override_db
    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=True)), \
         patch("api.routers.setup.setup.get_settings") as fake_get_settings:
        fake_get_settings.return_value = MagicMock(DISABLE_AUTH=True)
        response = client.post("/api/setup/bypass")
    assert response.status_code == 200
    assert response.json() == {"message": "Setup already completed or bypassed."}


def test_bypass_setup_users_exist(override_db):
    db = override_db
    # user count > 0 -> refuse
    db.execute.side_effect = lambda stmt: MagicMock(scalar=lambda: 1)
    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.get_settings") as fake_get_settings:
        fake_get_settings.return_value = MagicMock(DISABLE_AUTH=True)
        response = client.post("/api/setup/bypass")
    assert response.status_code == 400
    assert response.json() == {"detail": "Cannot bypass setup after a user has been registered."}


# --- register_first_user ----------------------------------------------------

def test_register_first_user_setup_already_completed(override_db):
    db = override_db
    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=True)):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Setup already completed."}


def test_register_first_user_success_new_user(override_db):
    db = override_db
    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    mock_new_user = MagicMock()
    mock_new_user.username = "admin"

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=None)), \
         patch("api.routers.setup.setup.create_user", new=AsyncMock(return_value=mock_new_user)), \
         patch("api.routers.setup.setup.create_access_token", return_value="fake_token"):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})

    assert response.status_code == 200
    assert response.json() == {"login": "successful", "username": "admin"}
    auth_wrapper_mock.set_access_cookies.assert_called_once_with("fake_token", ANY, max_age=900)


def test_register_first_user_error_creating_user(override_db):
    db = override_db
    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    async def boom(*a, **kw):
        raise Exception("DB error")

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=None)), \
         patch("api.routers.setup.setup.create_user", side_effect=boom):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Could not create setup account."}


def test_register_first_user_success_existing_user(override_db):
    db = override_db
    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    existing_user = MagicMock()
    existing_user.id = 1
    existing_user.username = "admin"
    existing_user.is_superuser = True
    existing_user.hashed_password = "stored_hash"

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=existing_user)), \
         patch("api.routers.setup.setup.verify_password", new=AsyncMock(return_value=True)) as verify, \
         patch("api.routers.setup.setup.create_access_token", return_value="fake_token"):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
    assert response.status_code == 200
    assert response.json() == {"login": "successful", "username": "admin"}
    verify.assert_awaited_once_with("password", "stored_hash")
    db.commit.assert_not_awaited()


def test_register_first_user_rejects_wrong_password_for_existing_user(override_db):
    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    existing_user = MagicMock()
    existing_user.id = 1
    existing_user.is_superuser = True
    existing_user.hashed_password = "stored_hash"

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=existing_user)), \
         patch("api.routers.setup.setup.verify_password", new=AsyncMock(return_value=False)):
        response = client.post("/api/setup/register", json={"username": "admin", "password": "password"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid setup credentials."}
    auth_wrapper_mock.set_access_cookies.assert_not_called()


def test_register_first_user_rejects_second_username(override_db):
    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock
    query_result = MagicMock()
    query_result.first.return_value = (1,)
    override_db.execute.side_effect = None
    override_db.execute.return_value = query_result

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=None)), \
         patch("api.routers.setup.setup.create_user", new=AsyncMock()) as create:
        response = client.post("/api/setup/register", json={"username": "attacker", "password": "password"})
    assert response.status_code == 403
    assert response.json() == {"detail": "Setup account already registered."}
    create.assert_not_awaited()
    auth_wrapper_mock.set_access_cookies.assert_not_called()


def test_register_first_user_rejects_blank_username(override_db):
    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)):
        response = client.post("/api/setup/register", json={"username": "  ", "password": "password"})
    assert response.status_code == 422
    assert response.json() == {"detail": "Username and password are required."}


# --- finalize_setup ---------------------------------------------------------

def test_finalize_setup_already_completed(override_db):
    db = override_db
    auth_wrapper_mock = MagicMock()
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=True)), \
         patch("api.routers.setup.setup.auth_check_setup_pending", new=AsyncMock(return_value=None)):
        response = client.post("/api/setup/finalize")
    assert response.status_code == 200
    assert response.json() == {"message": "Setup already completed"}


def test_finalize_setup_user_not_found(override_db):
    db = override_db
    auth_wrapper_mock = MagicMock()
    auth_wrapper_mock.get_jwt_subject = AsyncMock(return_value="admin")
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.auth_check_setup_pending", new=AsyncMock(return_value=None)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=None)):
        response = client.post("/api/setup/finalize")
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}


def test_finalize_setup_not_superuser(override_db):
    db = override_db
    auth_wrapper_mock = MagicMock()
    auth_wrapper_mock.get_jwt_subject = AsyncMock(return_value="user")
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    mock_user = MagicMock()
    mock_user.is_superuser = False

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.auth_check_setup_pending", new=AsyncMock(return_value=None)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=mock_user)):
        response = client.post("/api/setup/finalize")
    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized"}


def test_finalize_setup_2fa_not_enabled(override_db):
    db = override_db
    auth_wrapper_mock = MagicMock()
    auth_wrapper_mock.get_jwt_subject = AsyncMock(return_value="admin")
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    mock_user = MagicMock()
    mock_user.is_superuser = True
    mock_user.is_2fa_enabled = False

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.auth_check_setup_pending", new=AsyncMock(return_value=None)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=mock_user)):
        response = client.post("/api/setup/finalize")
    assert response.status_code == 400
    assert response.json() == {"detail": "2FA must be enabled to finalize setup."}


def test_finalize_setup_success(override_db):
    db = override_db
    auth_wrapper_mock = MagicMock()
    auth_wrapper_mock.get_jwt_subject = AsyncMock(return_value="admin")
    app.dependency_overrides[get_auth_wrapper] = lambda: auth_wrapper_mock

    mock_user = MagicMock()
    mock_user.username = "admin"
    mock_user.is_superuser = True
    mock_user.is_2fa_enabled = True

    with patch("api.routers.setup.setup.is_setup_completed_async", new=AsyncMock(return_value=False)), \
         patch("api.routers.setup.setup.auth_check_setup_pending", new=AsyncMock(return_value=None)), \
         patch("api.routers.setup.setup.get_user_by_name", new=AsyncMock(return_value=mock_user)), \
         patch("api.routers.setup.setup.mark_setup_completed", new=AsyncMock(return_value=None)), \
         patch("api.routers.setup.setup.create_access_token", return_value="fresh"):
        response = client.post("/api/setup/finalize")
    assert response.status_code == 200
    assert response.json() == {"message": "Setup finalized"}
    assert mock_user.is_active is True
    auth_wrapper_mock.set_access_cookies.assert_called_once()
