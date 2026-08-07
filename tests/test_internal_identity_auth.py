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
from oopsnote.api.routes import catalog
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


def test_foreign_task_and_asset_are_404_even_for_an_administrator(monkeypatch, tmp_path):
    registry = WorkspaceRegistry(
        ControlDatabase(tmp_path / "control" / "app.sqlite"),
        tmp_path / "storage",
    )
    factory = WorkspaceStoreFactory()
    monkeypatch.setattr(main, "WORKSPACE_REGISTRY", registry)
    monkeypatch.setattr(main, "WORKSPACE_STORE_FACTORY", factory)
    now = int(time.time())
    environment = {
        "OOPSNOTE_AUTH_MODE": "better-auth",
        "OOPSNOTE_BFF_HMAC_SECRET": SECRET.decode("ascii"),
    }
    with patch.dict("os.environ", environment, clear=False):
        client = TestClient(main.app)
        _payload, encoded, signature = _signed_identity(
            user_id="auth-owner",
            issued_at=now,
            method="POST",
            path="/tasks",
        )
        created = client.post(
            "/tasks",
            headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
            json={"subject": "math"},
        )
        task_id = created.json()["task"]["id"]
        owner = Principal("auth-owner", UserRole.USER)
        owner_stores = factory.for_context(registry.require(owner))
        asset_path = owner_stores.asset_store.save_bytes(b"private", "private.bin")

        _payload, encoded, signature = _signed_identity(
            user_id="auth-other-admin",
            role="admin",
            issued_at=now,
            method="GET",
            path=f"/tasks/{task_id}",
        )
        foreign_task = client.get(
            f"/tasks/{task_id}",
            headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
        )
        _payload, encoded, signature = _signed_identity(
            user_id="auth-other-admin",
            role="admin",
            issued_at=now,
            method="GET",
            path=asset_path,
        )
        foreign_asset = client.get(
            asset_path,
            headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
        )
        _payload, encoded, signature = _signed_identity(
            user_id="auth-owner",
            issued_at=now,
            method="GET",
            path=asset_path,
        )
        owner_asset = client.get(
            asset_path,
            headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
        )

    assert created.status_code == 200
    assert foreign_task.status_code == 404
    assert foreign_asset.status_code == 404
    assert owner_asset.status_code == 200
    assert owner_asset.content == b"private"


def test_obsidian_sync_output_is_bound_to_the_authenticated_workspace(monkeypatch, tmp_path):
    registry = WorkspaceRegistry(
        ControlDatabase(tmp_path / "control" / "app.sqlite"),
        tmp_path / "storage",
    )
    monkeypatch.setattr(main, "WORKSPACE_REGISTRY", registry)
    monkeypatch.setattr(main, "WORKSPACE_STORE_FACTORY", WorkspaceStoreFactory())
    observed: list[tuple[object, object]] = []

    class RecordingSyncer:
        def __init__(self, task_store, vault_root=None, tag_store=None):
            observed.append((task_store.base_dir.resolve(), vault_root.resolve()))

        def sync(self):
            return "ok"

        def sync_for_subject(self, _subject):
            return "ok"

    monkeypatch.setattr(catalog, "ObsidianSyncer", RecordingSyncer)
    now = int(time.time())
    environment = {
        "OOPSNOTE_AUTH_MODE": "better-auth",
        "OOPSNOTE_BFF_HMAC_SECRET": SECRET.decode("ascii"),
    }
    with patch.dict("os.environ", environment, clear=False):
        client = TestClient(main.app)
        for user_id, role in [("sync-owner", "user"), ("sync-admin", "admin")]:
            _payload, encoded, signature = _signed_identity(
                user_id=user_id,
                role=role,
                issued_at=now,
                method="POST",
                path="/sync",
            )
            response = client.post(
                "/sync",
                headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
            )
            assert response.status_code == 200

    assert len(observed) == 2
    assert observed[0][0] != observed[1][0]
    assert observed[0][1] != observed[1][1]
    assert all(vault.name == "obsidian-vault" for _task_root, vault in observed)
    assert all(vault.parent == task_root.parent for task_root, vault in observed)


def test_global_tag_dimension_settings_require_an_administrator(monkeypatch, tmp_path):
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
        responses = []
        for user_id, role in [("tag-user", "user"), ("tag-admin", "admin")]:
            _payload, encoded, signature = _signed_identity(
                user_id=user_id,
                role=role,
                issued_at=now,
                method="PUT",
                path="/settings/tag-dimensions",
            )
            responses.append(client.put(
                "/settings/tag-dimensions",
                headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
                json={"dimensions": {}},
            ))

    assert [response.status_code for response in responses] == [403, 200]


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


def test_better_auth_self_provision_applies_invitation_quota_only_to_the_signed_user(monkeypatch, tmp_path):
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
            user_id="auth-self-provision",
            issued_at=now,
            method="POST",
            path="/internal/members/provision-self",
        )
        response = client.post(
            "/internal/members/provision-self",
            headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
            json={"daily_success_limit": 4},
        )

    assert response.status_code == 200
    assert response.json()["auth_user_id"] == "auth-self-provision"
    assert response.json()["quota"]["daily_success_limit"] == 4
    assert registry.quota_summary("auth-self-provision")["daily_success_limit"] == 4
    assert registry.quota_summary("auth-other") is None


def test_own_quota_endpoint_uses_only_the_signed_user(monkeypatch, tmp_path):
    registry = WorkspaceRegistry(
        ControlDatabase(tmp_path / "control" / "app.sqlite"),
        tmp_path / "storage",
    )
    registry.provision("quota-owner", daily_success_limit=9)
    registry.provision("quota-other", daily_success_limit=99)
    monkeypatch.setattr(main, "WORKSPACE_REGISTRY", registry)
    monkeypatch.setattr(main, "WORKSPACE_STORE_FACTORY", WorkspaceStoreFactory())
    now = int(time.time())
    _payload, encoded, signature = _signed_identity(
        user_id="quota-owner",
        issued_at=now,
        method="GET",
        path="/me/quota",
    )
    environment = {
        "OOPSNOTE_AUTH_MODE": "better-auth",
        "OOPSNOTE_BFF_HMAC_SECRET": SECRET.decode("ascii"),
    }
    with patch.dict("os.environ", environment, clear=False):
        response = TestClient(main.app).get(
            "/me/quota",
            headers={"x-oopsnote-identity": encoded, "x-oopsnote-signature": signature},
        )

    assert response.status_code == 200
    assert response.json()["quota"]["daily_success_limit"] == 9


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
