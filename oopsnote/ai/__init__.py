"""Managed AI execution for OopsNote."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AgentBackend",
    "HermesRunner",
    "LangChainRunner",
    "ManagedAiRunner",
    "ManagedWorkItem",
    "PiRpcBackend",
    "PiRpcRunner",
]


def __getattr__(name: str) -> Any:
    """Load public runners only when requested, keeping submodules independent."""
    if name not in __all__:
        raise AttributeError(name)
    if name == "ManagedWorkItem":
        from .work_items import ManagedWorkItem

        return ManagedWorkItem
    from . import runner

    return getattr(runner, name)
