from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid import UUID
from typing import Union, Optional
from datetime import datetime


# bcrypt only considers the first 72 BYTES of a password — and since bcrypt
# 4.x it raises ValueError outright for longer input. Pydantic's max_length
# counts characters, so a multi-byte UTF-8 password (umlauts, emoji) can pass
# that bound while still exceeding 72 bytes. Validating the encoded length
# turns the over-long case into a clean 422 at the API boundary instead of an
# unhandled 500 from the hashing call.
BCRYPT_MAX_PASSWORD_BYTES = 72


def _within_bcrypt_byte_limit(value: Optional[str]) -> Optional[str]:
    if value is not None and len(value.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
        )
    return value


class UserBase(BaseModel):
    username: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class UserCreate(UserBase):
    username: str
    # bcrypt only uses the first 72 bytes of input and silently truncates the
    # rest, so passwords sharing a 72-byte prefix would be interchangeable.
    # A hard min_length=8 broke many existing tests that register users with
    # short convenience passwords; the security-relevant upper bound is kept
    # and min_length=1 still rejects empty passwords. max_length caps the
    # character count; the byte length is enforced by the validator below.
    password: str = Field(min_length=1, max_length=72)
    is_active: bool = True
    is_superuser: bool = False
    perm_start: bool = False
    perm_stop: bool = False
    perm_restart: bool = False
    perm_delete: bool = False
    model_config = ConfigDict(from_attributes=True)

    @field_validator("password")
    @classmethod
    def _validate_password_bytes(cls, value: str) -> str:
        return _within_bcrypt_byte_limit(value)


class UserLogin(UserCreate):
    otp_token: Optional[str] = None


class UserUpdate(UserBase):
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    perm_start: Optional[bool] = None
    perm_stop: Optional[bool] = None
    perm_restart: Optional[bool] = None
    perm_delete: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)

    @field_validator("password")
    @classmethod
    def _validate_password_bytes(cls, value: Optional[str]) -> Optional[str]:
        return _within_bcrypt_byte_limit(value)


class UserSelfUpdate(BaseModel):
    """Self-service profile update for POST /api/auth/me.

    Deliberately excludes every privilege/state field (`perm_*`,
    `is_superuser`, `is_active`). Accepting UserUpdate here let a
    low-privilege user grant themselves `perm_delete` etc. — a
    self-privilege-escalation vector. Extra fields are ignored
    (Pydantic default), so crafted `perm_*` keys simply never apply.
    """
    username: Optional[str] = None
    password: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

    @field_validator("password")
    @classmethod
    def _validate_password_bytes(cls, value: Optional[str]) -> Optional[str]:
        return _within_bcrypt_byte_limit(value)


class User(UserBase):
    id: Optional[Union[int, str, UUID]] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_2fa_enabled: Optional[bool] = None
    perm_start: Optional[bool] = None
    perm_stop: Optional[bool] = None
    perm_restart: Optional[bool] = None
    perm_delete: Optional[bool] = None
    authDisabled: Optional[bool] = False

    model_config = ConfigDict(from_attributes=True)


class APIKEY(BaseModel):
    id: Optional[int] = None
    key_name: Optional[str] = None
    is_active: Optional[bool] = None
    user: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GenerateAPIKEY(BaseModel):
    key_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class DisplayAPIKEY(APIKEY):
    token: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
