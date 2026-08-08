"""Workspace capability context for the private managed MCP boundary."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone

from oopsnote.core import AssetStore, RunStore, TagStore, TaskStore, WorkspaceId


@dataclass(frozen=True, slots=True)
class McpStores:
    task_store: TaskStore
    tag_store: TagStore
    asset_store: AssetStore
    run_store: RunStore


@dataclass(frozen=True, slots=True)
class McpCapability:
    workspace_id: WorkspaceId
    stores: McpStores
    expires_at: datetime

    def is_valid(self, now: datetime | None = None) -> bool:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return current < self.expires_at


_current_capability: ContextVar[McpCapability | None] = ContextVar(
    "oopsnote_mcp_capability",
    default=None,
)


def activate_capability(capability: McpCapability) -> Token[McpCapability | None]:
    return _current_capability.set(capability)


def reset_capability(token: Token[McpCapability | None]) -> None:
    _current_capability.reset(token)


def current_capability() -> McpCapability | None:
    return _current_capability.get()


__all__ = [
    "McpCapability",
    "McpStores",
    "activate_capability",
    "current_capability",
    "reset_capability",
]
