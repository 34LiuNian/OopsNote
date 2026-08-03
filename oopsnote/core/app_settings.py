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
            self._write(current)
            return current

    def _write(self, current: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f"{self.path.name}.{uuid4().hex}.tmp")
        try:
            temp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp.replace(self.path)
        finally:
            if temp.exists():
                temp.unlink()

    @staticmethod
    def _upsert_profile(current: dict[str, Any], profile: Any) -> None:
        from oopsnote.ai.providers import ProviderProfile

        profiles = [ProviderProfile.model_validate(item) for item in current.get("provider_profiles", [])]
        for existing in profiles:
            if existing.id == profile.id and existing.version > profile.version:
                raise ValueError("provider profile version cannot move backwards")
            if existing.id == profile.id and existing.version == profile.version and existing != profile:
                raise ValueError("provider profile changes require a new version")
        profiles = [item for item in profiles if item.id != profile.id]
        profiles.append(profile)
        current["provider_profiles"] = [item.model_dump(mode="json") for item in profiles]

    def provider_profiles(self) -> list[Any]:
        """Read the one authoritative non-secret provider profile collection."""
        from oopsnote.ai.providers import ProviderProfile

        profiles = self.get().get("provider_profiles", [])
        if not isinstance(profiles, list):
            raise StorageCorruptionError(self.path, ValueError("provider_profiles must be a list"))
        return [ProviderProfile.model_validate(item) for item in profiles]

    def upsert_provider_profile(self, profile: Any) -> Any:
        """Atomically replace one immutable profile version by id/version."""
        with self._lock:
            current = self.get()
            self._upsert_profile(current, profile)
            self._write(current)
            return profile

    def activate_provider_profile(self, profile: Any) -> Any:
        """Atomically persist one validated profile version and select it."""
        with self._lock:
            current = self.get()
            self._upsert_profile(current, profile)
            current["ai_provider_profile_id"] = profile.id
            self._write(current)
            return profile

    def activate_ocr_profile(self, profile: Any) -> Any:
        """Atomically persist one validated profile version and select it for OCR."""
        with self._lock:
            current = self.get()
            self._upsert_profile(current, profile)
            current["ocr_profile_id"] = profile.id
            self._write(current)
            return profile
