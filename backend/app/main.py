from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Avoid making pytest runs depend on local developer secrets/config.
    # You can still force-enable dotenv in tests by unsetting PYTEST_CURRENT_TEST.
    if (
        "PYTEST_CURRENT_TEST" not in os.environ
        and os.getenv("AI_MISTAKE_ORGANIZER_DISABLE_DOTENV") != "true"
    ):
        _backend_root = Path(__file__).resolve().parents[1]
        load_dotenv(_backend_root / ".env")
except Exception:
    # Optional dependency; backend still works if env vars are provided by the process.
    pass

from .bootstrap import create_app

app = create_app()
