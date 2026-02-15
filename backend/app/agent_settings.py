from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


@dataclass(frozen=True)
class AgentModelSettings:
    models: Dict[str, str]


class AgentModelSettingsStore:
    """Persist per-agent model selection (non-secret) on disk.

    This is designed for UI-driven model switching without touching API keys.
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "agent_models.json")
        self._lock = threading.Lock()

    def load(self) -> AgentModelSettings:
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
        with self._lock:
            payload = {"models": {k.upper(): v for k, v in settings.models.items()}}
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings

    def set_model(self, agent_name: str, model: str) -> AgentModelSettings:
        current = self.load()
        next_models = dict(current.models)
        next_models[agent_name.upper()] = model
        return self.save(AgentModelSettings(models=next_models))


@dataclass(frozen=True)
class AgentEnableSettings:
    enabled: Dict[str, bool]


class AgentEnableSettingsStore:
    """Persist per-agent enable switches (non-secret) on disk.

    Intended to control whether a given agent is executed / allowed to use the model.
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "agent_enabled.json")
        self._lock = threading.Lock()

    def load(self) -> AgentEnableSettings:
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
        with self._lock:
            payload = {
                "thinking": {k.upper(): bool(v) for k, v in settings.thinking.items()}
            }
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings
