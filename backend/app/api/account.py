from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth.deps import require_user
from ..models.auth import AuthMeResponse, PasswordUpdateRequest, UserProfileUpdateRequest, UserPublic
from ..services.user_store import user_store

router = APIRouter(dependencies=[Depends(require_user)])


def _to_public(user) -> UserPublic:
    return UserPublic(
        username=user.username,
        role=user.role,
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
    )


@router.get("/account/me", response_model=AuthMeResponse)
def get_account_me(current_user: UserPublic = Depends(require_user)) -> AuthMeResponse:
    user = user_store.get_user(current_user.username)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return AuthMeResponse(user=_to_public(user))


@router.patch("/account/me", response_model=AuthMeResponse)
def update_account_me(
    payload: UserProfileUpdateRequest,
    current_user: UserPublic = Depends(require_user),
) -> AuthMeResponse:
    try:
        user = user_store.update_profile(
            username=current_user.username,
            new_username=payload.username,
            nickname=payload.nickname,
            avatar_url=payload.avatar_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthMeResponse(user=_to_public(user))


@router.patch("/account/password")
def update_account_password(
    payload: PasswordUpdateRequest,
    current_user: UserPublic = Depends(require_user),
) -> dict[str, str]:
    try:
        user_store.update_password(
            username=current_user.username,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "密码修改成功"}
