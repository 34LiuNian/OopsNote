from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class TaskRepositoryLike(Protocol):
    def list_all(self) -> dict[str, Any]: ...


class AgentSettingsLike(Protocol):
    def load_models(self) -> dict[str, str]: ...

    def save_models(self, models: dict[str, str] | None) -> dict[str, str]: ...

    def enabled_snapshot(self) -> dict[str, bool]: ...

    def save_enabled(self, enabled: dict[str, bool] | None) -> dict[str, bool]: ...

    def thinking_snapshot(self) -> dict[str, bool]: ...

    def save_thinking(self, thinking: dict[str, bool] | None) -> dict[str, bool]: ...


class TasksServiceLike(Protocol):
    def ensure_workers_started(self) -> None: ...


class ModelsServiceLike(Protocol):
    def prefetch_cache(self) -> None: ...


@dataclass
class BackendState:
    repository: TaskRepositoryLike
    ai_gateway_status: dict[str, object]
    agent_settings: AgentSettingsLike
    tasks: TasksServiceLike | None = None
    models: ModelsServiceLike | None = None
