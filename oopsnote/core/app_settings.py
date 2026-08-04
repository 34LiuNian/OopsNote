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
    def _upsert_channel(current: dict[str, Any], channel: Any) -> None:
        from oopsnote.ai.providers import ProviderChannel

        channels = [ProviderChannel.model_validate(item) for item in current.get("provider_channels", [])]
        for existing in channels:
            if existing.id == channel.id and existing.version > channel.version:
                raise ValueError("provider channel version cannot move backwards")
            if existing.id == channel.id and existing.version == channel.version and existing != channel:
                raise ValueError("provider channel changes require a new version")
        channels = [item for item in channels if item.id != channel.id]
        channels.append(channel)
        current["provider_channels"] = [item.model_dump(mode="json") for item in channels]

    @staticmethod
    def _policy_is_runnable(current: dict[str, Any]) -> bool:
        """Keep stored policy references valid when a channel catalogue changes."""
        from oopsnote.ai.providers import LangChainModelPolicy, ProviderChannel

        raw_policy = current.get("langchain_model_policy")
        if not isinstance(raw_policy, dict):
            return False
        try:
            policy = LangChainModelPolicy.model_validate(raw_policy)
            channels = {
                channel.id: channel
                for channel in (
                    ProviderChannel.model_validate(item)
                    for item in current.get("provider_channels", [])
                )
            }
        except ValueError:
            return False
        for stage, selection in (
            ("vision", policy.vision),
            ("agent", policy.agent),
            ("review", policy.review),
        ):
            channel = channels.get(selection.channel_id)
            if channel is None or not channel.enabled or not channel.credential_ref:
                return False
            try:
                model = channel.model(selection.model_id)
            except KeyError:
                return False
            if not model.enabled:
                return False
            if stage == "vision" and not model.capability.vision:
                return False
            if stage != "vision" and not model.capability.tool_calling:
                return False
        return True

    def provider_channels(self) -> list[Any]:
        """Read channels; legacy single-model profiles are intentionally excluded."""
        from oopsnote.ai.providers import ProviderChannel

        channels = self.get().get("provider_channels", [])
        if not isinstance(channels, list):
            raise StorageCorruptionError(self.path, ValueError("provider_channels must be a list"))
        return [ProviderChannel.model_validate(item) for item in channels]

    def upsert_provider_channel(self, channel: Any) -> Any:
        with self._lock:
            current = self.get()
            self._upsert_channel(current, channel)
            if "langchain_model_policy" in current and not self._policy_is_runnable(current):
                current.pop("langchain_model_policy", None)
            self._write(current)
            return channel

    def remove_provider_channel(self, channel_id: str) -> None:
        with self._lock:
            current = self.get()
            channels = current.get("provider_channels", [])
            remaining = [item for item in channels if isinstance(item, dict) and item.get("id") != channel_id]
            if len(remaining) == len(channels):
                raise KeyError(channel_id)
            current["provider_channels"] = remaining
            policy = current.get("langchain_model_policy")
            if isinstance(policy, dict) and any(
                isinstance(policy.get(stage), dict) and policy[stage].get("channel_id") == channel_id
                for stage in ("vision", "agent", "review")
            ):
                current.pop("langchain_model_policy", None)
            self._write(current)

    def langchain_model_policy(self) -> Any | None:
        from oopsnote.ai.providers import LangChainModelPolicy

        value = self.get().get("langchain_model_policy")
        return LangChainModelPolicy.model_validate(value) if isinstance(value, dict) else None

    def set_langchain_model_policy(self, policy: Any) -> Any:
        with self._lock:
            current = self.get()
            current["langchain_model_policy"] = policy.model_dump(mode="json")
            if not self._policy_is_runnable(current):
                raise ValueError("LangChain policy references an unavailable channel or model")
            self._write(current)
            return policy

    def retire_legacy_provider_secrets(self) -> list[str]:
        """Remove retired profile-shaped settings and return their opaque refs."""
        with self._lock:
            current = self.get()
            raw = current.get("provider_profiles", [])
            if not isinstance(raw, list) or not raw:
                return []
            references = [
                item.get("credential_ref")
                for item in raw
                if isinstance(item, dict) and isinstance(item.get("credential_ref"), str)
            ]
            current.pop("provider_profiles", None)
            current.pop("provider_validation_results", None)
            current.pop("ai_provider_profile_id", None)
            current.pop("ocr_profile_id", None)
            self._write(current)
            return references
