"""Atomic run admission and quota settlement in the control-plane database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from oopsnote.core import RunPurpose, WorkspaceId

from .database import ControlDatabase


class QuotaError(RuntimeError):
    """A run cannot be admitted under the workspace policy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RunAdmission:
    workspace_id: WorkspaceId
    run_id: str
    reservation_id: str
    created: bool
    reservation_state: str


class QuotaService:
    """Own the transactional boundary for run creation and usage settlement."""

    def __init__(self, database: ControlDatabase) -> None:
        self.database = database

    def admit_run(
        self,
        workspace_id: WorkspaceId,
        *,
        task_id: str,
        purpose: RunPurpose,
        idempotency_key: str,
        units: int = 1,
        run_id: str | None = None,
        retry_of: str | None = None,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> RunAdmission:
        workspace = WorkspaceId.parse(workspace_id)
        if not task_id.strip():
            raise ValueError("task_id must not be empty")
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must not be empty")
        if units < 1:
            raise ValueError("units must be positive")
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        usage_day = timestamp.date().isoformat()
        namespaced_key = f"{workspace}:{idempotency_key.strip()}"
        requested_run_id = run_id or str(uuid4())

        self.database.migrate()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    """
                    SELECT r.id AS run_id, r.quota_reservation_id,
                           u.state AS reservation_state
                    FROM usage_reservations AS u
                    JOIN runs AS r ON r.quota_reservation_id = u.id
                    WHERE u.idempotency_key = ?
                    ORDER BY r.queued_at DESC
                    LIMIT 1
                    """,
                    (namespaced_key,),
                ).fetchone()
                if existing is not None:
                    connection.commit()
                    return RunAdmission(
                        workspace,
                        str(existing["run_id"]),
                        str(existing["quota_reservation_id"]),
                        False,
                        str(existing["reservation_state"]),
                    )

                policy = connection.execute(
                    "SELECT daily_success_limit FROM quota_policies WHERE workspace_id = ?",
                    (str(workspace),),
                ).fetchone()
                if policy is None:
                    raise QuotaError("workspace_not_registered", "Workspace is not registered")

                used = connection.execute(
                    """
                    SELECT COALESCE(SUM(units), 0)
                    FROM usage_reservations
                    WHERE workspace_id = ?
                      AND usage_day_utc = ?
                      AND state IN ('reserved', 'consumed')
                    """,
                    (str(workspace), usage_day),
                ).fetchone()[0]
                if int(used) + units > int(policy["daily_success_limit"]):
                    raise QuotaError("daily_limit_exceeded", "Daily usage limit exceeded")

                reservation_id = str(uuid4())
                connection.execute(
                    """
                    INSERT INTO usage_reservations(
                        id, workspace_id, operation, units, idempotency_key,
                        state, root_run_id, usage_day_utc, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'reserved', ?, ?, ?)
                    """,
                    (
                        reservation_id,
                        str(workspace),
                        purpose.value,
                        units,
                        namespaced_key,
                        requested_run_id,
                        usage_day,
                        timestamp.isoformat(),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO runs(
                        id, workspace_id, task_id, purpose, status,
                        retry_of, quota_reservation_id, queued_at, payload_json
                    ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
                    """,
                    (
                        requested_run_id,
                        str(workspace),
                        task_id,
                        purpose.value,
                        retry_of,
                        reservation_id,
                        timestamp.isoformat(),
                        _json_payload(payload),
                    ),
                )
                connection.commit()
            except (sqlite3.Error, QuotaError):
                connection.rollback()
                raise
        return RunAdmission(workspace, requested_run_id, reservation_id, True, "reserved")

    def start_run(
        self,
        workspace_id: WorkspaceId,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> str:
        """Atomically claim one execution slot for a persisted queued run."""
        workspace = WorkspaceId.parse(workspace_id)
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        self.database.migrate()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                run = connection.execute(
                    "SELECT workspace_id, status FROM runs WHERE id = ?",
                    (run_id,),
                ).fetchone()
                if run is None or run["workspace_id"] != str(workspace):
                    raise KeyError(run_id)
                if run["status"] == "running":
                    connection.commit()
                    return "running"
                if run["status"] != "queued":
                    raise QuotaError("run_not_startable", "Only queued runs can start")
                policy = connection.execute(
                    "SELECT max_concurrent_runs FROM quota_policies WHERE workspace_id = ?",
                    (str(workspace),),
                ).fetchone()
                if policy is None:
                    raise QuotaError("workspace_not_registered", "Workspace is not registered")
                active = connection.execute(
                    "SELECT COUNT(*) FROM runs WHERE workspace_id = ? AND status = 'running'",
                    (str(workspace),),
                ).fetchone()[0]
                if int(active) >= int(policy["max_concurrent_runs"]):
                    raise QuotaError("concurrency_exceeded", "Concurrent run limit exceeded")
                connection.execute(
                    "UPDATE runs SET status = 'running', started_at = COALESCE(started_at, ?) WHERE id = ?",
                    (timestamp, run_id),
                )
                connection.commit()
            except (sqlite3.Error, QuotaError, KeyError):
                connection.rollback()
                raise
        return "running"

    def defer_run(self, workspace_id: WorkspaceId, run_id: str) -> str:
        """Release an execution slot while preserving the queued reservation."""
        workspace = WorkspaceId.parse(workspace_id)
        self.database.migrate()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                run = connection.execute(
                    "SELECT workspace_id, status FROM runs WHERE id = ?",
                    (run_id,),
                ).fetchone()
                if run is None or run["workspace_id"] != str(workspace):
                    raise KeyError(run_id)
                if run["status"] == "queued":
                    connection.commit()
                    return "queued"
                if run["status"] != "running":
                    raise QuotaError("run_not_deferable", "Only running runs can be deferred")
                connection.execute("UPDATE runs SET status = 'queued' WHERE id = ?", (run_id,))
                connection.commit()
            except (sqlite3.Error, QuotaError, KeyError):
                connection.rollback()
                raise
        return "queued"

    def settle_run(
        self,
        workspace_id: WorkspaceId,
        run_id: str,
        *,
        status: str,
        now: datetime | None = None,
        reason: str | None = None,
    ) -> str:
        workspace = WorkspaceId.parse(workspace_id)
        if status not in {"completed", "failed", "cancelled", "timed_out"}:
            raise ValueError("status must be a terminal run status")
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        reservation_state = "consumed" if status == "completed" else "released"

        self.database.migrate()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT workspace_id, status, quota_reservation_id
                FROM runs WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None or row["workspace_id"] != str(workspace):
                connection.rollback()
                raise KeyError(run_id)
            if row["status"] in {"completed", "failed", "cancelled", "timed_out"}:
                connection.commit()
                return str(row["status"])
            connection.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
                (status, timestamp, run_id),
            )
            connection.execute(
                """
                UPDATE usage_reservations
                SET state = ?, finalized_at = ?, reason = ?
                WHERE id = ? AND state = 'reserved'
                """,
                (reservation_state, timestamp, reason, row["quota_reservation_id"]),
            )
            connection.commit()
            return status

    def admit_retry(
        self,
        workspace_id: WorkspaceId,
        *,
        previous_run_id: str,
        task_id: str,
        purpose: RunPurpose,
        run_id: str,
        payload: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> RunAdmission:
        """Reopen a released reservation for a transient retry exactly once."""
        workspace = WorkspaceId.parse(workspace_id)
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.database.migrate()
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                previous = connection.execute(
                    """
                    SELECT r.workspace_id, r.task_id, r.purpose,
                           u.id AS reservation_id, u.state, u.units,
                           u.usage_day_utc
                    FROM runs AS r
                    JOIN usage_reservations AS u ON u.id = r.quota_reservation_id
                    WHERE r.id = ?
                    """,
                    (previous_run_id,),
                ).fetchone()
                if previous is None or previous["workspace_id"] != str(workspace):
                    raise QuotaError("retry_not_found", "Retry source run is not in this workspace")
                if previous["state"] != "released":
                    raise QuotaError("retry_not_eligible", "Only released reservations can be retried")
                if previous["task_id"] != task_id or previous["purpose"] != purpose.value:
                    raise QuotaError("retry_not_eligible", "Retry must preserve task and purpose")
                policy = connection.execute(
                    "SELECT daily_success_limit FROM quota_policies WHERE workspace_id = ?",
                    (str(workspace),),
                ).fetchone()
                if policy is None:
                    raise QuotaError("workspace_not_registered", "Workspace is not registered")
                usage_day = timestamp.date().isoformat()
                used = connection.execute(
                    """
                    SELECT COALESCE(SUM(units), 0)
                    FROM usage_reservations
                    WHERE workspace_id = ? AND usage_day_utc = ? AND state IN ('reserved', 'consumed')
                    """,
                    (str(workspace), usage_day),
                ).fetchone()[0]
                if int(used) + int(previous["units"]) > int(policy["daily_success_limit"]):
                    raise QuotaError("daily_limit_exceeded", "Daily usage limit exceeded")
                connection.execute(
                    """
                    UPDATE usage_reservations
                    SET state = 'reserved', usage_day_utc = ?, finalized_at = NULL, reason = NULL
                    WHERE id = ? AND state = 'released'
                    """,
                    (usage_day, previous["reservation_id"]),
                )
                connection.execute(
                    """
                    INSERT INTO runs(
                        id, workspace_id, task_id, purpose, status,
                        retry_of, quota_reservation_id, queued_at, payload_json
                    ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        str(workspace),
                        task_id,
                        purpose.value,
                        previous_run_id,
                        previous["reservation_id"],
                        timestamp.isoformat(),
                        _json_payload(payload),
                    ),
                )
                connection.commit()
            except (sqlite3.Error, QuotaError):
                connection.rollback()
                raise
        return RunAdmission(
            workspace,
            run_id,
            str(previous["reservation_id"]),
            True,
            "reserved",
        )


def _json_payload(payload: dict[str, Any] | None) -> str:
    import json

    return json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))
