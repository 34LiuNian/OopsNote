"""OIDC access-token validation for authenticated Web requests."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Request


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthConfig:
    issuer: str
    audience: str
    jwks_url: str
    mode: str = "oidc"

    @property
    def enabled(self) -> bool:
        return self.mode == "oidc" and bool(self.issuer and self.audience and self.jwks_url)

    @property
    def local(self) -> bool:
        return self.mode == "local"


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
    mode = os.getenv("OOPSNOTE_AUTH_MODE", "oidc").strip().lower() or "oidc"
    if mode not in {"oidc", "local"}:
        raise RuntimeError("OOPSNOTE_AUTH_MODE must be 'oidc' or 'local'")
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
        raise AuthenticationError("Authentication service is temporarily unavailable", status_code=503) from error
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


def require_admin_request(request: Request) -> AuthenticatedUser | None:
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
    if not config.enabled:
        host = (request.client.host if request.client else "").strip().lower()
        if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise AuthenticationError("Administrator access requires OIDC outside loopback", status_code=403)
        return None
    user = getattr(request.state, "auth", None)
    if not isinstance(user, AuthenticatedUser):
        raise AuthenticationError("Missing authenticated user")
    subjects = {value.strip() for value in os.getenv("OOPSNOTE_ADMIN_SUBJECTS", "").split(",") if value.strip()}
    roles = {value.strip() for value in os.getenv("OOPSNOTE_ADMIN_ROLES", "admin").split(",") if value.strip()}
    if user.subject in subjects or _claim_values(user.claims).intersection(roles):
        return user
    raise AuthenticationError("Administrator role is required", status_code=403)
