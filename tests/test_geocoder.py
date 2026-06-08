from __future__ import annotations

import logging

from status_sync_api.config import GeocodeConfig
from status_sync_api.geocoder import LocationAddress, ReverseGeocoder, format_address


class SequenceGeocoder(ReverseGeocoder):
    def __init__(self, results: list[LocationAddress | None]) -> None:
        super().__init__(
            GeocodeConfig(
                timeout_seconds=2.0,
                cache_ttl_seconds=1,
            )
        )
        self.results = results
        self.calls = 0

    def _fetch_address(self, latitude: float, longitude: float) -> LocationAddress | None:
        self.calls += 1
        return self.results.pop(0)


def test_china_address_is_reduced_to_district_level() -> None:
    payload = {
        "address": {
            "country_code": "cn",
            "province": "陕西省",
            "city": "西安市",
            "city_district": "雁塔区",
            "road": "科技路",
            "house_number": "1号",
        }
    }

    assert format_address(payload) == LocationAddress(
        province="陕西省",
        city="西安市",
        district="雁塔区",
    )


def test_china_address_uses_display_name_when_nominatim_city_is_district() -> None:
    payload = {
        "addresstype": "suburb",
        "display_name": "太乙路街道, 碑林区, 西安市, 陕西省, 710049, 中国",
        "address": {
            "country_code": "cn",
            "suburb": "太乙路街道",
            "city": "碑林区",
            "state": "陕西省",
        },
    }

    assert format_address(payload) == LocationAddress(
        province="陕西省",
        city="西安市",
        district="碑林区",
    )


def test_reverse_geocoder_uses_stale_address_until_failure_retry_window(
    monkeypatch,
    caplog,
) -> None:
    now = 0.0
    geocoder = SequenceGeocoder(
        [
            LocationAddress(province="示例省", city="示例市", district="示例区"),
            None,
            LocationAddress(province="新示例省", city="新示例市", district="新示例区"),
        ]
    )

    monkeypatch.setattr("status_sync_api.geocoder.time.time", lambda: now)
    caplog.set_level(logging.WARNING)

    assert geocoder.reverse(34.0, 108.0) == LocationAddress(
        province="示例省",
        city="示例市",
        district="示例区",
    )
    assert geocoder.calls == 1

    now = 2.0
    assert geocoder.reverse(34.0, 108.0) == LocationAddress(
        province="示例省",
        city="示例市",
        district="示例区",
    )
    assert geocoder.calls == 2
    assert "retrying in 4.0 seconds" in caplog.text

    now = 5.0
    assert geocoder.reverse(34.0, 108.0) == LocationAddress(
        province="示例省",
        city="示例市",
        district="示例区",
    )
    assert geocoder.calls == 2

    now = 7.0
    assert geocoder.reverse(34.0, 108.0) == LocationAddress(
        province="新示例省",
        city="新示例市",
        district="新示例区",
    )
    assert geocoder.calls == 3


def test_reverse_geocoder_returns_none_during_failure_retry_window_without_history(
    monkeypatch,
) -> None:
    now = 0.0
    geocoder = SequenceGeocoder([None])

    monkeypatch.setattr("status_sync_api.geocoder.time.time", lambda: now)

    assert geocoder.reverse(34.0, 108.0) is None
    assert geocoder.calls == 1

    now = 3.0
    assert geocoder.reverse(34.0, 108.0) is None
    assert geocoder.calls == 1
