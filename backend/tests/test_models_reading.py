from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _make_client(monkeypatch, main_module, *, startup_fetch: bool) -> TestClient:
    """Create a TestClient with startup behavior controlled via monkeypatch."""

    if not startup_fetch:
        # Prevent startup prefetch from making any fetch calls.
        monkeypatch.setattr(
            main_module,
            "_guess_openai_gateway_config",
            lambda: (None, None, None, "Authorization"),
            raising=True,
        )

    return TestClient(main_module.app)


def test_models_uses_cache_when_present(monkeypatch):
    from app import main as main_module

    # Ensure startup doesn't fetch.
    client = _make_client(monkeypatch, main_module, startup_fetch=False)

    # Seed cache.
    main_module._models_cache = [
        {"id": "m-1", "provider": "x", "provider_type": "openai"},
        {"id": "m-2", "provider": "y", "provider_type": "openai"},
    ]

    # If cache is present and refresh=false, fetch must not be called.
    def _should_not_fetch(*args: Any, **kwargs: Any):
        raise AssertionError("_fetch_openai_models should not be called when cache exists")

    monkeypatch.setattr(main_module, "_fetch_openai_models", _should_not_fetch, raising=True)

    res = client.get("/models")
    assert res.status_code == 200
    payload = res.json()
    assert [item["id"] for item in payload["items"]] == ["m-1", "m-2"]


def test_models_refresh_true_fetches(monkeypatch):
    from app import main as main_module

    client = _make_client(monkeypatch, main_module, startup_fetch=False)

    main_module._models_cache = [
        {"id": "old", "provider": "x", "provider_type": "openai"},
    ]

    calls: list[tuple] = []

    def _fake_fetch(base_url: str, api_key: str | None, authorization: str | None, auth_header_name: str, timeout_seconds: float = 5.0):
        calls.append((base_url, api_key, authorization, auth_header_name))
        return [
            {"id": "new-1", "provider": "gw", "provider_type": "openai"},
            {"id": "new-2", "provider": "gw", "provider_type": "openai"},
        ]

    monkeypatch.setattr(main_module, "_guess_openai_gateway_config", lambda: ("http://gw/v1", None, "Bearer t", "Authorization"), raising=True)
    monkeypatch.setattr(main_module, "_fetch_openai_models", _fake_fetch, raising=True)

    res = client.get("/models?refresh=true")
    assert res.status_code == 200
    payload = res.json()
    assert [item["id"] for item in payload["items"]] == ["new-1", "new-2"]
    assert len(calls) == 1


def test_startup_prefetch_populates_cache(monkeypatch):
    from app import main as main_module

    main_module._models_cache = None

    calls: list[tuple] = []

    def _fake_fetch(base_url: str, api_key: str | None, authorization: str | None, auth_header_name: str, timeout_seconds: float = 5.0):
        calls.append((base_url, api_key, authorization, auth_header_name))
        return [{"id": "boot", "provider": "gw", "provider_type": "openai"}]

    monkeypatch.setattr(main_module, "_guess_openai_gateway_config", lambda: ("http://gw/v1", None, "Bearer t", "Authorization"), raising=True)
    monkeypatch.setattr(main_module, "_fetch_openai_models", _fake_fetch, raising=True)

    # Trigger startup events (prefetch runs here).
    with TestClient(main_module.app) as client:
        res = client.get("/models")
        assert res.status_code == 200

    assert len(calls) == 1
    assert main_module._models_cache is not None
    assert main_module._models_cache[0]["id"] == "boot"
