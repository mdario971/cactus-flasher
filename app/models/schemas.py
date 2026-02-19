"""Pydantic schemas for Cactus Flasher."""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from enum import Enum


class ProjectType(str, Enum):
    ESPHOME = "esphome"
    ARDUINO = "arduino"
    PLATFORMIO = "platformio"


class BoardType(str, Enum):
    ESP32 = "esp32"
    ESP32S2 = "esp32s2"
    ESP32S3 = "esp32s3"
    ESP32C3 = "esp32c3"
    ESP8266 = "esp8266"


# Authentication schemas
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class UserCreate(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserInfo(BaseModel):
    username: str
    created_at: str
    password_changed_at: Optional[str] = None


class UserListResponse(BaseModel):
    users: List[UserInfo]


# Board schemas
class BoardBase(BaseModel):
    name: str
    id: int = Field(..., ge=1, le=99)
    type: BoardType = BoardType.ESP32
    host: Optional[str] = None  # Override DDNS if needed
    hostname: Optional[str] = None  # Custom hostname override
    api_key: Optional[str] = None  # ESPHome native API encryption key
    mac_address: Optional[str] = None  # Board MAC address (AA:BB:CC:DD:EE:FF)
    web_username: Optional[str] = None  # ESPHome web_server HTTP Basic Auth username
    web_password: Optional[str] = None  # ESPHome web_server HTTP Basic Auth password


class BoardCreate(BoardBase):
    pass


class BoardUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[BoardType] = None
    host: Optional[str] = None
    hostname: Optional[str] = None
    api_key: Optional[str] = None
    mac_address: Optional[str] = None
    web_username: Optional[str] = None
    web_password: Optional[str] = None


class SensorInfo(BaseModel):
    id: str
    name: str
    state: Optional[str] = None
    unit: Optional[str] = None


class BoardStatus(BaseModel):
    name: str
    id: int
    type: BoardType
    webserver_port: int
    ota_port: int
    api_port: int
    online: bool
    host: str
    hostname: str
    mac_address: Optional[str] = None
    last_seen: Optional[str] = None
    sensors: Optional[List[SensorInfo]] = None
    device_info: Optional[dict] = None


class BoardList(BaseModel):
    boards: List[BoardStatus]


class BoardStatusLogEntry(BaseModel):
    timestamp: str
    board_name: str
    event: Literal["online", "offline"]
    details: Optional[str] = None


# Build schemas
class BuildRequest(BaseModel):
    project_type: ProjectType
    board_type: BoardType = BoardType.ESP32


class BuildStatus(BaseModel):
    build_id: str
    status: Literal["pending", "building", "success", "failed"]
    message: Optional[str] = None
    firmware_path: Optional[str] = None
    logs: Optional[str] = None


# Flash schemas
class FlashRequest(BaseModel):
    board_name: str
    firmware_path: Optional[str] = None  # Use if already built
    build_id: Optional[str] = None  # Use to flash from a build


class FlashStatus(BaseModel):
    flash_id: str
    board_name: str
    status: Literal["pending", "uploading", "success", "failed"]
    progress: int = 0
    message: Optional[str] = None


# WebSocket message schemas
class WSMessage(BaseModel):
    type: Literal["log", "progress", "status", "error"]
    data: dict
