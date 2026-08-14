"""Authentication contracts for OIDC and the trusted Better Auth BFF."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt
from fastapi import Request

from oopsnote.core import Principal, UserRole

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthConfig:
    issuer: str
    audience: str
    jwks_url: str
    mode: str = "better-auth"

    @property
    def enabled(self) -> bool:
        return self.mode == "oidc" and bool(self.issuer and self.audience and self.jwks_url)

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


@dataclass(frozen=True)
class AuthenticatedUser:
    subject: str
    claims: dict[str, Any]


class AuthenticationError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def auth_config_from_env() -> AuthConfig:
    mode = os.getenv("OOPSNOTE_AUTH_MODE", "better-auth").strip().lower() or "better-auth"
    if mode not in {"oidc", "local", "better-auth"}:
        raise RuntimeError("OOPSNOTE_AUTH_MODE must be 'oidc', 'better-auth', or 'local'")
    issuer = os.getenv("OOPSNOTE_AUTH_ISSUER", "").strip().rstrip("/")
    audience = os.getenv("OOPSNOTE_AUTH_AUDIENCE", "").strip()
    jwks_url = os.getenv("OOPSNOTE_AUTH_JWKS_URL", "").strip()
    if issuer and not jwks_url:
        jwks_url = f"{issuer}/.well-known/jwks.json"
    return AuthConfig(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
        mode=mode,
    )


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


@lru_cache(maxsize=8)
def _jwk_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url)


def _bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "").strip()
    if not header:
        raise AuthenticationError("Missing bearer token")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Invalid authorization scheme")
    return token


def authenticate_request(request: Request, config: AuthConfig) -> AuthenticatedUser:
    if not config.enabled:
        raise AuthenticationError("Authentication is not configured", status_code=500)
    token = _bearer_token(request)
    try:
        signing_key = _jwk_client(config.jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.audience,
            issuer=config.issuer,
            options={"require": ["exp", "iss", "sub"]},
        )
    except jwt.PyJWKClientConnectionError as error:
        logger.error("OIDC JWKS retrieval failed from %s: %s", config.jwks_url, error)
        raise AuthenticationError(
            "Authentication service is temporarily unavailable", status_code=503
        ) from error
    except jwt.PyJWKClientError as error:
        raise AuthenticationError(f"Invalid token: {error}") from error
    except jwt.InvalidTokenError as error:
        raise AuthenticationError(f"Invalid token: {error}") from error
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise AuthenticationError("Token is missing subject")
    return AuthenticatedUser(subject=subject, claims=claims)


def _claim_values(claims: dict[str, Any]) -> set[str]:
    """Normalize the common OIDC role/group claim shapes."""
    values: set[str] = set()
    for key in ("role", "roles", "groups"):
        value = claims.get(key)
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, list):
            values.update(item for item in value if isinstance(item, str))
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        value = realm_access.get("roles")
        if isinstance(value, list):
            values.update(item for item in value if isinstance(item, str))
    return {value.strip() for value in values if value.strip()}


def require_admin_request(request: Request) -> AuthenticatedUser | Principal | None:
    """Authorize privileged settings at the API boundary.

    Local mode is an explicit loopback-development mode. The deployment must
    keep the backend port private because it intentionally has no user identity.
    When OIDC is disabled OopsNote is explicitly local-only and loopback is the
    administrator. Once OIDC is enabled, a verified token must carry a role in
    ``OOPSNOTE_ADMIN_ROLES`` (default: ``admin``) or a configured subject.
    """
    config = auth_config_from_env()
    if config.local:
        return None
    if config.better_auth:
        principal = getattr(request.state, "principal", None)
        if not isinstance(principal, Principal):
            raise AuthenticationError("Missing authenticated user")
        if principal.role != UserRole.ADMIN:
            raise AuthenticationError("Administrator role is required", status_code=403)
        return principal
    if not config.enabled:
        host = (request.client.host if request.client else "").strip().lower()
        if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise AuthenticationError(
                "Administrator access requires OIDC outside loopback", status_code=403
            )
        return None
    user = getattr(request.state, "auth", None)
    if not isinstance(user, AuthenticatedUser):
        raise AuthenticationError("Missing authenticated user")
    subjects = {
        value.strip()
        for value in os.getenv("OOPSNOTE_ADMIN_SUBJECTS", "").split(",")
        if value.strip()
    }
    roles = {
        value.strip()
        for value in os.getenv("OOPSNOTE_ADMIN_ROLES", "admin").split(",")
        if value.strip()
    }
    if user.subject in subjects or _claim_values(user.claims).intersection(roles):
        return user
    raise AuthenticationError("Administrator role is required", status_code=403)
