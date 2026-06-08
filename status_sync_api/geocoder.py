from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from status_sync_api.config import GeocodeConfig

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class FailedLookup:
    retry_after: float


class ReverseGeocoder:
    def __init__(self, config: GeocodeConfig) -> None:
        self.config = config
        self._cache: dict[str, CachedAddress] = {}
        self._failures: dict[str, FailedLookup] = {}

    def reverse(self, latitude: float, longitude: float) -> LocationAddress | None:
        if not self.config.enabled:
            logger.debug("Reverse geocoding is disabled.")
            return None

        cache_key = f"{latitude:.4f},{longitude:.4f}"
        cached = self._cache.get(cache_key)
        now = time.time()
        if cached and cached.expires_at > now:
            return cached.value

        failed = self._failures.get(cache_key)
        if failed and failed.retry_after > now:
            logger.debug(
                "Skipping reverse geocoding for %.5f,%.5f until retry window opens.",
                latitude,
                longitude,
            )
            return cached.value if cached else None

        address = self._fetch_address(latitude, longitude)
        if address:
            self._cache[cache_key] = CachedAddress(
                value=address,
                expires_at=now + self.config.cache_ttl_seconds,
            )
            self._failures.pop(cache_key, None)
            return address

        retry_seconds = self.config.timeout_seconds * 2
        self._failures[cache_key] = FailedLookup(retry_after=now + retry_seconds)
        logger.warning(
            "Reverse geocoding failed for %.5f,%.5f; retrying in %.1f seconds.",
            latitude,
            longitude,
            retry_seconds,
        )
        if cached:
            logger.debug(
                "Using stale reverse geocoding cache for %.5f,%.5f.",
                latitude,
                longitude,
            )
            return cached.value
        return None

    def _fetch_address(self, latitude: float, longitude: float) -> LocationAddress | None:
        if self.config.provider == "amap":
            return self._fetch_amap_address(latitude, longitude)
        if self.config.provider == "nominatim":
            return self._fetch_nominatim_address(latitude, longitude)

        logger.warning("Unsupported reverse geocoding provider: %s", self.config.provider)
        return None

    def _fetch_amap_address(self, latitude: float, longitude: float) -> LocationAddress | None:
        if not self.config.api_key:
            logger.warning("Amap reverse geocoding key is not configured.")
            return None

        params = {
            "key": self.config.api_key,
            "location": f"{longitude:.6f},{latitude:.6f}",
            "extensions": "base",
            "output": "JSON",
        }

        payload = self._request_json(latitude, longitude, params)
        if not payload:
            return None

        address = format_amap_address(payload)
        if not address:
            logger.warning(
                "Amap reverse geocoding response did not include a usable address for %.5f,%.5f.",
                latitude,
                longitude,
            )
        return address

    def _fetch_nominatim_address(self, latitude: float, longitude: float) -> LocationAddress | None:
        headers = {"User-Agent": self.config.user_agent}
        params = {
            "format": "jsonv2",
            "lat": latitude,
            "lon": longitude,
            "zoom": self.config.zoom,
            "addressdetails": 1,
            "accept-language": self.config.language,
        }

        payload = self._request_json(latitude, longitude, params, headers)
        if not payload:
            return None

        address = format_nominatim_address(payload)
        if not address:
            logger.warning(
                "Nominatim reverse geocoding response did not include a usable address "
                "for %.5f,%.5f.",
                latitude,
                longitude,
            )
        return address

    def _request_json(
        self,
        latitude: float,
        longitude: float,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                response = client.get(self.config.endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            logger.warning(
                "Reverse geocoding request failed for %.5f,%.5f: %s",
                latitude,
                longitude,
                exc,
            )
            return None
        except ValueError as exc:
            logger.warning(
                "Reverse geocoding response was invalid for %.5f,%.5f: %s",
                latitude,
                longitude,
                exc,
            )
            return None

        if not isinstance(payload, dict):
            logger.warning(
                "Reverse geocoding response was not an object for %.5f,%.5f.",
                latitude,
                longitude,
            )
            return None
        return payload


def format_amap_address(payload: dict[str, Any]) -> LocationAddress | None:
    if str(payload.get("status", "")).strip() != "1":
        logger.warning(
            "Amap reverse geocoding failed: %s",
            _clean_text(payload.get("info")) or "unknown error",
        )
        return None

    regeocode = payload.get("regeocode")
    if not isinstance(regeocode, dict):
        return None

    component = regeocode.get("addressComponent")
    if not isinstance(component, dict):
        return None

    province = _clean_amap_component(component.get("province"))
    city = _clean_amap_component(component.get("city"))
    district = _clean_amap_component(component.get("district"))

    if not city and province in {"北京市", "天津市", "上海市", "重庆市"}:
        city = province

    return _empty_to_none(
        LocationAddress(
            province=province,
            city=city,
            district=district,
        )
    )


def format_address(payload: dict[str, Any]) -> LocationAddress | None:
    return format_nominatim_address(payload)


def format_nominatim_address(payload: dict[str, Any]) -> LocationAddress | None:
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


def _clean_amap_component(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = _clean_text(item)
            if text:
                return text
        return None
    if isinstance(value, dict):
        return None
    return _clean_text(value)


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
