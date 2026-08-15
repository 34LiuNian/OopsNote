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
            temp.write_text(
                json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            temp.replace(self.path)
        finally:
            if temp.exists():
                temp.unlink()

    @staticmethod
    def _upsert_channel(current: dict[str, Any], channel: Any) -> None:
        from oopsnote.ai.providers import ProviderChannel

        channels = [
            ProviderChannel.model_validate(item) for item in current.get("provider_channels", [])
        ]
        for existing in channels:
            if existing.id == channel.id and existing.version > channel.version:
                raise ValueError("provider channel version cannot move backwards")
            if (
                existing.id == channel.id
                and existing.version == channel.version
                and existing != channel
            ):
                raise ValueError("provider channel changes require a new version")
        existing_index = next(
            (index for index, item in enumerate(channels) if item.id == channel.id), None
        )
        if existing_index is None:
            channels.append(channel)
        else:
            channels[existing_index] = channel
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
            ("diagram", policy.diagram),
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
            if stage in {"vision", "diagram"} and not model.capability.vision:
                return False
            if stage in {"agent", "review"} and not model.capability.tool_calling:
                return False
        return True

    def provider_channels(self) -> list[Any]:
        """Read the configured provider channels."""
        from oopsnote.ai.providers import ProviderChannel

        channels = self.get().get("provider_channels", [])
        if not isinstance(channels, list):
            raise StorageCorruptionError(self.path, ValueError("provider_channels must be a list"))
        return [ProviderChannel.model_validate(item) for item in channels]

    def upsert_provider_channel(self, channel: Any) -> Any:
        with self._lock:
            current = self.get()
            self._upsert_channel(current, channel)
            self._write(current)
            return channel

    def remove_provider_channel(self, channel_id: str) -> None:
        with self._lock:
            current = self.get()
            channels = current.get("provider_channels", [])
            remaining = [
                item for item in channels if isinstance(item, dict) and item.get("id") != channel_id
            ]
            if len(remaining) == len(channels):
                raise KeyError(channel_id)
            current["provider_channels"] = remaining
            self._write(current)

    def langchain_model_policy(self) -> Any | None:
        from oopsnote.ai.providers import LangChainModelPolicy

        value = self.get().get("langchain_model_policy")
        if not isinstance(value, dict):
            return None
        try:
            return LangChainModelPolicy.model_validate(value)
        except ValueError:
            return None

    def reorder_provider_channels(self, channel_ids: list[str]) -> None:
        """Persist one complete, validated channel order atomically."""
        from oopsnote.ai.providers import ProviderChannel

        with self._lock:
            current = self.get()
            raw_channels = current.get("provider_channels", [])
            if not isinstance(raw_channels, list):
                raise StorageCorruptionError(
                    self.path, ValueError("provider_channels must be a list")
                )
            channels = [ProviderChannel.model_validate(item) for item in raw_channels]
            existing_ids = [channel.id for channel in channels]
            if len(channel_ids) != len(existing_ids) or set(channel_ids) != set(existing_ids):
                raise ValueError("provider channel order must contain every channel exactly once")
            by_id = {channel.id: channel for channel in channels}
            current["provider_channels"] = [
                by_id[channel_id].model_dump(mode="json") for channel_id in channel_ids
            ]
            self._write(current)

    def set_langchain_model_policy(self, policy: Any) -> Any:
        with self._lock:
            current = self.get()
            current["langchain_model_policy"] = policy.model_dump(mode="json")
            if not self._policy_is_runnable(current):
                raise ValueError("LangChain policy references an unavailable channel or model")
            self._write(current)
            return policy
