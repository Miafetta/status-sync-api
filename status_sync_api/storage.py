from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import Lock

from pydantic import TypeAdapter

from status_sync_api.models import StatusRecord


class JsonStatusStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._record_adapter = TypeAdapter(StatusRecord)
        self._legacy_records_adapter = TypeAdapter(list[StatusRecord])
        self._lock = Lock()

    def save(self, record: StatusRecord) -> None:
        with self._lock:
            self._write_record(record)

    def latest(self) -> StatusRecord | None:
        if not self.path.exists():
            return None

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return self._read_record(data)
        except (OSError, ValueError):
            return None

    def _read_record(self, data: object) -> StatusRecord | None:
        if not isinstance(data, dict):
            return None

        if "record" in data:
            return self._record_adapter.validate_python(data["record"])

        # Backward-compatible read for older storage files that kept history.
        if "records" in data:
            records = self._legacy_records_adapter.validate_python(data["records"])
            return records[-1] if records else None

        return self._record_adapter.validate_python(data)

    def _write_record(self, record: StatusRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"record": record.model_dump(mode="json")}

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        ) as temp_file:
            json.dump(payload, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_name = temp_file.name

        os.replace(temp_name, self.path)
