from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict
from uuid import uuid4

from .models import (
    ArchiveRecord,
    AssetMetadata,
    PipelineResult,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
)


class InMemoryTaskRepository:
    """A simple in-memory store for demo and unit testing usage."""

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskRecord] = {}

    def create(
        self, payload: TaskCreateRequest, asset: AssetMetadata | None = None
    ) -> TaskRecord:
        task_id = uuid4().hex
        now = datetime.now(timezone.utc)
        record = TaskRecord(
            id=task_id,
            payload=payload,
            asset=asset,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._tasks[task_id] = record
        return record

    def get(self, task_id: str) -> TaskRecord:
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} not found")
        return self._tasks[task_id]

    def list_all(self) -> Dict[str, TaskRecord]:
        return dict(self._tasks)

    def save_pipeline_result(self, task_id: str, result: PipelineResult) -> TaskRecord:
        record = self.get(task_id)
        now = datetime.now(timezone.utc)
        updated = record.model_copy(
            update={
                "status": TaskStatus.COMPLETED,
                "updated_at": now,
                "detection": result.detection,
                "problems": result.problems,
                "solutions": result.solutions,
                "tags": result.tags,
                "archive_record": result.archive,
            }
        )
        self._tasks[task_id] = updated
        return updated

    def mark_failed(self, task_id: str, reason: str) -> TaskRecord:
        record = self.get(task_id)
        now = datetime.now(timezone.utc)
        updated = record.model_copy(
            update={
                "status": TaskStatus.FAILED,
                "updated_at": now,
                "last_error": reason,
            }
        )
        self._tasks[task_id] = updated
        return updated

    def mark_processing(self, task_id: str) -> TaskRecord:
        record = self.get(task_id)
        now = datetime.now(timezone.utc)
        updated = record.model_copy(
            update={
                "status": TaskStatus.PROCESSING,
                "updated_at": now,
            }
        )
        self._tasks[task_id] = updated
        return updated

    def patch_task(self, task_id: str, **fields) -> TaskRecord:
        record = self.get(task_id)
        now = datetime.now(timezone.utc)
        payload = {**fields, "updated_at": now}
        updated = record.model_copy(update=payload)
        self._tasks[task_id] = updated
        return updated

    def delete(self, task_id: str) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} not found")
        del self._tasks[task_id]


class ArchiveStore:
    """Stub archive store — in production this would persist to Postgres/S3."""

    def __init__(self) -> None:
        self._archives: Dict[str, ArchiveRecord] = {}

    def save(self, archive: ArchiveRecord) -> ArchiveRecord:
        self._archives[archive.task_id] = archive
        return archive

    def get(self, task_id: str) -> ArchiveRecord:
        return self._archives[task_id]


class FileTaskRepository:
    """File-backed task repository.

    Persists each task record as a JSON file so tasks/problems survive process restarts.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or (
            Path(__file__).resolve().parents[1] / "storage" / "tasks"
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: Dict[str, TaskRecord] = {}
        self._load_all()

    def _task_path(self, task_id: str) -> Path:
        return self.base_dir / f"{task_id}.json"

    def _write(self, record: TaskRecord) -> None:
        path = self._task_path(record.id)
        tmp = path.with_suffix(".json.tmp")
        payload = record.model_dump(mode="json")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(path)

    def _load_all(self) -> None:
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                record = TaskRecord.model_validate(raw)
                self._tasks[record.id] = record
            except Exception:
                # Ignore corrupted/partial files; they can be repaired manually.
                continue

    def create(
        self, payload: TaskCreateRequest, asset: AssetMetadata | None = None
    ) -> TaskRecord:
        task_id = uuid4().hex
        now = datetime.now(timezone.utc)
        record = TaskRecord(
            id=task_id,
            payload=payload,
            asset=asset,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        self._tasks[task_id] = record
        self._write(record)
        return record

    def get(self, task_id: str) -> TaskRecord:
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} not found")
        return self._tasks[task_id]

    def list_all(self) -> Dict[str, TaskRecord]:
        return dict(self._tasks)

    def save_pipeline_result(self, task_id: str, result: PipelineResult) -> TaskRecord:
        record = self.get(task_id)
        now = datetime.now(timezone.utc)
        updated = record.model_copy(
            update={
                "status": TaskStatus.COMPLETED,
                "updated_at": now,
                "detection": result.detection,
                "problems": result.problems,
                "solutions": result.solutions,
                "tags": result.tags,
                "archive_record": result.archive,
            }
        )
        self._tasks[task_id] = updated
        self._write(updated)
        return updated

    def mark_failed(self, task_id: str, reason: str) -> TaskRecord:
        record = self.get(task_id)
        now = datetime.now(timezone.utc)
        updated = record.model_copy(
            update={
                "status": TaskStatus.FAILED,
                "updated_at": now,
                "last_error": reason,
            }
        )
        self._tasks[task_id] = updated
        self._write(updated)
        return updated

    def mark_processing(self, task_id: str) -> TaskRecord:
        record = self.get(task_id)
        now = datetime.now(timezone.utc)
        updated = record.model_copy(
            update={
                "status": TaskStatus.PROCESSING,
                "updated_at": now,
            }
        )
        self._tasks[task_id] = updated
        self._write(updated)
        return updated

    def patch_task(self, task_id: str, **fields) -> TaskRecord:
        record = self.get(task_id)
        now = datetime.now(timezone.utc)
        payload = {**fields, "updated_at": now}
        updated = record.model_copy(update=payload)
        self._tasks[task_id] = updated
        self._write(updated)
        return updated

    def delete(self, task_id: str) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} not found")
        path = self._task_path(task_id)
        try:
            if path.exists():
                path.unlink()
        finally:
            del self._tasks[task_id]
