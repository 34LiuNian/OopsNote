from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth.deps import require_admin
from ..models.auth import (
    AdminPasswordResetRequest,
    AdminUserUpdateRequest,
    AuthMeResponse,
    UserListResponse,
    UserPublic,
)
from ..services.user_store import user_store

router = APIRouter(dependencies=[Depends(require_admin)])


def _to_public(user) -> UserPublic:
    return UserPublic(
        username=user.username,
        role=user.role,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
    )


@router.get("/users", response_model=UserListResponse)
def list_users(query: str | None = Query(default=None)) -> UserListResponse:
    users = user_store.list_users(query=query)
    return UserListResponse(items=[_to_public(item) for item in users])


@router.patch("/users/{username}", response_model=AuthMeResponse)
def update_user(
    username: str,
    payload: AdminUserUpdateRequest,
) -> AuthMeResponse:
    try:
        user = user_store.admin_update_user(
            username=username,
            role=payload.role,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthMeResponse(user=_to_public(user))


@router.patch("/users/{username}/password", response_model=AuthMeResponse)
def reset_user_password(
    username: str,
    payload: AdminPasswordResetRequest,
) -> AuthMeResponse:
    try:
        user = user_store.admin_reset_password(
            username=username,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthMeResponse(user=_to_public(user))
