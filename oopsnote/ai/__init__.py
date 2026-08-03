"""Managed AI execution for OopsNote."""

from __future__ import annotations

from typing import Any

__all__ = ["AgentBackend", "HermesRunner", "LangChainRunner", "ManagedAiRunner", "PiRpcBackend", "PiRpcRunner"]


def __getattr__(name: str) -> Any:
    """Load public runners only when requested, keeping submodules independent."""
    if name not in __all__:
        raise AttributeError(name)
    from . import runner

    return getattr(runner, name)
