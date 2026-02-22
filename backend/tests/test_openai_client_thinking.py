"""Tests for OpenAI client thinking mode support."""

from __future__ import annotations

from app.clients.openai_client import OpenAIClient


def _make_client(monkeypatch) -> OpenAIClient:
    class _DummyOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("app.clients.openai_client.OpenAI", _DummyOpenAI)
    return OpenAIClient(api_key="test-key", base_url="http://localhost:5000/v1")


def test_structured_chat_accepts_thinking(monkeypatch) -> None:
    """Test that structured_chat passes thinking parameter to completion."""
    client = _make_client(monkeypatch)

    seen: dict[str, object] = {}

    def _fake_complete(messages, **kwargs):
        seen["thinking"] = kwargs.get("thinking")
        return {"ok": True}

    monkeypatch.setattr(client, "_complete_json_messages", _fake_complete)

    payload = client.structured_chat(
        "sys",
        "user",
        thinking=True,
    )

    assert payload == {"ok": True}
    assert seen["thinking"] is True


def test_structured_chat_with_image_accepts_thinking(monkeypatch) -> None:
    """Test that structured_chat_with_image passes thinking parameter to completion."""
    client = _make_client(monkeypatch)

    seen: dict[str, object] = {}

    def _fake_complete(messages, **kwargs):
        seen["thinking"] = kwargs.get("thinking")
        return {"ok": True}

    monkeypatch.setattr(client, "_complete_json_messages", _fake_complete)

    payload = client.structured_chat_with_image(
        "sys",
        "user",
        b"img",
        "image/jpeg",
        thinking=False,
    )

    assert payload == {"ok": True}
    assert seen["thinking"] is False
