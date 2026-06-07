from __future__ import annotations

from status_sync_api.geocoder import LocationAddress, format_address


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
