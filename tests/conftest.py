"""Shared test baseline: API regression tests explicitly use loopback local auth."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _local_auth_baseline(monkeypatch):
    monkeypatch.setenv("OOPSNOTE_AUTH_MODE", "local")
