from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegistrationSettings:
    enabled: bool = False


class RegistrationSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "auth.json")
        self._lock = threading.Lock()

    def load(self) -> RegistrationSettings:
        with self._lock:
            if not self.path.exists():
                return RegistrationSettings(enabled=False)
            data = json.loads(self.path.read_text(encoding="utf-8"))
            enabled = bool(data.get("registration_enabled", False)) if isinstance(data, dict) else False
            return RegistrationSettings(enabled=enabled)

    def save(self, settings: RegistrationSettings) -> RegistrationSettings:
        with self._lock:
            payload = {"registration_enabled": bool(settings.enabled)}
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return settings
