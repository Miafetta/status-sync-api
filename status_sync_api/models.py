from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RawStatusUpload(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: dict[str, Any] | None = None
    model: str | None = None
    battery_raw: str | None = None
    window_raw: str | None = None
    wifi_raw: str | None = None
    net_raw: str | None = None
    location_raw: str | None = None
    current_app_package: str | None = None
    current_app_name: str | None = None


class StatusRecord(BaseModel):
    id: str
    received_at: datetime
    raw: dict[str, Any]


class PhoneStatusData(BaseModel):
    device_name: str | None = None
    battery_level: int | None = Field(default=None, ge=0, le=100)
    battery_charging: bool | None = None
    wifi_connected: bool | None = None
    wifi_ssid: str | None = None
    network_type: str | None = None
    current_app: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None


class LatestStatusResponse(BaseModel):
    online: bool
    updated_at: datetime | None = None
    data: PhoneStatusData | None = None


class UploadResponse(BaseModel):
    ok: bool
    id: str
    received_at: datetime
