"""Safely migrate the legacy single-user storage tree into one workspace.

The command is intentionally conservative: without ``--apply`` it only reads
and reports. Apply copies into a temporary sibling, validates the copy, then
renames it into ``storage/workspaces/<workspace_id>``. The legacy tree is never
deleted or modified by this command.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from oopsnote.control import ControlDatabase, WorkspaceRegistry
from oopsnote.core import RunStatus, RunStore, TaskRecord, TaskRun


@dataclass(frozen=True)
class MigrationReport:
    storage_dir: str
    admin_user_id: str
    task_count: int
    run_count: int
    asset_count: int
    batch_job_count: int
    paper_count: int
    setting_files: int
    active_run_ids: tuple[str, ...]
    invalid_files: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return not self.active_run_ids and not self.invalid_files


def _load_tasks(storage_dir: Path) -> tuple[list[tuple[Path, TaskRecord]], list[str]]:
    records: list[tuple[Path, TaskRecord]] = []
    invalid: list[str] = []
    for path in sorted(storage_dir.glob("*.json")):
        try:
            records.append((path, TaskRecord.model_validate_json(path.read_text(encoding="utf-8"))))
        except Exception:
            invalid.append(str(path.relative_to(storage_dir)))
    return records, invalid


def _load_runs(storage_dir: Path) -> tuple[list[tuple[Path, TaskRun]], list[str]]:
    records: list[tuple[Path, TaskRun]] = []
    invalid: list[str] = []
    run_dir = storage_dir / "runs"
    for path in sorted(run_dir.glob("*.json")) if run_dir.is_dir() else []:
        try:
            records.append((path, TaskRun.model_validate_json(path.read_text(encoding="utf-8"))))
        except Exception:
            invalid.append(str(path.relative_to(storage_dir)))
    return records, invalid


def _asset_references(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.startswith("/assets/") else []
    if isinstance(value, dict):
        return [reference for item in value.values() for reference in _asset_references(item)]
    if isinstance(value, list):
        return [reference for item in value for reference in _asset_references(item)]
    return []


def build_report(storage_dir: Path, admin_user_id: str) -> MigrationReport:
    tasks, invalid_tasks = _load_tasks(storage_dir)
    runs, invalid_runs = _load_runs(storage_dir)
    task_ids = {task.id for _path, task in tasks}
    warnings = [
        f"runs/{run.id}.json:missing-task:{run.task_id}"
        for _path, run in runs
        if run.task_id not in task_ids
    ]
    for _path, task in tasks:
        for reference in _asset_references(task.model_dump(mode="json")):
            name = reference.removeprefix("/assets/")
            if Path(name).name != name or not (storage_dir / "assets" / name).is_file():
                warnings.append(f"{task.id}.json:missing-asset:{reference}")
    active = tuple(sorted(run.id for _path, run in runs if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}))
    assets = [path for path in (storage_dir / "assets").rglob("*") if path.is_file()] if (storage_dir / "assets").is_dir() else []
    batch_jobs = list((storage_dir / "batch_jobs").glob("*.json")) if (storage_dir / "batch_jobs").is_dir() else []
    papers = list((storage_dir / "papers").glob("*.json")) if (storage_dir / "papers").is_dir() else []
    settings = [
        storage_dir / "settings" / name
        for name in ("tags_user.json", "batch_sessions.json", "problem_merges.json")
        if (storage_dir / "settings" / name).is_file()
    ]
    return MigrationReport(
        storage_dir=str(storage_dir),
        admin_user_id=admin_user_id,
        task_count=len(tasks),
        run_count=len(runs),
        asset_count=len(assets),
        batch_job_count=len(batch_jobs),
        paper_count=len(papers),
        setting_files=len(settings),
        active_run_ids=active,
        invalid_files=tuple(sorted(invalid_tasks + invalid_runs)),
        warnings=tuple(sorted(warnings)),
    )


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def apply_migration(storage_dir: Path, admin_user_id: str, report: MigrationReport) -> str:
    if not report.ready:
        raise RuntimeError("migration is not ready; stop active runs and fix invalid files first")
    registry = WorkspaceRegistry(ControlDatabase(storage_dir / "control" / "app.sqlite"), storage_dir)
    workspace = registry.provision(admin_user_id)
    destination = workspace.root
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"workspace destination already contains data: {destination}")
    temporary = destination.parent / f".migration-{workspace.workspace_id}-{uuid4().hex}"
    try:
        temporary.mkdir(parents=True)
        tasks, _ = _load_tasks(storage_dir)
        runs, _ = _load_runs(storage_dir)
        for source, task in tasks:
            target = temporary / "tasks" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(task.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
        for source, run in runs:
            target = temporary / "runs" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                run.model_copy(update={"workspace_id": str(workspace.workspace_id)}).model_dump_json(indent=2),
                encoding="utf-8",
            )
        for name in ("assets", "batch_jobs", "papers"):
            _copy_tree(storage_dir / name, temporary / name)
        for name in ("tags_user.json", "batch_sessions.json", "problem_merges.json"):
            _copy_tree(storage_dir / "settings" / name, temporary / "settings" / name)

        database = registry.database
        database.migrate()
        with database.connection() as connection:
            for _source, run in runs:
                status = run.status.value
                if status in {RunStatus.QUEUED.value, RunStatus.RUNNING.value}:
                    raise RuntimeError(f"run became active during migration: {run.id}")
                connection.execute(
                    """
                    INSERT INTO runs(
                        id, workspace_id, task_id, purpose, status,
                        retry_of, quota_reservation_id, queued_at, started_at, finished_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
                    ON CONFLICT(id) DO NOTHING
                    """,
                    (
                        run.id,
                        str(workspace.workspace_id),
                        run.task_id,
                        run.purpose.value,
                        status,
                        run.queued_at.isoformat(),
                        run.started_at.isoformat() if run.started_at else None,
                        run.ended_at.isoformat() if run.ended_at else None,
                        json.dumps({"legacy_import": True, "retry_of_run_id": run.retry_of_run_id}, ensure_ascii=False),
                    ),
                )
                owner = connection.execute(
                    "SELECT workspace_id FROM runs WHERE id = ?",
                    (run.id,),
                ).fetchone()
                if owner is None or owner["workspace_id"] != str(workspace.workspace_id):
                    raise RuntimeError(f"historical run id belongs to another workspace: {run.id}")
            connection.commit()
        destination.parent.mkdir(parents=True, exist_ok=True)
        # WorkspaceContext creates the registered root eagerly; it is still
        # empty here, so remove only that exact newly-created directory before
        # the atomic sibling rename.
        if destination.exists():
            if any(destination.iterdir()):
                raise RuntimeError(f"workspace destination became non-empty: {destination}")
            destination.rmdir()
        temporary.replace(destination)
        registry.mark_legacy_imported(admin_user_id)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return str(workspace.workspace_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-dir", type=Path, default=Path("storage"))
    parser.add_argument("--admin-user-id", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    storage_dir = args.storage_dir.resolve()
    report = build_report(storage_dir, args.admin_user_id)
    payload = asdict(report) | {"ready": report.ready, "generated_at": datetime.now(timezone.utc).isoformat()}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.write_text(rendered + "\n", encoding="utf-8")
    if not args.apply:
        return 0 if report.ready else 2
    if not report.ready:
        return 2
    try:
        workspace_id = apply_migration(storage_dir, args.admin_user_id, report)
    except Exception as error:
        print(f"apply failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"applied": True, "workspace_id": workspace_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
