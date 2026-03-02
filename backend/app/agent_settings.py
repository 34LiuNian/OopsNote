"""Agent settings management - per-agent model, enable, thinking, temperature,
gateway, and debug configuration.

This module provides persistent storage for agent-specific settings that control:
- Model selection per agent
- Enable/disable switches per agent
- Thinking mode toggles per agent
- Temperature overrides per agent
- Gateway connection parameters (base_url, api_key, default model, temperature)
- Debug switches (LLM payload logging, task persistence)
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class AgentModelSettings:
    """Immutable container for agent model settings.

    Attributes:
        models: Mapping of agent names (uppercase) to model identifiers
    """

    models: Dict[str, str]


class AgentModelSettingsStore:
    """Persist per-agent model selection (non-secret) on disk.

    This is designed for UI-driven model switching without touching API
    keys.
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "agent_models.json")
        self._lock = threading.Lock()

    def load(self) -> AgentModelSettings:
        """Load agent model settings from disk.

        Returns:
            AgentModelSettings with current model mappings
        """
        with self._lock:
            if not self.path.exists():
                return AgentModelSettings(models={})
            data = json.loads(self.path.read_text(encoding="utf-8"))
            models = data.get("models", {}) if isinstance(data, dict) else {}
            if not isinstance(models, dict):
                models = {}
            normalized = {
                str(k).upper(): str(v) for k, v in models.items() if v is not None
            }
            return AgentModelSettings(models=normalized)

    def save(self, settings: AgentModelSettings) -> AgentModelSettings:
        """Save agent model settings to disk.

        Args:
            settings: Settings to persist

        Returns:
            Saved settings
        """
        with self._lock:
            payload = {"models": {k.upper(): v for k, v in settings.models.items()}}
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings

    def set_model(self, agent_name: str, model: str) -> AgentModelSettings:
        """Set model for a specific agent.

        Args:
            agent_name: Agent identifier (case-insensitive)
            model: Model name to use

        Returns:
            Updated settings after save
        """
        current = self.load()
        next_models = dict(current.models)
        next_models[agent_name.upper()] = model
        return self.save(AgentModelSettings(models=next_models))


@dataclass(frozen=True)
class AgentEnableSettings:
    """Immutable container for agent enable/disable settings.

    Attributes:
        enabled: Mapping of agent names (uppercase) to enable state
    """

    enabled: Dict[str, bool]


class AgentEnableSettingsStore:
    """Persist per-agent enable switches (non-secret) on disk.

    Intended to control whether a given agent is executed / allowed to
    use the model.
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "agent_enabled.json")
        self._lock = threading.Lock()

    def load(self) -> AgentEnableSettings:
        """Load agent enable settings from disk.

        Returns:
            AgentEnableSettings with current enable states
        """
        with self._lock:
            if not self.path.exists():
                return AgentEnableSettings(enabled={})
            data = json.loads(self.path.read_text(encoding="utf-8"))
            enabled = data.get("enabled", {}) if isinstance(data, dict) else {}
            if not isinstance(enabled, dict):
                enabled = {}

            normalized: Dict[str, bool] = {}
            for k, v in enabled.items():
                if k is None:
                    continue
                normalized[str(k).upper()] = bool(v)
            return AgentEnableSettings(enabled=normalized)

    def save(self, settings: AgentEnableSettings) -> AgentEnableSettings:
        """Save agent enable settings to disk.

        Args:
            settings: Settings to persist

        Returns:
            Saved settings
        """
        with self._lock:
            payload = {
                "enabled": {k.upper(): bool(v) for k, v in settings.enabled.items()}
            }
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings


@dataclass(frozen=True)
class AgentThinkingSettings:
    """Immutable container for agent thinking mode settings.

    Attributes:
        thinking: Mapping of agent names (uppercase) to thinking mode state
    """

    thinking: Dict[str, bool]


class AgentThinkingSettingsStore:
    """Persist per-agent thinking switches (non-secret) on disk.

    The meaning is intentionally lightweight: it influences prompt style.
    Providers may ignore it if unsupported.
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "agent_thinking.json")
        self._lock = threading.Lock()

    def load(self) -> AgentThinkingSettings:
        """Load agent thinking mode settings from disk.

        Returns:
            AgentThinkingSettings with current thinking mode states
        """
        with self._lock:
            if not self.path.exists():
                return AgentThinkingSettings(thinking={})
            data = json.loads(self.path.read_text(encoding="utf-8"))
            thinking = data.get("thinking", {}) if isinstance(data, dict) else {}
            if not isinstance(thinking, dict):
                thinking = {}

            normalized: Dict[str, bool] = {}
            for k, v in thinking.items():
                if k is None:
                    continue
                normalized[str(k).upper()] = bool(v)
            return AgentThinkingSettings(thinking=normalized)

    def save(self, settings: AgentThinkingSettings) -> AgentThinkingSettings:
        """Save agent thinking mode settings to disk.

        Args:
            settings: Settings to persist

        Returns:
            Saved settings
        """
        with self._lock:
            payload = {
                "thinking": {k.upper(): bool(v) for k, v in settings.thinking.items()}
            }
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings


