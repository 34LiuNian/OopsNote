"""Backward-compatible imports for the split AI runtime modules.

New code should import shared lifecycle types from ``oopsnote.ai.managed`` and
process implementations from ``oopsnote.ai.backends``. This module remains the
stable public surface used by existing integrations and tests.
"""

from __future__ import annotations

import subprocess

from oopsnote.ai.backends import HermesRunner, PiRpcBackend, PiRpcRunner
from oopsnote.ai.managed import AgentBackend, ManagedAiRunner

__all__ = [
    "AgentBackend",
    "HermesRunner",
    "ManagedAiRunner",
    "PiRpcBackend",
    "PiRpcRunner",
    "subprocess",
]
