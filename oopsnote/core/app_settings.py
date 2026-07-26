"""Persistent store for user-editable application settings."""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from .store import StorageCorruptionError

class AppSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def get(self) -> dict[str, Any]:
        with self._lock:
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return {}
            except (OSError, json.JSONDecodeError) as error:
                raise StorageCorruptionError(self.path, error) from error
            return value if isinstance(value, dict) else {}

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            current = self.get()
            current.update(values)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_name(f"{self.path.name}.{uuid4().hex}.tmp")
            try:
                temp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                temp.replace(self.path)
            finally:
                if temp.exists():
                    temp.unlink()
            return current
