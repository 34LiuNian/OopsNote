from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.deps import require_admin, require_user
from ..auth.security import create_access_token
from ..config import load_app_config
from ..models.auth import (
    AuthMeResponse,
    AuthTokenResponse,
    LoginRequest,
    RegisterRequest,
    RegistrationSettingsResponse,
    RegistrationSettingsUpdateRequest,
    UserPublic,
)
from .deps import get_auth_settings_service
from ..services.user_store import user_store

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
    user = user_store.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token, expires_in = create_access_token(
        subject=user.username,
        role=user.role,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        expires_minutes=config.jwt_access_token_expire_minutes,
    )
    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=_to_public(user),
    )


@router.post("/auth/register", response_model=AuthTokenResponse)
def register(payload: RegisterRequest, request: Request) -> AuthTokenResponse:
    config = load_app_config()
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

    token, expires_in = create_access_token(
        subject=user.username,
        role=user.role,
        secret=config.jwt_secret,
        algorithm=config.jwt_algorithm,
        expires_minutes=config.jwt_access_token_expire_minutes,
    )
    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
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
