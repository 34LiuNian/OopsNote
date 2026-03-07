from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.deps import require_admin, require_user
from ..auth.security import create_access_token, create_refresh_token, decode_refresh_token
from ..config import SecurityConfig, load_app_config
from ..models.auth import (
    AuthMeResponse,
    AuthTokenResponse,
    LoginRequest,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
    RegistrationSettingsResponse,
    RegistrationSettingsUpdateRequest,
    UserPublic,
)
from .deps import get_auth_settings_service
from ..services.user_store import user_store
from ..services.login_store import login_attempt_store

router = APIRouter()


def _to_public(user) -> UserPublic:
    return UserPublic(
        username=user.username,
        role=user.role,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
    )


@router.post("/auth/login", response_model=AuthTokenResponse)
def login(payload: LoginRequest) -> AuthTokenResponse:
    config = load_app_config()
    security_config = SecurityConfig.from_env()
    
    # Check if account is locked
    if login_attempt_store.is_locked(payload.username):
        remaining = login_attempt_store.get_lock_remaining(payload.username)
        raise HTTPException(
            status_code=429,
            detail=f"账号已被锁定，请{remaining}分钟后再试"
        )
    
    user = user_store.authenticate(payload.username, payload.password)
    if user is None:
        # Record failed attempt
        login_attempt_store.record_failed_attempt(
            payload.username,
            max_attempts=security_config.max_login_attempts,
            lockout_minutes=security_config.lockout_duration_minutes,
        )
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # Clear failed attempts on success
    login_attempt_store.clear_attempts(payload.username)
    
    # Create access token
    access_token, access_expires_in = create_access_token(
        subject=user.username,
        role=user.role,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        expires_minutes=config.jwt_access_token_expire_minutes,
    )
    
    # Create refresh token
    refresh_token, refresh_expires_in = create_refresh_token(
        subject=user.username,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        expires_days=security_config.jwt_refresh_token_expire_days,
    )
    
    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=access_expires_in,
        refresh_expires_in=refresh_expires_in,
        user=_to_public(user),
    )


@router.post("/auth/refresh", response_model=RefreshTokenResponse)
def refresh_token(payload: RefreshTokenRequest) -> RefreshTokenResponse:
    """Refresh access token using refresh token."""
    config = load_app_config()
    
    try:
        refresh_payload = decode_refresh_token(
            payload.refresh_token,
            secret=config.jwt_secret,
            algorithm=config.jwt_algorithm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    
    username = str(refresh_payload.get("sub") or "").strip()
    if not username:
        raise HTTPException(status_code=401, detail="无效的刷新凭证")
    
    # Verify user still exists and is active
    user = user_store.get_user(username)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    
    # Create new access token
    access_token, expires_in = create_access_token(
        subject=user.username,
        role=user.role,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        expires_minutes=config.jwt_access_token_expire_minutes,
    )
    
    return RefreshTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post("/auth/register", response_model=AuthTokenResponse)
def register(payload: RegisterRequest, request: Request) -> AuthTokenResponse:
    config = load_app_config()
    security_config = SecurityConfig.from_env()
    auth_settings = get_auth_settings_service(request)
    registration = auth_settings.load_registration()
    if not registration.enabled:
        raise HTTPException(status_code=403, detail="当前未开放注册")

    try:
        user = user_store.create_user(
            username=payload.username,
            password=payload.password,
            nickname=payload.nickname,
            avatar_url=payload.avatar_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Create access token
    access_token, access_expires_in = create_access_token(
        subject=user.username,
        role=user.role,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        expires_minutes=config.jwt_access_token_expire_minutes,
    )
    
    # Create refresh token
    refresh_token, refresh_expires_in = create_refresh_token(
        subject=user.username,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        expires_days=security_config.jwt_refresh_token_expire_days,
    )

    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=access_expires_in,
        refresh_expires_in=refresh_expires_in,
        user=_to_public(user),
    )


@router.get("/auth/me", response_model=AuthMeResponse)
def me(current_user: UserPublic = Depends(require_user)) -> AuthMeResponse:
    user = user_store.get_user(current_user.username)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return AuthMeResponse(user=_to_public(user))


@router.get(
    "/auth/registration",
    response_model=RegistrationSettingsResponse,
)
def get_registration_enabled(request: Request) -> RegistrationSettingsResponse:
    auth_settings = get_auth_settings_service(request)
    settings = auth_settings.load_registration()
    return RegistrationSettingsResponse(enabled=settings.enabled)


@router.get(
    "/settings/auth-registration",
    response_model=RegistrationSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def get_registration_settings(request: Request) -> RegistrationSettingsResponse:
    auth_settings = get_auth_settings_service(request)
    settings = auth_settings.load_registration()
    return RegistrationSettingsResponse(enabled=settings.enabled)


@router.put(
    "/settings/auth-registration",
    response_model=RegistrationSettingsResponse,
    dependencies=[Depends(require_admin)],
)
def update_registration_settings(
    payload: RegistrationSettingsUpdateRequest,
    request: Request,
) -> RegistrationSettingsResponse:
    auth_settings = get_auth_settings_service(request)
    settings = auth_settings.save_registration(payload.enabled)
    return RegistrationSettingsResponse(enabled=settings.enabled)
