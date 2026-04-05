"""环境变量工具函数。"""

import os


def float_env(name: str, default: float = 0.0) -> float:
    """从环境变量读取浮点数。"""
    try:
        return float(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


def bool_env(name: str, default: bool = False) -> bool:
    """从环境变量读取布尔值。"""
    return os.getenv(name, str(default)).lower() in ("true", "1", "yes", "on")


def int_env(name: str, default: int = 0) -> int:
    """从环境变量读取整数。"""
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default
