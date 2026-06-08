# Status Sync API

[简体中文](../README.md)

Status Sync API is a lightweight backend for Status Sync Android. It receives status JSON uploaded by Android, stores the latest status, and cleans raw fields into structured JSON for the blog status card.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/upload_raw` | Android raw status upload |
| `GET` | `/api/status/latest` | Cleaned status for the blog |
| `GET` | `/healthz` | Health check |

No status:

```json
{
  "online": false,
  "updated_at": null,
  "data": null
}
```

Latest status:

```json
{
  "online": true,
  "updated_at": "2026-06-07T15:30:00+08:00",
  "data": {
    "device_name": "Example Phone",
    "battery_level": 86,
    "battery_charging": true,
    "wifi_connected": true,
    "wifi_ssid": "Example WiFi",
    "network_type": "4G | 5G",
    "current_app": "Example App",
    "province": "Example Province",
    "city": "Example City",
    "district": "Example District"
  }
}
```

## Processing

Android upload fields come from `status-sync-android`:

```json
{
  "model": "EXAMPLE_MODEL",
  "battery_raw": "dumpsys battery output",
  "wifi_raw": "Wi-Fi status output",
  "net_raw": "LTE,NR",
  "location_raw": "last location output",
  "current_app_package": "app.placeholder.demo",
  "current_app_name": "Example App"
}
```

If the input is a receiver log object, the API also reads the nested `data` object:

```json
{
  "received_at": "2026-06-07T21:28:29.696091",
  "client_ip": "203.0.113.10",
  "data": {
    "model": "EXAMPLE_MODEL"
  }
}
```

Processing rules:

- `model` can be mapped through `processing.device_aliases`; otherwise it is returned as-is.
- `battery_raw` is parsed into `battery_level` and `battery_charging`.
- `wifi_raw` is parsed into `wifi_connected` and `wifi_ssid`.
- `net_raw` is normalized through `processing.network_aliases`, such as `5G` or `4G`. Multi-SIM network values are kept in order, for example `LTE,NR` becomes `4G | 5G`.
- `current_app` uses the uploaded `current_app_name` directly. No package-name dictionary is maintained.
- `location_raw` extracts coordinates and calls a public reverse geocoding API, then outputs `province/city/district`.
- Direct `location_text`, `location`, and `province/city/district` uploads are also accepted.
- Values listed in `status.private_values` are treated as intentionally hidden, such as `none` from Android private mode.

Display delay is controlled by the Android app or frontend policy. The API no longer delays publishing and only processes data.

## Storage And Cache

- The API stores only the latest input and does not keep history.
- The input storage path is controlled by `storage.path`, defaulting to `data/status.json`.
- The stored file contains `id`, `received_at`, and the unprocessed `raw` input data.
- If the upload is a receiver log object, the nested `data` object is stored as `raw`.
- `/api/status/latest` output is not stored separately. It is generated from `raw`, config, and geocoding results on each request.
- Reverse geocoding results are cached in memory. The cache TTL is controlled by `geocode.cache_ttl_seconds`, defaulting to 24 hours.
- Reverse geocoding failures are logged and retried after `geocode.timeout_seconds * 2`. During the retry wait, a previous successful address is returned when available.
- The geocoding cache and failure retry state are not written to a file or database and are lost when the API restarts.

## Configuration

Copy and edit the YAML config:

```powershell
Copy-Item config.example.yaml config.yaml
```

Configuration items:

| Key | Description |
| --- | --- |
| `server.host` | Service listen host. Usually `0.0.0.0` inside Docker. |
| `server.port` | Service listen port. Default is `8000`. |
| `auth.upload_token` | Bearer Token used by Android status uploads. |
| `auth.require_upload_token` | Whether upload token validation is required. Recommended `true` for production. |
| `storage.path` | Latest status JSON storage path. |
| `status.online_threshold_seconds` | How many seconds after the latest upload should still count as online. |
| `status.private_values` | Field values treated as intentionally hidden, such as `none`. |
| `status.max_raw_value_length` | Maximum saved length for a single raw field. |
| `status.output_timezone` | Timezone for `updated_at`, such as `+08:00` or `UTC`. |
| `processing.device_aliases` | Display aliases for device models. |
| `processing.network_aliases` | Display aliases for network types, such as `NR: 5G` and `LTE: 4G`. |
| `geocode.*` | Reverse geocoding configuration. Default uses the Nominatim reverse API. |
| `cors.*` | CORS configuration. For production, allow only the blog domain. |

Common environment overrides:

```text
STATUS_SYNC_CONFIG
STATUS_SYNC_UPLOAD_TOKEN
STATUS_SYNC_CORS_ORIGINS
STATUS_SYNC_STORAGE_PATH
STATUS_SYNC_PORT
STATUS_SYNC_OUTPUT_TIMEZONE
STATUS_SYNC_GEOCODE_ENABLED
STATUS_SYNC_GEOCODE_USER_AGENT
```

## Run Locally

Python 3.11 or later is supported. The commands below use 3.11 as the example.

Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item config.example.yaml config.yaml
status-sync-api
```

macOS/Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp config.example.yaml config.yaml
status-sync-api
```

The default address is `http://localhost:8000`.

## Docker

```bash
cp config.example.yaml config.yaml
docker compose up -d --build
```

## Test

```bash
ruff check .
pytest
```

## Related Projects

```text
Miafetta/status-sync-android
        |
        | Uploads status
        v
Miafetta/status-sync-api  <- Current project
        |
        | Outputs cleaned status JSON
        v
Miafetta/miafetta.github.io
```

- [Miafetta/status-sync-android](https://github.com/Miafetta/status-sync-android): Android status collection and upload client.
- [Miafetta/status-sync-api](https://github.com/Miafetta/status-sync-api): Status data processing API, the current project.
- [Miafetta/miafetta.github.io](https://github.com/Miafetta/miafetta.github.io): Blog display frontend.

## License

Status Sync API is licensed under the GNU General Public License v3.0. See [LICENSE](../LICENSE) for details.
