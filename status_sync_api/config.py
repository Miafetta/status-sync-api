from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_NETWORK_ALIASES: dict[str, str | None] = {
    "NR": "5G",
    "NR_SA": "5G",
    "NR_NSA": "5G",
    "LTE": "4G",
    "IWLAN": "Wi-Fi Calling",
    "Unknown": None,
}


@dataclass(frozen=True)
class ServerConfig:
    host: str = "0.0.0.0"
    port: int = 8000


@dataclass(frozen=True)
class AuthConfig:
    upload_token: str = ""
    require_upload_token: bool = True


@dataclass(frozen=True)
class StorageConfig:
    path: Path = Path("data/status.json")


@dataclass(frozen=True)
class RoutesConfig:
    upload: str = "/upload"
    status: str = "/status"
    health: str = "/health"


@dataclass(frozen=True)
class StatusConfig:
    online_threshold_seconds: int = 1800
    private_values: list[str] = field(default_factory=lambda: ["none"])
    max_raw_value_length: int = 20000
    output_timezone: str = "+08:00"


@dataclass(frozen=True)
class ProcessingConfig:
    device_aliases: dict[str, str] = field(default_factory=dict)
    network_aliases: dict[str, str | None] = field(
        default_factory=lambda: DEFAULT_NETWORK_ALIASES.copy()
    )


@dataclass(frozen=True)
class CorsConfig:
    allow_origins: list[str] = field(default_factory=lambda: ["*"])
    allow_methods: list[str] = field(default_factory=lambda: ["GET", "POST", "OPTIONS"])
    allow_headers: list[str] = field(default_factory=lambda: ["*"])


@dataclass(frozen=True)
class GeocodeConfig:
    enabled: bool = True
    endpoint: str = "https://nominatim.openstreetmap.org/reverse"
    user_agent: str = "status-sync-api/0.1"
    language: str = "zh-CN"
    timeout_seconds: float = 5.0
    cache_ttl_seconds: int = 86400
    zoom: int = 12


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    routes: RoutesConfig = field(default_factory=RoutesConfig)
    status: StatusConfig = field(default_factory=StatusConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    cors: CorsConfig = field(default_factory=CorsConfig)
    geocode: GeocodeConfig = field(default_factory=GeocodeConfig)


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path or os.getenv("STATUS_SYNC_CONFIG", DEFAULT_CONFIG_PATH))
    data = _load_yaml(config_path)

    return AppConfig(
        server=ServerConfig(
            host=_env_str("STATUS_SYNC_HOST", data, "server", "host", default="0.0.0.0"),
            port=_env_int("STATUS_SYNC_PORT", data, "server", "port", default=8000),
        ),
        auth=AuthConfig(
            upload_token=_env_str("STATUS_SYNC_UPLOAD_TOKEN", data, "auth", "upload_token"),
            require_upload_token=_env_bool(
                "STATUS_SYNC_REQUIRE_UPLOAD_TOKEN",
                data,
                "auth",
                "require_upload_token",
                default=True,
            ),
        ),
        storage=StorageConfig(
            path=Path(
                _env_str(
                    "STATUS_SYNC_STORAGE_PATH",
                    data,
                    "storage",
                    "path",
                    default="data/status.json",
                )
            ),
        ),
        routes=RoutesConfig(
            upload=_route_path(data, "routes", "upload", default="/upload"),
            status=_route_path(data, "routes", "status", default="/status"),
            health=_route_path(data, "routes", "health", default="/health"),
        ),
        status=StatusConfig(
            online_threshold_seconds=max(
                1,
                _env_int(
                    "STATUS_SYNC_ONLINE_THRESHOLD_SECONDS",
                    data,
                    "status",
                    "online_threshold_seconds",
                    default=1800,
                ),
            ),
            private_values=_env_list(
                "STATUS_SYNC_PRIVATE_VALUES",
                data,
                "status",
                "private_values",
                default=["none"],
            ),
            max_raw_value_length=max(
                100,
                _env_int(
                    "STATUS_SYNC_MAX_RAW_VALUE_LENGTH",
                    data,
                    "status",
                    "max_raw_value_length",
                    default=20000,
                ),
            ),
            output_timezone=_env_str(
                "STATUS_SYNC_OUTPUT_TIMEZONE",
                data,
                "status",
                "output_timezone",
                default="+08:00",
            ),
        ),
        processing=ProcessingConfig(
            device_aliases=_str_dict(data, "processing", "device_aliases"),
            network_aliases={
                **DEFAULT_NETWORK_ALIASES,
                **_nullable_str_dict(data, "processing", "network_aliases"),
            },
        ),
        cors=CorsConfig(
            allow_origins=_env_list(
                "STATUS_SYNC_CORS_ORIGINS",
                data,
                "cors",
                "allow_origins",
                default=["*"],
            ),
            allow_methods=_env_list(
                "STATUS_SYNC_CORS_METHODS",
                data,
                "cors",
                "allow_methods",
                default=["GET", "POST", "OPTIONS"],
            ),
            allow_headers=_env_list(
                "STATUS_SYNC_CORS_HEADERS",
                data,
                "cors",
                "allow_headers",
                default=["*"],
            ),
        ),
        geocode=GeocodeConfig(
            enabled=_env_bool(
                "STATUS_SYNC_GEOCODE_ENABLED",
                data,
                "geocode",
                "enabled",
                default=True,
            ),
            endpoint=_env_str(
                "STATUS_SYNC_GEOCODE_ENDPOINT",
                data,
                "geocode",
                "endpoint",
                default="https://nominatim.openstreetmap.org/reverse",
            ),
            user_agent=_env_str(
                "STATUS_SYNC_GEOCODE_USER_AGENT",
                data,
                "geocode",
                "user_agent",
                default="status-sync-api/0.1",
            ),
            language=_env_str(
                "STATUS_SYNC_GEOCODE_LANGUAGE",
                data,
                "geocode",
                "language",
                default="zh-CN",
            ),
            timeout_seconds=max(
                0.5,
                _env_float(
                    "STATUS_SYNC_GEOCODE_TIMEOUT_SECONDS",
                    data,
                    "geocode",
                    "timeout_seconds",
                    default=5.0,
                ),
            ),
            cache_ttl_seconds=max(
                60,
                _env_int(
                    "STATUS_SYNC_GEOCODE_CACHE_TTL_SECONDS",
                    data,
                    "geocode",
                    "cache_ttl_seconds",
                    default=86400,
                ),
            ),
            zoom=max(
                3,
                min(
                    18,
                    _env_int("STATUS_SYNC_GEOCODE_ZOOM", data, "geocode", "zoom", default=12),
                ),
            ),
        ),
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file) or {}
    return data if isinstance(data, dict) else {}


