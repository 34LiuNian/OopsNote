from __future__ import annotations

import os


def test_trace_event_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_TRACE", "true")
    monkeypatch.setenv("AI_TRACE_DIR", str(tmp_path))

    from app.request_context import set_request_id, reset_request_id
    from app.trace import trace_event

    token = set_request_id("ridtest")
    try:
        trace_event("unit_test", foo="bar")
    finally:
        reset_request_id(token)

    p = tmp_path / "ridtest.jsonl"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    assert "\"event\": \"unit_test\"" in content
    assert "\"foo\": \"bar\"" in content
