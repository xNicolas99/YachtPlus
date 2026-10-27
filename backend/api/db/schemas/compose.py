from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Optional


class Compose(BaseModel):
    name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ComposeWrite(Compose):
    content: Optional[Any] = None
    preview_token: Optional[str] = Field(default=None, min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$", exclude=True)
    model_config = ConfigDict(from_attributes=True)


class ComposeRead(ComposeWrite):
    path: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ComposeServiceChange(BaseModel):
    name: str
    change: str


class ComposeSecurityChange(BaseModel):
    service: str
    fields: list[str]


class ComposePreview(BaseModel):
    name: str
    normalized_content: str
    diff: str
    affected_services: list[ComposeServiceChange]
    security_changes: list[ComposeSecurityChange]
    warnings: list[str]
    preview_token: str
