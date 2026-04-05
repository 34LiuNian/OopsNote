"""后端应用入口模块。"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    # 避免 pytest 运行依赖本地开发者的私有配置。
    # 如需在测试中强制启用 dotenv，可取消设置
    # `PYTEST_CURRENT_TEST`。
    if (
        "PYTEST_CURRENT_TEST" not in os.environ
        and os.getenv("AI_MISTAKE_ORGANIZER_DISABLE_DOTENV") != "true"
    ):
        _backend_root = Path(__file__).resolve().parents[1]
        load_dotenv(_backend_root / ".env")
except Exception:
    # `python-dotenv` 为可选依赖；只要进程环境变量已配置，
    # 后端仍可正常运行。
    pass

from .bootstrap import create_app

app = create_app()