def _from_data(data: dict[str, Any], section: str, key: str, default: Any) -> Any:
    section_data = data.get(section, {})
    if not isinstance(section_data, dict):
        return default
    return section_data.get(key, default)


def _env_str(env_name: str, data: dict[str, Any], section: str, key: str, default: str = "") -> str:
    env_value = os.getenv(env_name)
    if env_value is not None:
        return env_value
    value = _from_data(data, section, key, default)
    return str(value).strip()


def _route_path(data: dict[str, Any], section: str, key: str, default: str) -> str:
    value = _from_data(data, section, key, default)
    path = str(value).strip() or default
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def _env_int(env_name: str, data: dict[str, Any], section: str, key: str, default: int) -> int:
    value = os.getenv(env_name)
    if value is None:
        value = _from_data(data, section, key, default)
    return int(value)


def _env_float(
    env_name: str,
    data: dict[str, Any],
    section: str,
    key: str,
    default: float,
) -> float:
    value = os.getenv(env_name)
    if value is None:
        value = _from_data(data, section, key, default)
    return float(value)


def _env_bool(env_name: str, data: dict[str, Any], section: str, key: str, default: bool) -> bool:
    value = os.getenv(env_name)
    if value is None:
        value = _from_data(data, section, key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_list(
    env_name: str,
    data: dict[str, Any],
    section: str,
    key: str,
    default: list[str],
) -> list[str]:
    value: Any = os.getenv(env_name)
    if value is not None:
        return [item.strip() for item in value.split(",") if item.strip()]

    value = _from_data(data, section, key, default)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return default


def _str_dict(data: dict[str, Any], section: str, key: str) -> dict[str, str]:
    value = _from_data(data, section, key, {})
    if not isinstance(value, dict):
        return {}
    return {
        str(item_key).strip(): str(item_value).strip() for item_key, item_value in value.items()
    }


def _nullable_str_dict(data: dict[str, Any], section: str, key: str) -> dict[str, str | None]:
    value = _from_data(data, section, key, {})
    if not isinstance(value, dict):
        return {}
    return {
        str(item_key).strip(): None if item_value is None else str(item_value).strip()
        for item_key, item_value in value.items()
    }
