from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from status_sync_api.config import GeocodeConfig


class Geocoder(Protocol):
    def reverse(self, latitude: float, longitude: float) -> LocationAddress | None: ...


@dataclass(frozen=True)
class LocationAddress:
    province: str | None = None
    city: str | None = None
    district: str | None = None


@dataclass(frozen=True)
class CachedAddress:
    value: LocationAddress
    expires_at: float


class ReverseGeocoder:
    def __init__(self, config: GeocodeConfig) -> None:
        self.config = config
        self._cache: dict[str, CachedAddress] = {}

    def reverse(self, latitude: float, longitude: float) -> LocationAddress | None:
        if not self.config.enabled:
            return None

        cache_key = f"{latitude:.4f},{longitude:.4f}"
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached and cached.expires_at > now:
            return cached.value

        address = self._fetch_address(latitude, longitude)
        if address:
            self._cache[cache_key] = CachedAddress(
                value=address,
                expires_at=now + self.config.cache_ttl_seconds,
            )
        return address

    def _fetch_address(self, latitude: float, longitude: float) -> LocationAddress | None:
        headers = {"User-Agent": self.config.user_agent}
        params = {
            "format": "jsonv2",
            "lat": latitude,
            "lon": longitude,
            "zoom": self.config.zoom,
            "addressdetails": 1,
            "accept-language": self.config.language,
        }

        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                response = client.get(self.config.endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        if not isinstance(payload, dict):
            return None
        return format_address(payload)


def format_address(payload: dict[str, Any]) -> LocationAddress | None:
    address = payload.get("address")
    if not isinstance(address, dict):
        return None

    country_code = _clean_text(address.get("country_code"))
    if country_code and country_code.lower() == "cn":
        return _format_china_address(payload, address)

    province = _first_text(address, "province", "state", "region")
    city = _first_text(address, "city", "town", "municipality", "county")
    district = _first_text(address, "city_district", "district", "county", "suburb")

    return _empty_to_none(
        LocationAddress(
            province=province,
            city=city,
            district=district,
        )
    )


def _format_china_address(
    payload: dict[str, Any], address: dict[str, Any]
) -> LocationAddress | None:
    province = _first_text(address, "province", "state", "region")
    city = _first_text(address, "city", "town", "municipality", "state_district")
    district = _first_text(address, "city_district", "district", "county")

    if city and _is_china_district(city) and not district:
        district = city
        city = None

    display_parts = _display_name_parts(payload)
    province = province or _first_part(display_parts, _is_china_province)
    city = city or _first_part(display_parts, _is_china_city)
    district = district or _first_part(display_parts, _is_china_district)

    if city and district and city == district:
        city = None

    return _empty_to_none(
        LocationAddress(
            province=province,
            city=city,
            district=district,
        )
    )


def _first_text(address: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        text = _clean_text(address.get(key))
        if text:
            return text
    return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _display_name_parts(payload: dict[str, Any]) -> list[str]:
    display_name = _clean_text(payload.get("display_name"))
    if not display_name:
        return []
    return [part.strip() for part in display_name.replace("，", ",").split(",") if part.strip()]


def _first_part(parts: list[str], predicate: Callable[[str], bool]) -> str | None:
    for part in parts:
        if predicate(part):
            return part
    return None


def _is_china_province(value: str) -> bool:
    return value.endswith(("省", "自治区", "特别行政区")) or value in {
        "北京市",
        "天津市",
        "上海市",
        "重庆市",
    }


def _is_china_city(value: str) -> bool:
    return value.endswith(("市", "自治州", "地区", "盟")) and not _is_china_province(value)


def _is_china_district(value: str) -> bool:
    return value.endswith(("区", "县", "旗"))


def _empty_to_none(address: LocationAddress) -> LocationAddress | None:
    if address.province or address.city or address.district:
        return address
    return None
