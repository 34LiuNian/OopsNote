"""Security configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


_RUNTIME_JWT_SECRET: str | None = None


def _resolve_jwt_secret() -> str:
    global _RUNTIME_JWT_SECRET

    jwt_secret = os.getenv("JWT_SECRET")
    if jwt_secret:
        return jwt_secret

    if _RUNTIME_JWT_SECRET:
        return _RUNTIME_JWT_SECRET

    import secrets

    _RUNTIME_JWT_SECRET = secrets.token_urlsafe(32)
    print(f"⚠️  WARNING: JWT_SECRET not set. Auto-generated (process-local): {_RUNTIME_JWT_SECRET[:8]}...")
    print("⚠️  Please set JWT_SECRET environment variable for production!")
    return _RUNTIME_JWT_SECRET


@dataclass(frozen=True)
class SecurityConfig:
    """Security-related configuration."""

    # JWT settings
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Login protection
    max_login_attempts: int = 20
    lockout_duration_minutes: int = 10

    # Password policy
    password_min_length: int = 8
    password_require_mixed_case: bool = False
    password_require_digit: bool = True
    password_require_special: bool = False

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        """Load security configuration from environment variables."""
        jwt_secret = _resolve_jwt_secret()
        
        # Validate JWT secret length
        if len(jwt_secret) < 32:
            import warnings
            warnings.warn(
                "JWT_SECRET is less than 32 characters. Consider using a stronger secret.",
                UserWarning,
                stacklevel=2
            )

        return cls(
            jwt_secret=jwt_secret,
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            jwt_access_token_expire_minutes=int(
                os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
            ),
            jwt_refresh_token_expire_days=int(
                os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
            ),
            max_login_attempts=int(os.getenv("MAX_LOGIN_ATTEMPTS", "20")),
            lockout_duration_minutes=int(os.getenv("LOCKOUT_DURATION_MINUTES", "10")),
            password_min_length=int(os.getenv("PASSWORD_MIN_LENGTH", "8")),
            password_require_mixed_case=os.getenv(
                "PASSWORD_REQUIRE_MIXED_CASE", "false"
            ).lower() == "true",
            password_require_digit=os.getenv(
                "PASSWORD_REQUIRE_DIGIT", "true"
            ).lower() == "true",
            password_require_special=os.getenv(
                "PASSWORD_REQUIRE_SPECIAL", "false"
            ).lower() == "true",
        )
