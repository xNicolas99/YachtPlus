from __future__ import annotations
from typing import List, Optional, Union, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TemplateItem(BaseModel):
    id: Optional[int] = None
    type: Optional[int] = None
    title: Optional[str] = None
    name: Optional[str] = None
    platform: Optional[str] = None
    description: Optional[str] = None
    logo: Optional[str] = None
    image: Optional[str] = None
    command: Optional[List[str]] = None
    notes: Optional[str] = None
    categories: Optional[List[Any]] = None
    restart_policy: Optional[str] = None
    ports: Optional[List[Any]] = []
    volumes: Optional[List[Any]] = []
    env: Optional[List[Any]] = []
    devices: Optional[List[Any]] = []
    labels: Optional[List[Any]] = []
    sysctls: Optional[List[Any]] = []
    cap_add: Optional[List[Any]] = []
    network_mode: Optional[str] = None
    network: Optional[str] = None
    cpus: Optional[float] = None # Changed to float for consistency with apps.py
    mem_limit: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


### TEMPLATE ####


class TemplateBase(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TemplateRead(TemplateBase):
    id: Optional[int] = None
    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class TemplateReadAll(TemplateBase):
    items: List[TemplateItem] = []
    model_config = ConfigDict(from_attributes=True)


class TemplateItems(TemplateRead):
    items: List[TemplateItem] = []

    model_config = ConfigDict(from_attributes=True)


### TEMPLATES END ###

### TEMPLATE VARIABLES ###


class TemplateVariables(BaseModel):
    variable: Optional[str] = None
    replacement: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReadTemplateVariables(TemplateVariables):
    id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)


### Export/Import ###


class Import_Export(BaseModel):
    templates: List[TemplateItems] = []
    variables: List[ReadTemplateVariables] = []
    model_config = ConfigDict(from_attributes=True)
