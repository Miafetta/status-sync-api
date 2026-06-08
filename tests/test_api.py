from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from status_sync_api.app import create_app
from status_sync_api.config import (
    AppConfig,
    AuthConfig,
    GeocodeConfig,
    ProcessingConfig,
    StatusConfig,
    StorageConfig,
)
from status_sync_api.geocoder import LocationAddress


class FakeGeocoder:
    def reverse(self, latitude: float, longitude: float) -> LocationAddress | None:
        assert round(latitude, 6) == 34.246341
        assert round(longitude, 6) == 108.977993
        return LocationAddress(province="陕西省", city="西安市", district="雁塔区")


def make_client(
    tmp_path: Path,
    *,
    geocoder: object | None = None,
    processing: ProcessingConfig | None = None,
    status: StatusConfig | None = None,
) -> TestClient:
    config = AppConfig(
        auth=AuthConfig(upload_token="secret", require_upload_token=True),
        storage=StorageConfig(path=tmp_path / "status.json"),
        status=status or StatusConfig(),
        processing=processing or ProcessingConfig(),
        geocode=GeocodeConfig(enabled=False),
    )
    app = create_app(config)
    if geocoder:
        app.state.geocoder = geocoder
    return TestClient(app)


def test_empty_latest_status(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.get("/api/status/latest")

    assert response.status_code == 200
    assert response.json() == {"online": False, "updated_at": None, "data": None}


def test_upload_requires_bearer_token(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/api/upload_raw", json={"model": "Pixel"})

    assert response.status_code == 401


def test_upload_and_latest_status_matches_blog_shape(tmp_path: Path) -> None:
    client = make_client(tmp_path, geocoder=FakeGeocoder())
    payload = {
        "model": "24129PN74C",
        "battery_raw": (
            "Current Battery Service state:\n"
            "  AC powered: false\n"
            "  USB powered: false\n"
            "  Wireless powered: false\n"
            "  status: 3\n"
            "  level: 66"
        ),
        "wifi_raw": 'Wifi is connected to "Himouto!"\nWifiInfo: SSID: "Himouto!", RSSI: -34',
        "net_raw": "LTE,Unknown",
        "location_raw": (
            "last location=Location[network 34.246341,108.977993 hAcc=30.0]\nenabled=true"
        ),
        "current_app_package": "com.miafetta.statussync",
        "current_app_name": "状态同步",
    }

    upload_response = client.post(
        "/api/upload_raw",
        headers={"Authorization": "Bearer secret"},
        json=payload,
    )
    latest_response = client.get("/api/status/latest")

    assert upload_response.status_code == 200
    latest = latest_response.json()
    assert latest["online"] is True
    assert latest["updated_at"].endswith("+08:00")
    assert latest["data"] == {
        "device_name": "24129PN74C",
        "battery_level": 66,
        "battery_charging": False,
        "wifi_connected": True,
        "wifi_ssid": "Himouto!",
        "network_type": "4G",
        "current_app": "状态同步",
        "province": "陕西省",
        "city": "西安市",
        "district": "雁塔区",
    }


def test_network_type_keeps_multiple_active_radio_types(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/upload_raw",
        headers={"Authorization": "Bearer secret"},
        json={"net_raw": "LTE,NR_SA,Unknown,lte"},
    )
    latest_response = client.get("/api/status/latest")

    assert response.status_code == 200
    assert latest_response.json()["data"]["network_type"] == "4G | 5G"


def test_upload_accepts_receiver_log_wrapped_data(tmp_path: Path) -> None:
    client = make_client(tmp_path, geocoder=FakeGeocoder())

    response = client.post(
        "/api/upload_raw",
        headers={"Authorization": "Bearer secret"},
        json={
            "received_at": "2026-06-07T21:28:29.696091",
            "client_ip": "192.168.0.12",
            "headers": {"user_agent": "okhttp/4.11.0"},
            "data": {
                "model": "24129PN74C",
                "battery_raw": "status: 3\nlevel: 66",
                "wifi_raw": 'Wifi is connected to "Himouto!"\nWifiInfo: SSID: "Himouto!"',
                "net_raw": "LTE,Unknown",
                "location_raw": "last location=Location[network 34.246341,108.977993 hAcc=30.0]",
                "current_app_name": "状态同步",
            },
        },
    )
    latest_response = client.get("/api/status/latest")

    assert response.status_code == 200
    assert latest_response.json()["data"]["current_app"] == "状态同步"
    assert latest_response.json()["data"]["province"] == "陕西省"


def test_uploaded_location_text_is_split_into_fields(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    client.post(
        "/api/upload_raw",
        headers={"Authorization": "Bearer secret"},
        json={"location_text": "陕西省西安市雁塔区"},
    )
    latest_response = client.get("/api/status/latest")

    assert latest_response.json()["data"] == {
        "device_name": None,
        "battery_level": None,
        "battery_charging": None,
        "wifi_connected": None,
        "wifi_ssid": None,
        "network_type": None,
        "current_app": None,
        "province": "陕西省",
        "city": "西安市",
        "district": "雁塔区",
    }


def test_private_payload_hides_public_data(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/upload_raw",
        headers={"Authorization": "Bearer secret"},
        json={
            "model": "none",
            "battery_raw": "none",
            "wifi_raw": "none",
            "net_raw": "none",
            "location_raw": "none",
            "current_app_name": "none",
        },
    )
    latest_response = client.get("/api/status/latest")

    assert response.status_code == 200
    assert latest_response.json()["data"] is None
