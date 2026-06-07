from __future__ import annotations

import re
import secrets
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from status_sync_api import __version__
from status_sync_api.config import AppConfig, load_config
from status_sync_api.geocoder import ReverseGeocoder
from status_sync_api.models import (
    LatestStatusResponse,
    RawStatusUpload,
    StatusRecord,
    UploadResponse,
)
from status_sync_api.parser import normalize_status, trim_raw_payload
from status_sync_api.storage import JsonStatusStore

TIMEZONE_OFFSET_RE = re.compile(r"^([+-])(\d{2}):?(\d{2})$")


def create_app(config: AppConfig | None = None) -> FastAPI:
    app_config = config or load_config()
    store = JsonStatusStore(app_config.storage.path)
    geocoder = ReverseGeocoder(app_config.geocode)

    app = FastAPI(
        title="Status Sync API",
        version=__version__,
        description="Self-hosted API for Status Sync Android phone status uploads.",
    )
    app.state.config = app_config
    app.state.store = store
    app.state.geocoder = geocoder

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_config.cors.allow_origins,
        allow_methods=app_config.cors.allow_methods,
        allow_headers=app_config.cors.allow_headers,
        allow_credentials=False,
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "name": "status-sync-api",
            "version": __version__,
            "docs": "/docs",
        }

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/upload_raw", response_model=UploadResponse)
    @app.post("/api/status/upload_raw", response_model=UploadResponse)
    async def upload_raw(
        payload: RawStatusUpload,
        request: Request,
        _: None = Depends(require_upload_auth),
    ) -> UploadResponse:
        config: AppConfig = request.app.state.config
        store: JsonStatusStore = request.app.state.store

        raw_status = _extract_status_payload(payload)
        record = StatusRecord(
            id=uuid4().hex,
            received_at=datetime.now(UTC),
            raw=trim_raw_payload(
                raw_status,
                config.status.max_raw_value_length,
            ),
        )
        store.save(record)

        return UploadResponse(ok=True, id=record.id, received_at=record.received_at)

    @app.get("/api/status/latest", response_model=LatestStatusResponse)
    def latest_status(request: Request) -> LatestStatusResponse:
        config: AppConfig = request.app.state.config
        store: JsonStatusStore = request.app.state.store
        record = store.latest()
        if record is None:
            return LatestStatusResponse(online=False)

        data = normalize_status(
            record.raw,
            config.status.private_values,
            config.processing.device_aliases,
            config.processing.network_aliases,
            request.app.state.geocoder,
        )
        return LatestStatusResponse(
            online=_is_online(record, config),
            updated_at=_to_output_timezone(record.received_at, config.status.output_timezone),
            data=data,
        )

    return app


async def require_upload_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    config: AppConfig = request.app.state.config
    if not config.auth.require_upload_token:
        return

    expected_token = config.auth.upload_token
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload token is required but not configured.",
        )

    if not _is_bearer_token_valid(authorization, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid upload token.",
        )


def _is_bearer_token_valid(authorization: str | None, expected_token: str) -> bool:
    scheme, _, token = (authorization or "").partition(" ")
    return scheme.lower() == "bearer" and secrets.compare_digest(token, expected_token)


def _extract_status_payload(payload: RawStatusUpload) -> dict[str, Any]:
    data = payload.model_dump(mode="json")
    nested = data.get("data")
    if isinstance(nested, dict):
        return nested
    return data


def _is_online(record: StatusRecord, config: AppConfig) -> bool:
    age_seconds = time.time() - _as_aware_datetime(record.received_at).timestamp()
    return age_seconds <= config.status.online_threshold_seconds


def _to_output_timezone(value: datetime, offset: str) -> datetime:
    return _as_aware_datetime(value).astimezone(_parse_timezone(offset))


def _as_aware_datetime(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _parse_timezone(offset: str) -> timezone:
    if offset.upper() == "UTC":
        return UTC

    match = TIMEZONE_OFFSET_RE.match(offset.strip())
    if not match:
        return UTC

    sign, hours, minutes = match.groups()
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    if sign == "-":
        delta = -delta
    return timezone(delta)


app = create_app()
