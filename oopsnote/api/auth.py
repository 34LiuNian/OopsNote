"""Authentication contracts for Better Auth and explicit loopback local mode."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address
from uuid import UUID

from fastapi import Request

from oopsnote.core import Principal, UserRole


@dataclass(frozen=True)
class AuthConfig:
    mode: str = "better-auth"

    @property
    def local(self) -> bool:
        return self.mode == "local"

    @property
    def better_auth(self) -> bool:
        return self.mode == "better-auth"


@dataclass(frozen=True)
class InternalIdentityConfig:
    secret: bytes
    max_age_seconds: int = 30
    max_future_skew_seconds: int = 5


class AuthenticationError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def auth_config_from_env() -> AuthConfig:
    mode = os.getenv("OOPSNOTE_AUTH_MODE", "better-auth").strip().lower() or "better-auth"
    if mode not in {"better-auth", "local"}:
        raise RuntimeError("OOPSNOTE_AUTH_MODE must be 'better-auth' or 'local'")
    return AuthConfig(mode=mode)


def internal_identity_config_from_env() -> InternalIdentityConfig:
    secret_file = os.getenv("OOPSNOTE_BFF_HMAC_SECRET_FILE", "").strip()
    if secret_file:
        try:
            with open(secret_file, "rb") as secret_handle:
                secret = secret_handle.read().strip()
        except OSError as error:
            raise RuntimeError("Unable to read OOPSNOTE_BFF_HMAC_SECRET_FILE") from error
    else:
        secret = os.getenv("OOPSNOTE_BFF_HMAC_SECRET", "").strip().encode("utf-8")
    if len(secret) < 32:
        raise RuntimeError("Better Auth BFF HMAC secret must contain at least 32 bytes")
    return InternalIdentityConfig(secret=secret)


def authorize_local_request(request: Request) -> None:
    """Keep the unauthenticated development mode on the loopback boundary."""
    host = (request.client.host if request.client else "").strip().lower()
    if host in {"localhost", "testclient"}:
        return
    try:
        is_loopback = ip_address(host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise AuthenticationError("Local auth mode accepts only loopback requests", status_code=403)


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as error:
        raise AuthenticationError("Invalid internal identity encoding") from error


def authenticate_internal_request(
    request: Request,
    config: InternalIdentityConfig,
    *,
    now: int | None = None,
) -> Principal:
    encoded = request.headers.get("x-oopsnote-identity", "").strip()
    signature = request.headers.get("x-oopsnote-signature", "").strip()
    if not encoded or not signature:
        raise AuthenticationError("Missing internal identity")
    try:
        encoded_bytes = encoded.encode("ascii")
    except UnicodeEncodeError as error:
        raise AuthenticationError("Invalid internal identity encoding") from error
    expected = hmac.new(config.secret, encoded_bytes, hashlib.sha256).digest()
    provided = _decode_base64url(signature)
    if not hmac.compare_digest(provided, expected):
        raise AuthenticationError("Invalid internal identity signature")
    try:
        payload = json.loads(_decode_base64url(encoded))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise AuthenticationError("Invalid internal identity payload") from error
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise AuthenticationError("Unsupported internal identity version")

    user_id = payload.get("user_id")
    role = payload.get("role")
    issued_at = payload.get("issued_at")
    request_id = payload.get("request_id")
    method = payload.get("method")
    path = payload.get("path")
    if not isinstance(user_id, str) or not user_id.strip():
        raise AuthenticationError("Internal identity is missing user_id")
    if role not in {UserRole.ADMIN.value, UserRole.USER.value}:
        raise AuthenticationError("Internal identity has an invalid role")
    if not isinstance(issued_at, int) or isinstance(issued_at, bool):
        raise AuthenticationError("Internal identity has an invalid issued_at")
    try:
        UUID(str(request_id))
    except (TypeError, ValueError) as error:
        raise AuthenticationError("Internal identity has an invalid request_id") from error
    if method != request.method.upper() or path != request.url.path:
        raise AuthenticationError("Internal identity does not match this request")

    current_time = now if now is not None else int(datetime.now(UTC).timestamp())
    age = current_time - issued_at
    if age > config.max_age_seconds or age < -config.max_future_skew_seconds:
        raise AuthenticationError("Internal identity has expired")
    try:
        return Principal(user_id=user_id, role=UserRole(role))
    except ValueError as error:
        raise AuthenticationError("Internal identity has invalid principal claims") from error


def require_admin_request(request: Request) -> Principal | None:
    """Authorize privileged settings at the Better Auth BFF boundary."""
    config = auth_config_from_env()
    if config.local:
        return None
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise AuthenticationError("Missing authenticated user")
    if principal.role != UserRole.ADMIN:
        raise AuthenticationError("Administrator role is required", status_code=403)
    return principal
