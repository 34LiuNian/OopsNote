"""Backend module - auto-generated docstring."""

from __future__ import annotations

import os


def float_env(name: str, default: float) -> float:
    """Parse environment variable as float."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def int_env(name: str, default: int) -> int:
    """Parse environment variable as integer."""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
