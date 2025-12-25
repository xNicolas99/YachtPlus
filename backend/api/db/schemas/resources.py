from pydantic import BaseModel, ConfigDict
from typing import Optional


class ImageWrite(BaseModel):
    image: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class VolumeWrite(BaseModel):
    name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class NetworkWrite(BaseModel):
    attachable: Optional[bool] = None
    internal: Optional[bool] = None
    ipv4gateway: Optional[str] = None
    ipv4range: Optional[str] = None
    ipv4subnet: Optional[str] = None
    ipv6_enabled: Optional[bool] = None
    ipv6gateway: Optional[str] = None
    ipv6range: Optional[str] = None
    ipv6subnet: Optional[str] = None
    name: Optional[str] = None
    networkDriver: Optional[str] = None
    network_devices: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
