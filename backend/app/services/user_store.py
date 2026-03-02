from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..auth.security import hash_password, verify_password
from ..config import load_app_config
from ..models.auth import UserRecord


class UserStore:
    def __init__(self, users_path: Path | None = None) -> None:
        base = Path(__file__).resolve().parents[2] / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.users_path = users_path or (base / "users.json")
        self._lock = threading.Lock()

    def get_user(self, username: str) -> UserRecord | None:
        target = (username or "").strip()
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

    def _seed_default_admin(self) -> list[UserRecord]:
        config = load_app_config()
        username = (config.auth_admin_username or "admin").strip() or "admin"
        password = config.auth_admin_password or "admin123456"
        admin = UserRecord(
            username=username,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
            created_at=datetime.now(timezone.utc),
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
