from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOG_PATH = Path(__file__).resolve().parents[1] / "storage" / "llm_errors.log"
_DEFAULT_PREVIEW_CHARS = 2000


def truncate_preview(text: str, max_chars: int = _DEFAULT_PREVIEW_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...<truncated {len(text) - max_chars} chars>"


def append_llm_error_log(record: dict[str, Any]) -> None:
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
