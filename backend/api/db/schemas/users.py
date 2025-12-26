from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Union, Optional
from datetime import datetime


class UserBase(BaseModel):
    username: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class UserCreate(UserBase):
    password: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    perm_start: bool = False
    perm_stop: bool = False
    perm_restart: bool = False
    perm_delete: bool = False
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(UserBase):
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    perm_start: Optional[bool] = None
    perm_stop: Optional[bool] = None
    perm_restart: Optional[bool] = None
    perm_delete: Optional[bool] = None
    model_config = ConfigDict(from_attributes=True)


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
