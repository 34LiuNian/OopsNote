"""Environment variable utilities."""

import os


def float_env(name: str, default: float = 0.0) -> float:
    """Get a float value from environment variable."""
    try:
        return float(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


def bool_env(name: str, default: bool = False) -> bool:
    """Get a boolean value from environment variable."""
    return os.getenv(name, str(default)).lower() in ("true", "1", "yes", "on")


def int_env(name: str, default: int = 0) -> int:
    """Get an integer value from environment variable."""
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default
