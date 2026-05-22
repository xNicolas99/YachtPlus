import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch
from api.routers.auth_2fa import generate_2fa_logic
from api.db.models.users import User

def test_generate_2fa_logic_success():
    # Mock db
    mock_db = MagicMock()
    mock_user = User(username="testuser")
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    # Mock AuthWrapper
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    # Patch pyotp and crypto to avoid external dependencies
    with patch("api.routers.auth_2fa.pyotp.random_base32") as mock_random, \
         patch("api.routers.auth_2fa.encrypt") as mock_encrypt, \
         patch("api.routers.auth_2fa.auth_check_setup_pending") as mock_auth_check, \
         patch("api.routers.auth_2fa.qrcode.QRCode") as mock_qrcode:

        mock_random.return_value = "SECRET123"
        mock_encrypt.return_value = b"encrypted_secret"

        mock_qr_instance = MagicMock()
        mock_qrcode.return_value = mock_qr_instance

        mock_img = MagicMock()
        mock_qr_instance.make_image.return_value = mock_img

        # We need to mock buffered.getvalue() returning bytes
        def save_mock(buffered, format):
            buffered.write(b"fake_image_data")

        mock_img.save.side_effect = save_mock

        # Call function
        result = generate_2fa_logic(mock_db, mock_auth)

        # Assertions
        mock_auth_check.assert_called_once_with(mock_auth)
        mock_auth.get_jwt_subject.assert_called_once_with(allow_setup_pending=True)
        assert mock_user.otp_secret == b"encrypted_secret"
        mock_db.commit.assert_called_once()

        assert result["secret"] == "SECRET123"
        assert result["qr_code"].startswith("data:image/png;base64,")
        assert "provisioning_uri" in result

def test_generate_2fa_logic_user_not_found():
    # Mock db to return None for user
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # Mock AuthWrapper
    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "unknownuser"

    with patch("api.routers.auth_2fa.auth_check_setup_pending") as mock_auth_check:
        with pytest.raises(HTTPException) as excinfo:
            generate_2fa_logic(mock_db, mock_auth)

        assert excinfo.value.status_code == 404
        assert excinfo.value.detail == "User not found"
        mock_auth_check.assert_called_once_with(mock_auth)
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from api.routers.auth_2fa import generate_2fa_logic, generate_2fa_get, generate_2fa

def test_generate_2fa_logic_user_not_found():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "unknown"

    with patch("api.routers.auth_2fa.auth_check_setup_pending") as mock_auth_check:
        with pytest.raises(HTTPException) as exc:
            generate_2fa_logic(mock_db, mock_auth)

        assert exc.value.status_code == 404
        assert exc.value.detail == "User not found"
        mock_auth_check.assert_called_once_with(mock_auth)
        mock_auth.get_jwt_subject.assert_called_once_with(allow_setup_pending=True)

def test_generate_2fa_logic_success():
    mock_user = MagicMock()
    mock_user.username = "testuser"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    with patch("api.routers.auth_2fa.auth_check_setup_pending") as mock_auth_check, \
         patch("api.routers.auth_2fa.pyotp.random_base32", return_value="MOCKSECRET") as mock_random, \
         patch("api.routers.auth_2fa.encrypt", return_value=b"ENCRYPTED_SECRET") as mock_encrypt:

        result = generate_2fa_logic(mock_db, mock_auth)

        mock_auth_check.assert_called_once_with(mock_auth)
        mock_auth.get_jwt_subject.assert_called_once_with(allow_setup_pending=True)

        assert mock_user.otp_secret == b"ENCRYPTED_SECRET"
        mock_db.commit.assert_called_once()

        assert "secret" in result
        assert result["secret"] == "MOCKSECRET"
        assert "qr_code" in result
        assert result["qr_code"].startswith("data:image/png;base64,")
        assert "provisioning_uri" in result
        assert "YachtPlus" in result["provisioning_uri"]
        assert "testuser" in result["provisioning_uri"]

def test_generate_2fa_get():
    mock_db = MagicMock()
    mock_auth = MagicMock()
    with patch("api.routers.auth_2fa.generate_2fa_logic", return_value={"status": "ok"}) as mock_logic:
        result = generate_2fa_get(mock_db, mock_auth)
        assert result == {"status": "ok"}
        mock_logic.assert_called_once_with(mock_db, mock_auth)

def test_generate_2fa_post():
    mock_db = MagicMock()
    mock_auth = MagicMock()
    with patch("api.routers.auth_2fa.generate_2fa_logic", return_value={"status": "ok"}) as mock_logic:
        result = generate_2fa(mock_db, mock_auth)
        assert result == {"status": "ok"}
        mock_logic.assert_called_once_with(mock_db, mock_auth)

from api.routers.auth_2fa import enable_2fa, disable_2fa, TwoFactorRequest

