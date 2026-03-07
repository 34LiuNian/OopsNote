from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..auth.security import hash_password, verify_password
from ..config import load_app_config
from ..models.auth import UserRecord


_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,32}$")


def _normalize_username(username: str) -> str:
    return (username or "").strip()


def validate_username(username: str) -> str:
    normalized = _normalize_username(username)
    if not normalized:
        raise ValueError("用户名不能为空")
    if not _USERNAME_PATTERN.match(normalized):
        raise ValueError("用户名需为3-32位，且仅支持字母、数字、._-")
    return normalized


def validate_password(password: str) -> str:
    raw = password or ""
    if len(raw) < 8:
        raise ValueError("密码至少8位")
    if not any(ch.isalpha() for ch in raw) or not any(ch.isdigit() for ch in raw):
        raise ValueError("密码需同时包含字母和数字")
    return raw


class UserStore:
    def __init__(self, users_path: Path | None = None) -> None:
        base = Path(__file__).resolve().parents[2] / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.users_path = users_path or (base / "users.json")
        self._lock = threading.Lock()

    def get_user(self, username: str) -> UserRecord | None:
        target = _normalize_username(username)
        if not target:
            return None
        users = self._load_users()
        for user in users:
            if user.username == target:
                return user
        return None

    def authenticate(self, username: str, password: str) -> UserRecord | None:
        user = self.get_user(username)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def list_users(self, *, query: str | None = None) -> list[UserRecord]:
        users = self._load_users()
        if not query:
            return sorted(users, key=lambda item: item.created_at, reverse=True)
        target = query.strip().lower()
        if not target:
            return sorted(users, key=lambda item: item.created_at, reverse=True)
        filtered = [
            item
            for item in users
            if target in item.username.lower()
            or target in (item.nickname or "").lower()
        ]
        return sorted(filtered, key=lambda item: item.created_at, reverse=True)

    def create_user(
        self,
        *,
        username: str,
        password: str,
        role: str = "member",
        nickname: str | None = None,
        avatar_url: str | None = None,
    ) -> UserRecord:
        normalized_username = validate_username(username)
        validated_password = validate_password(password)
        normalized_nickname = (nickname or "").strip() or None
        normalized_avatar = (avatar_url or "").strip() or None
        now = datetime.now(timezone.utc)
        with self._lock:
            users = self._load_users_unlocked()
            if any(item.username == normalized_username for item in users):
                raise ValueError("用户名已存在")
            user = UserRecord(
                username=normalized_username,
                password_hash=hash_password(validated_password),
                role="admin" if role == "admin" else "member",
                is_active=True,
                nickname=normalized_nickname,
                avatar_url=normalized_avatar,
                created_at=now,
                updated_at=now,
            )
            users.append(user)
            self._write_users_unlocked(users)
            return user

    def update_profile(
        self,
        *,
        username: str,
        new_username: str | None = None,
        nickname: str | None = None,
        avatar_url: str | None = None,
    ) -> UserRecord:
        target_username = _normalize_username(username)
        normalized_new_username = (
            validate_username(new_username) if new_username is not None else None
        )
        normalized_nickname = nickname.strip() if nickname is not None else None
        normalized_avatar = avatar_url.strip() if avatar_url is not None else None
        now = datetime.now(timezone.utc)
        with self._lock:
            users = self._load_users_unlocked()
            target_index = -1
            for idx, item in enumerate(users):
                if item.username == target_username:
                    target_index = idx
                    break
            if target_index < 0:
                raise ValueError("用户不存在")

            current = users[target_index]
            final_username = normalized_new_username or current.username
            if final_username != current.username and any(
                item.username == final_username for item in users
            ):
                raise ValueError("用户名已存在")

            users[target_index] = current.model_copy(
                update={
                    "username": final_username,
                    "nickname": (
                        normalized_nickname
                        if normalized_nickname is not None
                        else current.nickname
                    ),
                    "avatar_url": (
                        normalized_avatar
                        if normalized_avatar is not None
                        else current.avatar_url
                    ),
                    "updated_at": now,
                }
            )
            self._write_users_unlocked(users)
            return users[target_index]

    def update_password(
        self,
        *,
        username: str,
        current_password: str,
        new_password: str,
    ) -> UserRecord:
        validated = validate_password(new_password)
        target_username = _normalize_username(username)
        now = datetime.now(timezone.utc)
        with self._lock:
            users = self._load_users_unlocked()
            target_index = -1
            for idx, item in enumerate(users):
                if item.username == target_username:
                    target_index = idx
                    break
            if target_index < 0:
                raise ValueError("用户不存在")
            current = users[target_index]
            if not verify_password(current_password, current.password_hash):
                raise ValueError("当前密码错误")
            users[target_index] = current.model_copy(
                update={
                    "password_hash": hash_password(validated),
                    "updated_at": now,
                }
            )
            self._write_users_unlocked(users)
            return users[target_index]

    def admin_reset_password(self, *, username: str, new_password: str) -> UserRecord:
        validated = validate_password(new_password)
        target_username = _normalize_username(username)
        now = datetime.now(timezone.utc)
        with self._lock:
            users = self._load_users_unlocked()
            target_index = -1
            for idx, item in enumerate(users):
                if item.username == target_username:
                    target_index = idx
                    break
            if target_index < 0:
                raise ValueError("用户不存在")
            current = users[target_index]
            users[target_index] = current.model_copy(
                update={
                    "password_hash": hash_password(validated),
                    "updated_at": now,
                }
            )
            self._write_users_unlocked(users)
            return users[target_index]

    def admin_update_user(
        self,
        *,
        username: str,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> UserRecord:
        target_username = _normalize_username(username)
        now = datetime.now(timezone.utc)
        with self._lock:
            users = self._load_users_unlocked()
            target_index = -1
            admin_count = sum(
                1 for item in users if item.role == "admin" and item.is_active
            )
            for idx, item in enumerate(users):
                if item.username == target_username:
                    target_index = idx
                    break
            if target_index < 0:
                raise ValueError("用户不存在")

            current = users[target_index]
            next_role = role if role in {"admin", "member"} else current.role
            next_active = bool(is_active) if is_active is not None else current.is_active

            if current.role == "admin" and current.is_active:
                if (next_role != "admin" or not next_active) and admin_count <= 1:
                    raise ValueError("至少需要保留一个可用管理员")

            users[target_index] = current.model_copy(
                update={
                    "role": next_role,
                    "is_active": next_active,
                    "updated_at": now,
                }
            )
            self._write_users_unlocked(users)
            return users[target_index]

    def _seed_default_admin(self) -> list[UserRecord]:
        config = load_app_config()
        username = (config.auth_admin_username or "admin").strip() or "admin"
        password = config.auth_admin_password or "admin123456"
        now = datetime.now(timezone.utc)
        admin = UserRecord(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            nickname="管理员",
            created_at=now,
            updated_at=now,
        )
        return [admin]

    def _load_users_unlocked(self) -> list[UserRecord]:
        if not self.users_path.exists():
            users = self._seed_default_admin()
            self._write_users_unlocked(users)
            return users

        raw = json.loads(self.users_path.read_text(encoding="utf-8"))
        items = raw.get("items", []) if isinstance(raw, dict) else []
        users: list[UserRecord] = []
        for item in items:
            try:
                users.append(UserRecord.model_validate(item))
            except Exception:
                continue

        if not users:
            users = self._seed_default_admin()
            self._write_users_unlocked(users)
        return users

    def _load_users(self) -> list[UserRecord]:
        with self._lock:
            return self._load_users_unlocked()

    def _write_users_unlocked(self, users: list[UserRecord]) -> None:
        payload = {
            "items": [u.model_dump(mode="json") for u in users],
        }
        self.users_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


user_store = UserStore()
