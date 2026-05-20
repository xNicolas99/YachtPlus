import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.db.database import Base
from api.db.models.users import User
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


def test_generate_2fa_logic_success(db):
    # Setup user
    u1 = User(username="testuser", hashed_password="pw", is_superuser=False)
    db.add(u1)
    db.commit()

    auth = MockAuth("testuser")
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


def test_generate_2fa_logic_user_not_found(db):
    auth = MockAuth("nonexistent_user")

    with pytest.raises(HTTPException) as excinfo:
        generate_2fa_logic(db, auth)

    assert excinfo.value.status_code == 404
    assert "User not found" in excinfo.value.detail