def test_enable_2fa_user_not_found():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "unknown"

    payload = TwoFactorRequest(code="123456")

    with patch("api.routers.auth_2fa.auth_check_setup_pending") as mock_auth_check:
        with pytest.raises(HTTPException) as exc:
            enable_2fa(payload=payload, db=mock_db, Authorize=mock_auth)

        assert exc.value.status_code == 400
        assert exc.value.detail == "2FA setup not initiated"
        mock_auth_check.assert_called_once_with(mock_auth, mock_db)
        mock_auth.get_jwt_subject.assert_called_once_with(allow_setup_pending=True)

def test_enable_2fa_success():
    mock_user = MagicMock()
    mock_user.username = "testuser"
    mock_user.otp_secret = b"ENCRYPTED_SECRET"
    mock_user.is_2fa_enabled = False

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    payload = TwoFactorRequest(code="123456")

    with patch("api.routers.auth_2fa.auth_check_setup_pending") as mock_auth_check, \
         patch("api.routers.auth_2fa.decrypt", return_value="DECRYPTED_SECRET") as mock_decrypt, \
         patch("api.routers.auth_2fa.pyotp.TOTP") as mock_totp_class:

        mock_totp_instance = MagicMock()
        mock_totp_instance.verify.return_value = True
        mock_totp_class.return_value = mock_totp_instance

        result = enable_2fa(payload=payload, db=mock_db, Authorize=mock_auth)

        mock_auth_check.assert_called_once_with(mock_auth)
        mock_decrypt.assert_called_once_with(b"ENCRYPTED_SECRET")
        mock_totp_class.assert_called_once_with("DECRYPTED_SECRET")
        mock_totp_instance.verify.assert_called_once_with("123456")

        assert mock_user.is_2fa_enabled is True
        mock_db.commit.assert_called_once()
        assert result == {"message": "2FA enabled successfully"}

def test_enable_2fa_invalid_code():
    mock_user = MagicMock()
    mock_user.username = "testuser"
    mock_user.otp_secret = b"ENCRYPTED_SECRET"
    mock_user.is_2fa_enabled = False

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    payload = TwoFactorRequest(code="wrong")

    with patch("api.routers.auth_2fa.auth_check_setup_pending") as mock_auth_check, \
         patch("api.routers.auth_2fa.decrypt", return_value="DECRYPTED_SECRET") as mock_decrypt, \
         patch("api.routers.auth_2fa.pyotp.TOTP") as mock_totp_class:

        mock_totp_instance = MagicMock()
        mock_totp_instance.verify.return_value = False
        mock_totp_class.return_value = mock_totp_instance

        with pytest.raises(HTTPException) as exc:
            enable_2fa(payload=payload, db=mock_db, Authorize=mock_auth)

        assert exc.value.status_code == 400
        assert exc.value.detail == "Invalid token or secret error"

def test_enable_2fa_exception():
    mock_user = MagicMock()
    mock_user.username = "testuser"
    mock_user.otp_secret = b"ENCRYPTED_SECRET"
    mock_user.is_2fa_enabled = False

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    payload = TwoFactorRequest(code="123456")

    with patch("api.routers.auth_2fa.auth_check_setup_pending") as mock_auth_check, \
         patch("api.routers.auth_2fa.decrypt", side_effect=Exception("Decryption error")):

        with pytest.raises(HTTPException) as exc:
            enable_2fa(payload=payload, db=mock_db, Authorize=mock_auth)

        assert exc.value.status_code == 400
        assert exc.value.detail == "Invalid token or secret error"

def test_disable_2fa_success():
    mock_user = MagicMock()
    mock_user.username = "testuser"
    mock_user.otp_secret = b"ENCRYPTED_SECRET"
    mock_user.is_2fa_enabled = True

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    mock_auth = MagicMock()
    mock_auth.get_jwt_subject.return_value = "testuser"

    with patch("api.routers.auth_2fa.auth_check") as mock_auth_check:
        result = disable_2fa(db=mock_db, Authorize=mock_auth)

        mock_auth_check.assert_called_once_with(mock_auth)
        mock_auth.get_jwt_subject.assert_called_once_with()

        assert mock_user.is_2fa_enabled is False
        assert mock_user.otp_secret is None
        mock_db.commit.assert_called_once()
        assert result == {"message": "2FA disabled successfully"}
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base
from api.db.models.users import User
from api.routers.auth_2fa import enable_2fa, TwoFactorRequest, disable_2fa
from fastapi import HTTPException
from api.utils.crypto import encrypt
import pyotp
from unittest.mock import patch
from api.routers.auth_2fa import generate_2fa_logic
from api.utils.crypto import decrypt

@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:')
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    yield db
    db.close()

