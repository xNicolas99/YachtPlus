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
