"""Contract tests for the Better Auth BFF to FastAPI identity envelope."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from oopsnote.api import main
from oopsnote.api.auth import (
    AuthenticationError,
    InternalIdentityConfig,
    authenticate_internal_request,
)
from oopsnote.core import Principal, UserRole
from oopsnote.control import ControlDatabase, WorkspaceRegistry
from oopsnote.core import WorkspaceStoreFactory


SECRET = b"test-only-bff-secret-that-is-at-least-32-bytes"


def _request(method: str, path: str, encoded: str, signature: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (b"x-oopsnote-identity", encoded.encode("ascii")),
                (b"x-oopsnote-signature", signature.encode("ascii")),
            ],
        }
    )


def _signed_identity(**overrides: object) -> tuple[dict[str, object], str, str]:
    payload: dict[str, object] = {
        "v": 1,
        "user_id": "auth-user-a",
        "role": "user",
        "issued_at": 1_000,
        "request_id": str(uuid4()),
        "method": "GET",
        "path": "/tasks",
        **overrides,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    signature = base64.urlsafe_b64encode(
        hmac.new(SECRET, encoded.encode("ascii"), hashlib.sha256).digest()
    ).rstrip(b"=").decode("ascii")
    return payload, encoded, signature


def test_valid_identity_binds_user_role_method_path_and_time():
    payload, encoded, signature = _signed_identity(role="admin")

    principal = authenticate_internal_request(
        _request("GET", "/tasks", encoded, signature),
        InternalIdentityConfig(SECRET),
        now=1_025,
    )

    assert principal.user_id == payload["user_id"]
    assert principal.role == UserRole.ADMIN


@pytest.mark.parametrize(
    ("method", "path", "now"),
    [("POST", "/tasks", 1_025), ("GET", "/other", 1_025), ("GET", "/tasks", 1_031)],
)
def test_identity_rejects_replayed_request_shape_or_expired_timestamp(method, path, now):
    _payload, encoded, signature = _signed_identity()

    with pytest.raises(AuthenticationError, match="(match|expired)"):
        authenticate_internal_request(
            _request(method, path, encoded, signature),
            InternalIdentityConfig(SECRET),
            now=now,
        )


def test_identity_rejects_tampering_before_parsing_claims():
    _payload, encoded, signature = _signed_identity()
    forged = encoded[:-1] + ("A" if encoded[-1] != "A" else "B")

    with pytest.raises(AuthenticationError, match="signature"):
        authenticate_internal_request(
            _request("GET", "/tasks", forged, signature),
            InternalIdentityConfig(SECRET),
            now=1_025,
        )


def test_identity_rejects_unknown_roles_and_malformed_request_ids():
    for overrides, message in [
        ({"role": "owner"}, "invalid role"),
        ({"request_id": "not-a-uuid"}, "request_id"),
    ]:
        _payload, encoded, signature = _signed_identity(**overrides)
        with pytest.raises(AuthenticationError, match=message):
            authenticate_internal_request(
                _request("GET", "/tasks", encoded, signature),
                InternalIdentityConfig(SECRET),
                now=1_025,
            )


def test_fastapi_better_auth_mode_requires_and_accepts_the_signed_bff_identity():
    now = int(time.time())
    _payload, encoded, signature = _signed_identity(issued_at=now)
    environment = {
        "OOPSNOTE_AUTH_MODE": "better-auth",
        "OOPSNOTE_BFF_HMAC_SECRET": SECRET.decode("ascii"),
    }
    with patch.dict("os.environ", environment, clear=False):
        missing = TestClient(main.app).get("/tasks")
        accepted = TestClient(main.app).get(
            "/tasks",
            headers={
                "x-oopsnote-identity": encoded,
                "x-oopsnote-signature": signature,
            },
        )

    assert missing.status_code == 401
    assert missing.json()["detail"] == "Missing internal identity"
    assert accepted.status_code == 200


def test_better_auth_requests_use_the_authenticated_user_workspace(monkeypatch, tmp_path):
    registry = WorkspaceRegistry(
        ControlDatabase(tmp_path / "control" / "app.sqlite"),
        tmp_path / "storage",
    )
    monkeypatch.setattr(main, "WORKSPACE_REGISTRY", registry)
    monkeypatch.setattr(main, "WORKSPACE_STORE_FACTORY", WorkspaceStoreFactory())
    now = int(time.time())
    environment = {
        "OOPSNOTE_AUTH_MODE": "better-auth",
        "OOPSNOTE_BFF_HMAC_SECRET": SECRET.decode("ascii"),
    }
    with patch.dict("os.environ", environment, clear=False):
        client = TestClient(main.app)
        _payload, encoded_a, signature_a = _signed_identity(
            user_id="auth-workspace-a",
            issued_at=now,
            method="POST",
            path="/tasks",
        )
        created = client.post(
            "/tasks",
            headers={
                "x-oopsnote-identity": encoded_a,
                "x-oopsnote-signature": signature_a,
            },
            json={"subject": "math"},
        )
        assert created.status_code == 200

        _payload, encoded_b, signature_b = _signed_identity(
            user_id="auth-workspace-b",
            issued_at=now,
            method="GET",
            path="/tasks",
        )
        isolated = client.get(
            "/tasks",
            headers={
                "x-oopsnote-identity": encoded_b,
                "x-oopsnote-signature": signature_b,
            },
        )

    assert isolated.status_code == 200
    assert isolated.json() == {"items": []}


def test_better_auth_admin_can_manage_quota_without_entering_member_workspace(monkeypatch, tmp_path):
    registry = WorkspaceRegistry(
        ControlDatabase(tmp_path / "control" / "app.sqlite"),
        tmp_path / "storage",
    )
    monkeypatch.setattr(main, "WORKSPACE_REGISTRY", registry)
    monkeypatch.setattr(main, "WORKSPACE_STORE_FACTORY", WorkspaceStoreFactory())
    now = int(time.time())
    environment = {
        "OOPSNOTE_AUTH_MODE": "better-auth",
        "OOPSNOTE_BFF_HMAC_SECRET": SECRET.decode("ascii"),
    }
    with patch.dict("os.environ", environment, clear=False):
        client = TestClient(main.app)
        _payload, encoded, signature = _signed_identity(
            user_id="auth-admin",
            role="admin",
            issued_at=now,
            method="POST",
            path="/admin/members/provision",
        )
        provisioned = client.post(
            "/admin/members/provision",
            headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
            json={"auth_user_id": "auth-member", "daily_success_limit": 6},
        )

        _payload, encoded, signature = _signed_identity(
            user_id="auth-admin",
            role="admin",
            issued_at=now,
            method="PATCH",
            path="/admin/members/auth-member/quota",
        )
        updated = client.patch(
            "/admin/members/auth-member/quota",
            headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
            json={"daily_success_limit": 8, "max_concurrent_runs": 2},
        )

    assert provisioned.status_code == 200
    assert provisioned.json()["quota"]["daily_success_limit"] == 6
    assert updated.status_code == 200
    assert updated.json()["quota"] == {
        "daily_success_limit": 8,
        "max_concurrent_runs": 2,
    }
    assert registry.require(Principal("auth-member", UserRole.USER)).root != registry.require(
        Principal("auth-admin", UserRole.ADMIN)
    ).root


def test_fastapi_health_does_not_require_the_bff_secret():
    with patch.dict(
        "os.environ",
        {
            "OOPSNOTE_AUTH_MODE": "better-auth",
            "OOPSNOTE_BFF_HMAC_SECRET": "",
            "OOPSNOTE_BFF_HMAC_SECRET_FILE": "",
        },
        clear=False,
    ):
        response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["auth"]["mode"] == "better-auth"
