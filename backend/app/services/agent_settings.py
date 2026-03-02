from __future__ import annotations

from dataclasses import dataclass, field

from ..agent_settings import (
    AgentEnableSettings,
    AgentEnableSettingsStore,
    AgentModelSettings,
    AgentModelSettingsStore,
    AgentTemperatureSettings,
    AgentTemperatureSettingsStore,
    AgentThinkingSettings,
    AgentThinkingSettingsStore,
    DebugSettings,
    DebugSettingsStore,
    GatewaySettings,
    GatewaySettingsStore,
)


@dataclass
class AgentSettingsService:
    model_store: AgentModelSettingsStore
    enable_store: AgentEnableSettingsStore
    thinking_store: AgentThinkingSettingsStore
    temperature_store: AgentTemperatureSettingsStore
    gateway_store: GatewaySettingsStore
    debug_store: DebugSettingsStore
    force_enabled_agents: set[str] = field(
        default_factory=lambda: {"OCR", "SOLVER", "TAGGER"}
    )

    def resolve_saved_model(self, agent: str) -> str | None:
        settings = self.model_store.load()
        return settings.models.get(str(agent).upper())

    def is_agent_enabled(self, name: str) -> bool:
        key = str(name).upper()
        if key in self.force_enabled_agents:
            return True
        try:
            settings = self.enable_store.load()
            return settings.enabled.get(key, True)
        except Exception:
            return True

    def enabled_snapshot(self) -> dict[str, bool]:
        # Expose a stable set of keys for UI.
        keys = ["SOLVER", "TAGGER", "OCR"]
        return {k: self.is_agent_enabled(k) for k in keys}

    def save_enabled(self, enabled: dict[str, bool] | None) -> dict[str, bool]:
        incoming: dict[str, bool] = {}
        for k, v in (enabled or {}).items():
            incoming[str(k).upper()] = bool(v)

        for locked in self.force_enabled_agents:
            incoming[locked] = True

        _saved = self.enable_store.save(AgentEnableSettings(enabled=incoming))
        return self.enabled_snapshot()

    def is_agent_thinking(self, name: str) -> bool:
        # Default True to preserve existing behavior.
        key = str(name).upper()
        try:
            settings = self.thinking_store.load()
            return settings.thinking.get(key, True)
        except Exception:
            return True

    def thinking_snapshot(self) -> dict[str, bool]:
        keys = ["SOLVER", "TAGGER", "OCR"]
        return {k: self.is_agent_thinking(k) for k in keys}

    def save_thinking(self, thinking: dict[str, bool] | None) -> dict[str, bool]:
        incoming: dict[str, bool] = {}
        for k, v in (thinking or {}).items():
            incoming[str(k).upper()] = bool(v)

        _saved = self.thinking_store.save(AgentThinkingSettings(thinking=incoming))
        return self.thinking_snapshot()

    def save_models(self, models: dict[str, str] | None) -> dict[str, str]:
        normalized = {str(k).upper(): str(v) for k, v in (models or {}).items() if v}
        saved = self.model_store.save(AgentModelSettings(models=normalized))
        return saved.models

    def load_models(self) -> dict[str, str]:
        settings = self.model_store.load()
        return settings.models

    # --- Temperature ---

    def resolve_temperature(self, agent: str) -> float | None:
        """Return per-agent temperature override, or None if not set."""
        settings = self.temperature_store.load()
        return settings.temperature.get(str(agent).upper())

    def temperature_snapshot(self) -> dict[str, float]:
        keys = ["SOLVER", "TAGGER", "OCR"]
        settings = self.temperature_store.load()
        return {k: settings.temperature[k] for k in keys if k in settings.temperature}

    def save_temperature(self, temperature: dict[str, float] | None) -> dict[str, float]:
        incoming: dict[str, float] = {}
        for k, v in (temperature or {}).items():
            try:
                incoming[str(k).upper()] = float(v)
            except (ValueError, TypeError):
                continue
        _saved = self.temperature_store.save(
            AgentTemperatureSettings(temperature=incoming)
        )
        return self.temperature_snapshot()

    # --- Gateway ---

    def load_gateway(self) -> GatewaySettings:
        return self.gateway_store.load()

    def save_gateway(self, settings: GatewaySettings) -> GatewaySettings:
        return self.gateway_store.save(settings)

    # --- Debug ---

    def load_debug(self) -> DebugSettings:
        return self.debug_store.load()

    def save_debug(self, settings: DebugSettings) -> DebugSettings:
        return self.debug_store.save(settings)
