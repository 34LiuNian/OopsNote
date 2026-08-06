"""Immutable auth-user to workspace registration."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from oopsnote.core.workspace import Principal, WorkspaceContext, WorkspaceId

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
