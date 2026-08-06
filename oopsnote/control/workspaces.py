"""Immutable auth-user to workspace registration."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from oopsnote.core.workspace import Principal, UserRole, WorkspaceContext, WorkspaceId

from .database import ControlDatabase


class WorkspaceRegistry:
    """Own the single durable mapping from a Better Auth user to a workspace."""

    def __init__(
        self,
        database: ControlDatabase,
        storage_root: Path,
        *,
        default_daily_success_limit: int = 20,
        default_max_concurrent_runs: int = 1,
    ) -> None:
        if default_daily_success_limit < 0:
            raise ValueError("default_daily_success_limit must be non-negative")
        if default_max_concurrent_runs < 1:
            raise ValueError("default_max_concurrent_runs must be at least 1")
        self.database = database
        self.storage_root = Path(storage_root)
        self.default_daily_success_limit = default_daily_success_limit
        self.default_max_concurrent_runs = default_max_concurrent_runs

    def get_or_create(self, principal: Principal) -> WorkspaceContext:
        """Return one stable workspace, including under repeated/concurrent calls."""
        self.database.migrate()
        now = datetime.now(timezone.utc).isoformat()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT id FROM workspaces WHERE auth_user_id = ?",
                    (principal.user_id,),
                ).fetchone()
                if row is None:
                    workspace_id = WorkspaceId.new()
                    connection.execute(
                        "INSERT INTO workspaces(id, auth_user_id, created_at) VALUES (?, ?, ?)",
                        (str(workspace_id), principal.user_id, now),
                    )
                    connection.execute(
                        """
                        INSERT INTO quota_policies(
                            workspace_id, daily_success_limit, max_concurrent_runs, updated_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            str(workspace_id),
                            self.default_daily_success_limit,
                            self.default_max_concurrent_runs,
                            now,
                        ),
                    )
                else:
                    workspace_id = WorkspaceId.parse(row["id"])
                connection.commit()
            except (sqlite3.Error, ValueError):
                connection.rollback()
                raise
        return WorkspaceContext._from_registry(self.storage_root, workspace_id)

    def require(self, principal: Principal) -> WorkspaceContext:
        """Resolve an existing mapping without silently creating an account."""
        self.database.migrate()
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT id FROM workspaces WHERE auth_user_id = ?",
                (principal.user_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"No workspace is registered for auth user {principal.user_id}")
        return WorkspaceContext._from_registry(
            self.storage_root,
            WorkspaceId.parse(row["id"]),
        )

    def provision(
        self,
        auth_user_id: str,
        *,
        daily_success_limit: int | None = None,
        max_concurrent_runs: int | None = None,
    ) -> WorkspaceContext:
        """Create the application workspace for a Better Auth user and set policy."""
        user_id = auth_user_id.strip()
        if not user_id:
            raise ValueError("auth_user_id must not be empty")
        workspace = self.get_or_create(
            Principal(user_id=user_id, role=UserRole.USER),
        )
        if daily_success_limit is None and max_concurrent_runs is None:
            return workspace
        self.update_quota(
            user_id,
            daily_success_limit=daily_success_limit,
            max_concurrent_runs=max_concurrent_runs,
        )
        return workspace

    def update_quota(
        self,
        auth_user_id: str,
        *,
        daily_success_limit: int | None = None,
        max_concurrent_runs: int | None = None,
    ) -> dict[str, int]:
        if daily_success_limit is not None and daily_success_limit < 0:
            raise ValueError("daily_success_limit must be non-negative")
        if max_concurrent_runs is not None and max_concurrent_runs < 1:
            raise ValueError("max_concurrent_runs must be at least 1")
        self.database.migrate()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT q.daily_success_limit, q.max_concurrent_runs
                FROM workspaces AS w
                JOIN quota_policies AS q ON q.workspace_id = w.id
                WHERE w.auth_user_id = ?
                """,
                (auth_user_id.strip(),),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(auth_user_id)
            daily = int(row["daily_success_limit"] if daily_success_limit is None else daily_success_limit)
            concurrent = int(row["max_concurrent_runs"] if max_concurrent_runs is None else max_concurrent_runs)
            connection.execute(
                """
                UPDATE quota_policies
                SET daily_success_limit = ?, max_concurrent_runs = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE workspace_id = (SELECT id FROM workspaces WHERE auth_user_id = ?)
                """,
                (daily, concurrent, auth_user_id.strip()),
            )
            connection.commit()
        return {"daily_success_limit": daily, "max_concurrent_runs": concurrent}

    def quota_summary(self, auth_user_id: str, *, usage_day_utc: str | None = None) -> dict[str, object] | None:
        self.database.migrate()
        day = usage_day_utc or datetime.now(timezone.utc).date().isoformat()
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT w.id AS workspace_id, q.daily_success_limit, q.max_concurrent_runs,
                       (SELECT COUNT(*) FROM runs r WHERE r.workspace_id = w.id AND r.status IN ('queued', 'running')) AS active_runs,
                       (SELECT COALESCE(SUM(u.units), 0) FROM usage_reservations u
                        WHERE u.workspace_id = w.id AND u.usage_day_utc = ? AND u.state IN ('reserved', 'consumed')) AS used_units
                FROM workspaces AS w
                JOIN quota_policies AS q ON q.workspace_id = w.id
                WHERE w.auth_user_id = ?
                """,
                (day, auth_user_id.strip()),
            ).fetchone()
        if row is None:
            return None
        return {
            "workspace_id": str(row["workspace_id"]),
            "daily_success_limit": int(row["daily_success_limit"]),
            "max_concurrent_runs": int(row["max_concurrent_runs"]),
            "active_runs": int(row["active_runs"]),
            "used_units": int(row["used_units"]),
            "usage_day_utc": day,
        }

    def quota_summaries(self, auth_user_ids: list[str], *, usage_day_utc: str | None = None) -> dict[str, dict[str, object] | None]:
        return {
            user_id: self.quota_summary(user_id, usage_day_utc=usage_day_utc)
            for user_id in dict.fromkeys(user_id.strip() for user_id in auth_user_ids if user_id.strip())
        }

    def mark_legacy_imported(self, auth_user_id: str) -> None:
        self.database.migrate()
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE workspaces
                SET legacy_imported_at = COALESCE(legacy_imported_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                WHERE auth_user_id = ?
                """,
                (auth_user_id.strip(),),
            )
            connection.commit()
