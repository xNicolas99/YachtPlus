from typing import List, Optional, Union
from pydantic import BaseModel, ConfigDict


class PortsSchema(BaseModel):
    cport: str
    proto: str
    label: Optional[str] = None
    hport: Optional[str] = None


class VolumesSchema(BaseModel):
    container: str
    bind: str


class EnvSchema(BaseModel):
    label: str
    default: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


class SysctlsSchema(BaseModel):
    name: str
    value: str


class DevicesSchema(BaseModel):
    container: str
    host: str


class LabelSchema(BaseModel):
    label: str
    value: str


class DeployForm(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    image: Optional[str] = None
    restart_policy: Optional[str] = None
    notes: Optional[str] = None
    command: Optional[List[str]] = None
    ports: Optional[List[PortsSchema]] = None
    volumes: Optional[List[VolumesSchema]] = None
    env: Optional[List[EnvSchema]] = None
    devices: Optional[List[DevicesSchema]] = None
    labels: Optional[List[LabelSchema]] = None
    sysctls: Optional[List[SysctlsSchema]] = None
    cap_add: Optional[List[str]] = None
    network_mode: Optional[str] = None
    network: Optional[str] = None
    cpus: Optional[float] = None
    mem_limit: Optional[str] = None
    edit: Optional[bool] = None
    id: Optional[str] = None
    template_id: Optional[int] = None


# LOGS #


class DeployLogs(BaseModel):
    logs: str


class AppLogs(BaseModel):
    logs: str


# Processes #


class Processes(BaseModel):
    Processes: List[List[str]]
    Titles: List[str]
