from __future__ import annotations

from datetime import datetime, timezone

from oopsnote.control import ControlDatabase
from oopsnote.core import RunStatus, TaskRecord, TaskRun
from scripts.migrate_multitenancy import apply_migration, build_report


def test_migration_dry_run_and_apply_preserve_legacy_tree_and_import_history(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "assets").mkdir()
    (storage / "runs").mkdir()
    (storage / "settings").mkdir()
    task = TaskRecord(id="task-legacy", subject="legacy")
    (storage / f"{task.id}.json").write_text(task.model_dump_json(), encoding="utf-8")
    run = TaskRun(
        id="run-legacy",
        task_id=task.id,
        status=RunStatus.COMPLETED,
        ended_at=datetime.now(timezone.utc),
    )
    (storage / "runs" / f"{run.id}.json").write_text(run.model_dump_json(), encoding="utf-8")
    (storage / "assets" / "legacy.png").write_bytes(b"legacy")
    original_task = (storage / f"{task.id}.json").read_bytes()

    report = build_report(storage, "auth-admin")
    assert report.ready
    assert report.task_count == 1
    assert report.run_count == 1
    workspace_id = apply_migration(storage, "auth-admin", report)

    workspace = storage / "workspaces" / workspace_id
    assert (workspace / "tasks" / f"{task.id}.json").is_file()
    assert (workspace / "runs" / f"{run.id}.json").is_file()
    assert (workspace / "assets" / "legacy.png").read_bytes() == b"legacy"
    assert (storage / f"{task.id}.json").read_bytes() == original_task

    with ControlDatabase(storage / "control" / "app.sqlite").connection() as connection:
        imported = connection.execute(
            "SELECT workspace_id, status, quota_reservation_id FROM runs WHERE id = ?",
            (run.id,),
        ).fetchone()
    assert imported["workspace_id"] == workspace_id
    assert imported["status"] == "completed"
    assert imported["quota_reservation_id"] is None
