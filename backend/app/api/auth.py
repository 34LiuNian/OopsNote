from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth.deps import require_user
from ..auth.security import create_access_token
from ..config import load_app_config
from ..models.auth import AuthMeResponse, AuthTokenResponse, LoginRequest, UserPublic
from ..services.user_store import user_store

router = APIRouter()


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
        user=UserPublic(username=user.username, role=user.role),
    )


@router.get("/auth/me", response_model=AuthMeResponse)
def me(current_user: UserPublic = Depends(require_user)) -> AuthMeResponse:
    return AuthMeResponse(user=current_user)
