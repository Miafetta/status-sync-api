from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from status_sync_api.geocoder import Geocoder, LocationAddress
from status_sync_api.models import PhoneStatusData

BATTERY_LEVEL_RE = re.compile(r"^\s*level:\s*(\d{1,3})\s*$", re.IGNORECASE | re.MULTILINE)
BATTERY_POWERED_RE = re.compile(
    r"^\s*(?:AC|USB|Wireless|Dock)\s+powered:\s*(true|false)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
BATTERY_STATUS_RE = re.compile(r"^\s*status:\s*(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
WIFI_CONNECTED_RE = re.compile(r"Wifi\s+is\s+connected", re.IGNORECASE)
WIFI_SSID_RE = re.compile(r'\bSSID:\s*"?([^",\n]+)"?', re.IGNORECASE)
LOCATION_COORD_PAIR_RE = re.compile(
    r"(?P<lat>[+-]?\d{1,2}(?:\.\d+)?)\s*,\s*(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)"
)
LOCATION_LAT_LON_RE = re.compile(
    r"(?:lat(?:itude)?)[=: ]+(?P<lat>[+-]?\d{1,2}(?:\.\d+)?).*?"
    r"(?:lon(?:gitude)?|lng)[=: ]+(?P<lon>[+-]?\d{1,3}(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)
CHINA_LOCATION_RE = re.compile(
    r"^(?P<province>.+?(?:省|自治区|特别行政区|市))?"
    r"(?P<city>.+?(?:市|自治州|地区|盟))?"
    r"(?P<district>.+?(?:区|县|市|旗))?$"
)


def normalize_status(
    raw: Mapping[str, Any],
    private_values: list[str],
    device_aliases: dict[str, str],
    network_aliases: dict[str, str | None],
    geocoder: Geocoder | None,
) -> PhoneStatusData | None:
    if _is_private_payload(raw, private_values):
        return None

    battery_raw = _as_text(raw.get("battery_raw"))
    wifi_raw = _as_text(raw.get("wifi_raw"))
    location = _parse_location(raw, private_values, geocoder)

    return PhoneStatusData(
        device_name=_parse_device_name(raw, private_values, device_aliases),
        battery_level=_parse_battery_level(battery_raw),
        battery_charging=_parse_battery_charging(battery_raw),
        wifi_connected=_parse_wifi_connected(wifi_raw),
        wifi_ssid=_parse_wifi_ssid(wifi_raw, private_values),
        network_type=_parse_network_type(raw.get("net_raw"), private_values, network_aliases),
        current_app=_clean_value(raw.get("current_app_name"), private_values),
        province=location.province if location else None,
        city=location.city if location else None,
        district=location.district if location else None,
    )


def trim_raw_payload(raw: Mapping[str, Any], max_length: int) -> dict[str, Any]:
    trimmed: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, str) and len(value) > max_length:
            trimmed[key] = value[:max_length] + "\n...[truncated]"
        else:
            trimmed[key] = value
    return trimmed


def _is_private_payload(raw: Mapping[str, Any], private_values: list[str]) -> bool:
    values = [_clean_value(value, []) for value in raw.values()]
    visible_values = [value for value in values if value]
    if not visible_values:
        return False

    private_set = {value.lower() for value in private_values}
    return all(value.lower() in private_set for value in visible_values)


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _clean_value(value: Any, private_values: list[str]) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {item.lower() for item in private_values}:
        return None
    return text


def _parse_device_name(
    raw: Mapping[str, Any],
    private_values: list[str],
    device_aliases: dict[str, str],
) -> str | None:
    model = _clean_value(raw.get("model"), private_values)
    if not model:
        return None
    return device_aliases.get(model, model)


def _parse_battery_level(raw: str) -> int | None:
    match = BATTERY_LEVEL_RE.search(raw)
    if not match:
        return None
    return max(0, min(100, int(match.group(1))))


def _parse_battery_charging(raw: str) -> bool | None:
    powered_values = [match.lower() == "true" for match in BATTERY_POWERED_RE.findall(raw)]
    if any(powered_values):
        return True

    status_match = BATTERY_STATUS_RE.search(raw)
    if status_match:
        return status_match.group(1) in {"2", "5"}

    return False if powered_values else None


def _parse_wifi_connected(raw: str) -> bool | None:
    if not raw:
        return None
    return bool(WIFI_CONNECTED_RE.search(raw))


def _parse_wifi_ssid(raw: str, private_values: list[str]) -> str | None:
    match = WIFI_SSID_RE.search(raw)
    if not match:
        return None
    return _clean_value(match.group(1).strip("<>"), private_values)


def _parse_network_type(
    value: Any,
    private_values: list[str],
    network_aliases: dict[str, str | None],
) -> str | None:
    raw = _clean_value(value, private_values)
    if not raw:
        return None

    for item in re.split(r"[,/|\s]+", raw):
        item = item.strip()
        if not item:
            continue
        mapped = network_aliases.get(item, item)
        if mapped:
            return mapped

    return None


def _parse_location(
    raw: Mapping[str, Any],
    private_values: list[str],
    geocoder: Geocoder | None,
) -> LocationAddress | None:
    direct = _location_from_direct_fields(raw, private_values)
    if direct:
        return direct

    location_text = _clean_value(raw.get("location_text"), private_values)
    if location_text:
        return _location_from_text(location_text)

    location_value = raw.get("location")
    if isinstance(location_value, Mapping):
        return _location_from_mapping(location_value, private_values)
    if isinstance(location_value, str):
        return _location_from_text(location_value)

    location_raw = _clean_value(raw.get("location_raw"), private_values)
    if not location_raw:
        return None

    coordinates = _extract_coordinates(location_raw)
    if coordinates and geocoder:
        latitude, longitude = coordinates
        return geocoder.reverse(latitude, longitude)

    return None


def _location_from_direct_fields(
    raw: Mapping[str, Any],
    private_values: list[str],
) -> LocationAddress | None:
    return _empty_location_to_none(
        LocationAddress(
            province=_clean_value(raw.get("province"), private_values),
            city=_clean_value(raw.get("city"), private_values),
            district=_clean_value(raw.get("district"), private_values),
        )
    )


def _location_from_mapping(
    raw: Mapping[str, Any],
    private_values: list[str],
) -> LocationAddress | None:
    return _empty_location_to_none(
        LocationAddress(
            province=_clean_value(raw.get("province"), private_values),
            city=_clean_value(raw.get("city"), private_values),
            district=_clean_value(raw.get("district"), private_values),
        )
    )


def _location_from_text(value: str) -> LocationAddress | None:
    text = value.strip()
    if not text:
        return None

    match = CHINA_LOCATION_RE.match(text)
    if not match:
        return LocationAddress(district=text)

    return _empty_location_to_none(
        LocationAddress(
            province=match.group("province"),
            city=match.group("city"),
            district=match.group("district"),
        )
    )


def _empty_location_to_none(location: LocationAddress) -> LocationAddress | None:
    if location.province or location.city or location.district:
        return location
    return None


def _extract_coordinates(raw: str) -> tuple[float, float] | None:
    for pattern in (LOCATION_LAT_LON_RE, LOCATION_COORD_PAIR_RE):
        match = pattern.search(raw)
        if not match:
            continue

        latitude = float(match.group("lat"))
        longitude = float(match.group("lon"))
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return latitude, longitude
    return None
