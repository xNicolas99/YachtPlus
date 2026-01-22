from sqlalchemy import Column, String, Boolean, DateTime, Integer
from api.db.database import Base


class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    # Generic settings model placeholder if needed by import references
    # Currently populated to satisfy imports expecting 'Settings' class
    # Real settings might be in api.settings (Pydantic) but this handles DB side.


class SecretKey(Base):
    __tablename__ = "secret_key"
    key = Column(String, primary_key=True, index=True)


class TokenBlacklist(Base):
    __tablename__ = "jwt_token_blacklist"
    jti = Column(String, primary_key=True, index=True)
    expires = Column(DateTime, nullable=True)
    revoked = Column(Boolean, nullable=False)

class SMTPSettings(Base):
    __tablename__ = "smtp_settings"
    id = Column(Integer, primary_key=True, index=True)
    server = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    sender_email = Column(String, nullable=False)
    use_tls = Column(Boolean, default=True)
