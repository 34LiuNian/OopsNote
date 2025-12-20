from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .request_context import get_request_id


def _is_enabled() -> bool:
    return os.getenv("AI_TRACE", "false").lower() == "true" or os.getenv("AI_DEBUG_LLM", "false").lower() == "true"


def _trace_dir() -> Path:
    # Default under backend/app/../storage/traces
    configured = os.getenv("AI_TRACE_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "storage" / "traces"


def _max_chars() -> int:
    try:
        return int(os.getenv("AI_TRACE_MAX_CHARS", "8000"))
    except ValueError:
        return 8000


def _truncate(value: Any) -> Any:
    if isinstance(value, str):
        max_chars = _max_chars()
        if len(value) > max_chars:
            return value[:max_chars] + f"\n...<truncated {len(value) - max_chars} chars>"
    return value


def trace_event(event: str, **fields: Any) -> None:
    """Append a JSONL trace entry into a per-request file named by request_id.

    Enabled when AI_TRACE=true or AI_DEBUG_LLM=true.
    """

    if not _is_enabled():
        return

    rid = get_request_id()
    if not rid or rid == "-":
        return

    out_dir = _trace_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{rid}.jsonl"

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "rid": rid,
        "event": event,
        **{k: _truncate(v) for k, v in fields.items()},
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
