from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import load_app_config
from ..models.auth import UserPublic
from ..services.user_store import user_store
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserPublic:
    config = load_app_config()

    if not config.auth_enabled:
        return UserPublic(username="local-dev", role="admin")

    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")

    try:
        payload = decode_access_token(
            credentials.credentials,
            secret=config.jwt_secret,
            algorithm=config.jwt_algorithm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    username = str(payload.get("sub") or "").strip()
    if not username:
        raise HTTPException(status_code=401, detail="无效的登录凭证")

    role = str(payload.get("role") or "member").strip() or "member"

    user = user_store.get_user(username)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    return UserPublic(username=user.username, role=role if role in {"admin", "member"} else user.role)


def require_admin(current_user: UserPublic = Depends(require_user)) -> UserPublic:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权限执行此操作")
    return current_user
