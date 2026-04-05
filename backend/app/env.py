"""环境变量解析辅助函数。"""

from __future__ import annotations

import os


def float_env(name: str, default: float) -> float:
    """将环境变量解析为浮点数。"""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def int_env(name: str, default: int) -> int:
    """将环境变量解析为整数。"""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
