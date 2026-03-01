"""Backend module - auto-generated docstring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class TaskRepositoryLike(Protocol):
    """Protocol for task repository dependency injection."""

    def list_all(self) -> dict[str, Any]: ...


class AgentSettingsLike(Protocol):
    """Protocol for agent settings service dependency injection."""

    def load_models(self) -> dict[str, str]: ...

    def save_models(self, models: dict[str, str] | None) -> dict[str, str]: ...

    def enabled_snapshot(self) -> dict[str, bool]: ...

    def save_enabled(self, enabled: dict[str, bool] | None) -> dict[str, bool]: ...

    def thinking_snapshot(self) -> dict[str, bool]: ...

    def save_thinking(self, thinking: dict[str, bool] | None) -> dict[str, bool]: ...


class TasksServiceLike(Protocol):
    """Protocol for tasks service dependency injection."""

    def ensure_workers_started(self) -> None: ...


class ModelsServiceLike(Protocol):
    """Protocol for models service dependency injection."""

    def prefetch_cache(self) -> None: ...


@dataclass
class BackendState:
    """Container for backend application state and services."""

    repository: TaskRepositoryLike
    ai_gateway_status: dict[str, object]
    agent_settings: AgentSettingsLike
    tasks: TasksServiceLike
    models: ModelsServiceLike