class MockAuth:
    def __init__(self, username, setup_pending=False):
        self.username = username
        self.setup_pending = setup_pending

    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


def test_generate_2fa_logic_success():
    # Setup user (unique username to avoid clashing with module-level shared db)
    u1 = User(username="logic_2fa_user", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("logic_2fa_user")
    result = generate_2fa_logic(db, auth)

    # Validate the response dictionary
    assert "secret" in result
    assert "qr_code" in result
    assert "provisioning_uri" in result
    assert result["qr_code"].startswith("data:image/png;base64,")

    # Validate that the DB record was updated correctly with ENCRYPTED secret
    db.refresh(u1)
    assert u1.otp_secret is not None

    # Assert decryption works and matches generated secret
    decrypted_secret = decrypt(u1.otp_secret)
    assert decrypted_secret == result["secret"]


def test_generate_2fa_logic_user_not_found():
    auth = MockAuth("nonexistent_2fa_user")

    with pytest.raises(HTTPException) as excinfo:
        generate_2fa_logic(db, auth)

    assert excinfo.value.status_code == 404
    assert "User not found" in excinfo.value.detail
import pyotp
from fastapi import HTTPException
from fastapi import HTTPException
from api.routers.auth_2fa import disable_2fa

engine = create_engine('sqlite:///:memory:')
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
db = SessionLocal()

from api.routers.auth_2fa import generate_2fa_get, generate_2fa, enable_2fa, disable_2fa, TwoFactorRequest

class MockAuth:
    def __init__(self, username):
        self.username = username

    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


def test_enable_2fa_success():
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    code = totp.now()

    u1 = User(
        username="admin_2fa", hashed_password="pw", is_superuser=True,
        otp_secret=encrypt(secret)
    )
    db.add(u1)
    db.commit()

    res = enable_2fa(
        payload=TwoFactorRequest(code=code), db=db,
        Authorize=MockAuth("admin_2fa")
    )
    assert res == {"message": "2FA enabled successfully"}

    user = db.query(User).filter(User.username == "admin_2fa").first()
    assert user.is_2fa_enabled is True


def test_enable_2fa_invalid_code():
    secret = pyotp.random_base32()

    u1 = User(
        username="admin_2fa_invalid", hashed_password="pw", is_superuser=True,
        otp_secret=encrypt(secret)
    )
    db.add(u1)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enable_2fa(
            payload=TwoFactorRequest(code="000000"), db=db,
            Authorize=MockAuth("admin_2fa_invalid")
        )

    assert exc.value.status_code == 400
    assert "Invalid token or secret error" in exc.value.detail


def test_enable_2fa_no_setup_initiated():
    u1 = User(
        username="admin_2fa_no_setup", hashed_password="pw", is_superuser=True,
        otp_secret=None
    )
    db.add(u1)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        enable_2fa(
            payload=TwoFactorRequest(code="123456"), db=db,
            Authorize=MockAuth("admin_2fa_no_setup")
        )

    assert exc.value.status_code == 400
    assert "2FA setup not initiated" in exc.value.detail


def test_disable_2fa_success():
    secret = pyotp.random_base32()
    u1 = User(
        username="admin_disable_2fa", hashed_password="pw", is_superuser=True,
        otp_secret=encrypt(secret), is_2fa_enabled=True
    )
    db.add(u1)
    db.commit()

    res = disable_2fa(db=db, Authorize=MockAuth("admin_disable_2fa"))
    assert res == {"message": "2FA disabled successfully"}

    user = db.query(User).filter(User.username == "admin_disable_2fa").first()
    assert user.is_2fa_enabled is False
    assert user.otp_secret is None


def test_generate_2fa_success():
    from api.routers.auth_2fa import generate_2fa_logic
    u1 = User(
        username="admin_generate_2fa", hashed_password="pw", is_superuser=True
    )
    db.add(u1)
    db.commit()

    res = generate_2fa_logic(db=db, Authorize=MockAuth("admin_generate_2fa"))
    assert "secret" in res
    assert "qr_code" in res
    assert "provisioning_uri" in res

    user = db.query(User).filter(User.username == "admin_generate_2fa").first()
    assert user.otp_secret is not None


def test_generate_2fa_user_not_found():
    from api.routers.auth_2fa import generate_2fa_logic

    with pytest.raises(HTTPException) as exc:
        generate_2fa_logic(
            db=db, Authorize=MockAuth("admin_generate_2fa_not_found")
        )

    assert exc.value.status_code == 404
    assert "User not found" in exc.value.detail


def test_generate_2fa_get_route():
    from api.routers.auth_2fa import generate_2fa_get
    u1 = User(
        username="admin_generate_get", hashed_password="pw", is_superuser=True
    )
    db.add(u1)
    db.commit()

    res = generate_2fa_get(db=db, Authorize=MockAuth("admin_generate_get"))
    assert "secret" in res
    assert "qr_code" in res


def test_generate_2fa_post_route():
    from api.routers.auth_2fa import generate_2fa
    u1 = User(
        username="admin_generate_post", hashed_password="pw", is_superuser=True
    )
    db.add(u1)
    db.commit()

    res = generate_2fa(db=db, Authorize=MockAuth("admin_generate_post"))
    assert "secret" in res
    assert "qr_code" in res


def test_get_db_yields_session():
    from api.routers.auth_2fa import get_db
    with patch("api.routers.auth_2fa.SessionLocal") as mock_session_local:
        mock_db = mock_session_local.return_value
        db_generator = get_db()
        db_instance = next(db_generator)
        assert db_instance is mock_db

        try:
            next(db_generator)
        except StopIteration:
            pass

        mock_db.close.assert_called_once()
    def jwt_required(self, allow_setup_pending=False):
        return True
    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username

def test_generate_2fa_get_success():
    u1 = User(username="2fauser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("2fauser")

    result = generate_2fa_get(db=db, Authorize=auth)

    assert "secret" in result
    assert "qr_code" in result
    assert "provisioning_uri" in result
    assert result["secret"] is not None
    assert result["qr_code"].startswith("data:image/png;base64,")
    assert "2fauser" in result["provisioning_uri"]

def test_generate_2fa_get_user_not_found():
    auth = MockAuth("unknownuser")

    with pytest.raises(HTTPException) as exc:
        generate_2fa_get(db=db, Authorize=auth)

    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

def test_enable_2fa_success():
    u1 = User(username="enableuser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("enableuser")

    # First generate to set secret
    gen_result = generate_2fa_get(db=db, Authorize=auth)
    secret = gen_result["secret"]

    # Now verify with code
    totp = pyotp.TOTP(secret)
    code = totp.now()

    req = TwoFactorRequest(code=code)
    result = enable_2fa(payload=req, db=db, Authorize=auth)

    assert result == {"message": "2FA enabled successfully"}

    # Check DB
    db.refresh(u1)
    assert u1.is_2fa_enabled == True

def test_enable_2fa_invalid_code():
    u1 = User(username="invalidcodeuser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("invalidcodeuser")

    # First generate to set secret
    generate_2fa_get(db=db, Authorize=auth)

    req = TwoFactorRequest(code="000000")
    with pytest.raises(HTTPException) as exc:
        enable_2fa(payload=req, db=db, Authorize=auth)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid token or secret error"

def test_enable_2fa_not_initiated():
    u1 = User(username="notinitiateduser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("notinitiateduser")

    # Try enabling without generating first
    req = TwoFactorRequest(code="123456")
    with pytest.raises(HTTPException) as exc:
        enable_2fa(payload=req, db=db, Authorize=auth)

    assert exc.value.status_code == 400
    assert exc.value.detail == "2FA setup not initiated"

def test_disable_2fa_success():
    u1 = User(username="disableuser", hashed_password="pw", is_superuser=False, is_2fa_enabled=True, otp_secret="some_secret")
    db.add(u1)
    db.commit()

    auth = MockAuth("disableuser")

    result = disable_2fa(db=db, Authorize=auth)

    assert result == {"message": "2FA disabled successfully"}

    # Check DB
    db.refresh(u1)
    assert u1.is_2fa_enabled == False
    assert u1.otp_secret is None

def test_generate_2fa_post_success():
    u1 = User(username="2fapostuser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("2fapostuser")

    result = generate_2fa(db=db, Authorize=auth)

    assert "secret" in result
    assert "qr_code" in result
    assert "provisioning_uri" in result
    assert result["secret"] is not None
    assert result["qr_code"].startswith("data:image/png;base64,")
    assert "2fapostuser" in result["provisioning_uri"]

    def jwt_required(self, allow_setup_pending=False):
        return True

    def get_jwt_subject(self, allow_setup_pending=False):
        return self.username


def test_disable_2fa_success(monkeypatch):
    monkeypatch.setattr("api.routers.auth_2fa.auth_check", lambda x: None)

    u = User(
        username="testuser",
        hashed_password="pw",
        is_2fa_enabled=True,
        otp_secret="secret"
    )
    db.add(u)
    db.commit()

    res = disable_2fa(db=db, Authorize=MockAuth("testuser"))

    assert res == {"message": "2FA disabled successfully"}

    db_user = db.query(User).filter(User.username == "testuser").first()
    assert db_user.is_2fa_enabled is False
    assert db_user.otp_secret is None


def test_disable_2fa_user_not_found(monkeypatch):
    monkeypatch.setattr("api.routers.auth_2fa.auth_check", lambda x: None)

    with pytest.raises(HTTPException) as exc:
        disable_2fa(db=db, Authorize=MockAuth("nonexistent"))

    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"
