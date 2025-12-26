from pydantic import BaseModel, ConfigDict
from typing import Any, Optional


class Compose(BaseModel):
    name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class ComposeWrite(Compose):
    content: Optional[Any] = None
    model_config = ConfigDict(from_attributes=True)


class ComposeRead(ComposeWrite):
    path: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
