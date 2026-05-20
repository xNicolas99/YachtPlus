import pytest
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
        mock_auth_check.assert_called_once_with(mock_auth)
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
