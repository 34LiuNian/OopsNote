from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

_PWD_ALGO = "pbkdf2_sha256"
_PWD_ITERATIONS = 390000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PWD_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"{_PWD_ALGO}${_PWD_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        algo, iterations_raw, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algo != _PWD_ALGO:
            return False
        iterations = int(iterations_raw)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def create_access_token(
    *,
    subject: str,
    role: str,
    secret: str,
    algorithm: str,
    expires_minutes: int,
) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=max(1, int(expires_minutes)))
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm=algorithm)
    return token, int((expire - now).total_seconds())


def decode_access_token(token: str, *, secret: str, algorithm: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
    except JWTError as exc:
        raise ValueError("无效或已过期的登录凭证") from exc
    if not isinstance(payload, dict):
        raise ValueError("无效的登录凭证")
    return payload
