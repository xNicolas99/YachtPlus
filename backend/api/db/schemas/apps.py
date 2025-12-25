from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class PortsSchema(BaseModel):
    cport: Optional[str] = None
    proto: Optional[str] = None
    label: Optional[str] = None
    hport: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class VolumesSchema(BaseModel):
    container: Optional[str] = None
    bind: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class EnvSchema(BaseModel):
    label: Optional[str] = None
    default: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class SysctlsSchema(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class DevicesSchema(BaseModel):
    container: Optional[str] = None
    host: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class LabelSchema(BaseModel):
    label: Optional[str] = None
    value: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


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
    logs: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class AppLogs(BaseModel):
    logs: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# Processes #


class Processes(BaseModel):
    Processes: Optional[List[List[str]]] = None
    Titles: Optional[List[str]] = None
    model_config = ConfigDict(from_attributes=True)
