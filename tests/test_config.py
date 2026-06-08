from __future__ import annotations

from status_sync_api.config import load_config


def test_load_yaml_config(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
server:
  host: "127.0.0.1"
  port: 9000
auth:
  upload_token: "secret"
storage:
  path: "tmp/status.json"
routes:
  upload: "custom-upload"
  status: "/custom-status"
  health: "/custom-health"
status:
  output_timezone: "+08:00"
processing:
  device_aliases:
    "24129PN74C": "Xiaomi 15"
  network_aliases:
    LTE: "4G"
geocode:
  enabled: false
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.server.host == "127.0.0.1"
    assert config.server.port == 9000
    assert config.auth.upload_token == "secret"
    assert config.routes.upload == "/custom-upload"
    assert config.routes.status == "/custom-status"
    assert config.routes.health == "/custom-health"
    assert config.status.output_timezone == "+08:00"
    assert config.processing.device_aliases["24129PN74C"] == "Xiaomi 15"
    assert config.processing.network_aliases["LTE"] == "4G"
    assert config.geocode.enabled is False