# ---------------------------------------------------------------------------
# Agent Temperature Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentTemperatureSettings:
    """Immutable container for per-agent temperature overrides.

    Attributes:
        temperature: Mapping of agent names (uppercase) to temperature values
    """

    temperature: Dict[str, float]


class AgentTemperatureSettingsStore:
    """Persist per-agent temperature overrides on disk."""

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "agent_temperature.json")
        self._lock = threading.Lock()

    def load(self) -> AgentTemperatureSettings:
        with self._lock:
            if not self.path.exists():
                return AgentTemperatureSettings(temperature={})
            data = json.loads(self.path.read_text(encoding="utf-8"))
            raw = data.get("temperature", {}) if isinstance(data, dict) else {}
            if not isinstance(raw, dict):
                raw = {}
            normalized: Dict[str, float] = {}
            for k, v in raw.items():
                if k is None:
                    continue
                try:
                    normalized[str(k).upper()] = float(v)
                except (ValueError, TypeError):
                    continue
            return AgentTemperatureSettings(temperature=normalized)

    def save(self, settings: AgentTemperatureSettings) -> AgentTemperatureSettings:
        with self._lock:
            payload = {
                "temperature": {
                    k.upper(): float(v) for k, v in settings.temperature.items()
                }
            }
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings


# ---------------------------------------------------------------------------
# Gateway Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GatewaySettings:
    """Immutable container for gateway connection parameters.

    These values override the corresponding environment variables when set.

    Attributes:
        base_url: OpenAI-compatible gateway base URL
        api_key: API key (stored in plaintext in local file)
        default_model: Fallback model name
        temperature: Default temperature
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    temperature: Optional[float] = None


class GatewaySettingsStore:
    """Persist gateway connection parameters on disk.

    Values stored here take priority over environment variables.
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "gateway.json")
        self._lock = threading.Lock()

    def load(self) -> GatewaySettings:
        with self._lock:
            if not self.path.exists():
                return GatewaySettings()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return GatewaySettings()
            temp = data.get("temperature")
            if temp is not None:
                try:
                    temp = float(temp)
                except (ValueError, TypeError):
                    temp = None
            return GatewaySettings(
                base_url=data.get("base_url") or None,
                api_key=data.get("api_key") or None,
                default_model=data.get("default_model") or None,
                temperature=temp,
            )

    def save(self, settings: GatewaySettings) -> GatewaySettings:
        with self._lock:
            payload: dict = {}
            if settings.base_url is not None:
                payload["base_url"] = settings.base_url
            if settings.api_key is not None:
                payload["api_key"] = settings.api_key
            if settings.default_model is not None:
                payload["default_model"] = settings.default_model
            if settings.temperature is not None:
                payload["temperature"] = settings.temperature
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings


# ---------------------------------------------------------------------------
# Debug Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DebugSettings:
    """Immutable container for debug switches.

    Attributes:
        debug_llm_payload: Whether to log LLM request/response payloads
        persist_tasks: Whether to persist tasks to disk
    """

    debug_llm_payload: bool = False
    persist_tasks: bool = True


class DebugSettingsStore:
    """Persist debug switches on disk."""

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "debug.json")
        self._lock = threading.Lock()

    def load(self) -> DebugSettings:
        with self._lock:
            if not self.path.exists():
                return DebugSettings()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return DebugSettings()
            return DebugSettings(
                debug_llm_payload=bool(data.get("debug_llm_payload", False)),
                persist_tasks=bool(data.get("persist_tasks", True)),
            )

    def save(self, settings: DebugSettings) -> DebugSettings:
        with self._lock:
            payload = {
                "debug_llm_payload": settings.debug_llm_payload,
                "persist_tasks": settings.persist_tasks,
            }
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings
