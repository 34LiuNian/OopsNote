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

    @property
    def enabled(self) -> bool:
        return bool(self.issuer and self.audience and self.jwks_url)


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
    issuer = os.getenv("OOPSNOTE_AUTH_ISSUER", "").strip().rstrip("/")
    audience = os.getenv("OOPSNOTE_AUTH_AUDIENCE", "").strip()
    jwks_url = os.getenv("OOPSNOTE_AUTH_JWKS_URL", "").strip()
    if issuer and not jwks_url:
        jwks_url = f"{issuer}/.well-known/jwks.json"
    return AuthConfig(
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
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
