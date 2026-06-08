# Status Sync API

[English Documentation Click Here](docs/README.md)

Status Sync API 是 Status Sync Android 的轻量后端。它只负责接收 Android 上传的状态 JSON、保存最新状态，并把 raw 字段清洗为博客状态卡片需要的结构化 JSON。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/upload_raw` | Android 上传原始状态 |
| `GET` | `/api/status/latest` | 博客读取清洗后的状态 |
| `GET` | `/healthz` | 健康检查 |

无状态时返回：

```json
{
  "online": false,
  "updated_at": null,
  "data": null
}
```

有状态时返回：

```json
{
  "online": true,
  "updated_at": "2026-06-07T15:30:00+08:00",
  "data": {
    "device_name": "示例手机",
    "battery_level": 86,
    "battery_charging": true,
    "wifi_connected": true,
    "wifi_ssid": "示例无线网络",
    "network_type": "4G | 5G",
    "current_app": "示例应用",
    "province": "示例省",
    "city": "示例市",
    "district": "示例区"
  }
}
```

## 数据处理

Android 上传字段来自 `status-sync-android`：

```json
{
  "model": "EXAMPLE_MODEL",
  "battery_raw": "dumpsys battery output",
  "wifi_raw": "Wi-Fi status output",
  "net_raw": "LTE,NR",
  "location_raw": "last location output",
  "current_app_package": "app.placeholder.demo",
  "current_app_name": "示例应用"
}
```

如果输入是接收日志格式，API 也会兼容读取其中的 `data` 对象：

```json
{
  "received_at": "2026-06-07T21:28:29.696091",
  "client_ip": "203.0.113.10",
  "data": {
    "model": "EXAMPLE_MODEL"
  }
}
```

API 处理规则：

- `model` 通过 `processing.device_aliases` 可选映射为展示名称，否则原样返回。
- `battery_raw` 解析为 `battery_level` 和 `battery_charging`。
- `wifi_raw` 解析为 `wifi_connected` 和 `wifi_ssid`。
- `net_raw` 通过 `processing.network_aliases` 转为 `5G`、`4G` 等展示值；多卡网络会按顺序输出多个值，例如 `LTE,NR` 输出 `4G | 5G`。
- `current_app` 直接使用 Android 上传的 `current_app_name`，不维护包名字典。
- `location_raw` 提取经纬度并调用公共反向地理编码 API，输出 `province/city/district`。
- `location_text`、`location`、`province/city/district` 也兼容直接上传。
- `status.private_values` 中的值会被视为主动隐藏，例如 Android 私密模式上传的 `none`。

展示延迟由 Android app 或前端策略控制，API 不再做延迟发布，只做数据处理。

## 存储与缓存

- API 只保存最新一次输入，不保存历史记录。
- 输入保存位置由 `storage.path` 控制，默认是 `data/status.json`。
- 保存文件包含 `id`、`received_at` 和清洗前的 `raw` 输入数据。
- 如果上传内容是外层接收日志格式，API 会取其中的 `data` 对象作为 `raw` 保存。
- `/api/status/latest` 的输出不会单独保存，而是在每次请求时由 `raw`、配置和地理编码结果即时生成。
- 反向地理编码结果有进程内缓存，缓存时间由 `geocode.cache_ttl_seconds` 控制，默认 24 小时。
- 反向地理编码失败后会记录日志，并在 `geocode.timeout_seconds * 2` 后重新查询；等待重试期间如有历史成功结果，会先返回历史地址。
- 地理编码缓存和失败重试状态不会写入文件或数据库，API 重启后会丢失。

## 配置

复制 YAML 配置文件并修改：

```powershell
Copy-Item config.example.yaml config.yaml
```

配置项说明：

| 配置项 | 说明 |
| --- | --- |
| `server.host` | 服务监听地址。Docker 内通常为 `0.0.0.0`。 |
| `server.port` | 服务监听端口，默认 `8000`。 |
| `auth.upload_token` | Android 上传状态时使用的 Bearer Token。 |
| `auth.require_upload_token` | 是否强制校验上传密钥。生产环境建议 `true`。 |
| `storage.path` | 最新状态 JSON 文件保存位置。 |
| `status.online_threshold_seconds` | 最新上报在多少秒内算在线。 |
| `status.private_values` | 视为主动隐藏的字段值，例如 `none`。 |
| `status.max_raw_value_length` | 单个 raw 字段最大保存字符数。 |
| `status.output_timezone` | `updated_at` 输出时区，例如 `+08:00` 或 `UTC`。 |
| `processing.device_aliases` | 设备型号展示别名。 |
| `processing.network_aliases` | 网络类型展示别名，例如 `NR: 5G`、`LTE: 4G`。 |
| `geocode.*` | 反向地理编码配置。默认使用 Nominatim reverse API。 |
| `cors.*` | 跨域访问配置。生产环境建议只允许博客域名。 |

环境变量可覆盖常用配置：

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

## 本地运行

需要 Python 3.11 或更高版本，以下命令以 3.11 为例。

Windows：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item config.example.yaml config.yaml
status-sync-api
```

macOS/Linux：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp config.example.yaml config.yaml
status-sync-api
```

默认监听 `http://localhost:8000`。

## Docker

```bash
cp config.example.yaml config.yaml
docker compose up -d --build
```

## 测试

```bash
ruff check .
pytest
```

## 相关项目

```text
Miafetta/status-sync-android
        |
        | 上传状态
        v
Miafetta/status-sync-api  <- 当前项目
        |
        | 输出清洗后的状态 JSON
        v
Miafetta/miafetta.github.io
```

- [Miafetta/status-sync-android](https://github.com/Miafetta/status-sync-android)：Android 状态采集与上传端。
- [Miafetta/status-sync-api](https://github.com/Miafetta/status-sync-api)：状态数据处理 API，当前项目。
- [Miafetta/miafetta.github.io](https://github.com/Miafetta/miafetta.github.io)：博客展示端。

## 许可证

状态同步 API 使用 GNU General Public License v3.0 开源许可证。详情请查看 [LICENSE](LICENSE)。
