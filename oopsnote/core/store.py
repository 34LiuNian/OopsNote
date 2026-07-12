"""JSON 文件存储层。

每个 Task 一个 JSON 文件，原子写入（先写 .tmp 再 replace）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Problem, TaskCreateRequest, TaskRecord, TaskStatus


class TaskStore:
    """基于文件的任务仓储。"""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[1] / "storage"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self.base_dir / f"{task_id}.json"

    def _write(self, record: TaskRecord) -> None:
        path = self._path(record.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            record.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    def create(self, payload: TaskCreateRequest) -> TaskRecord:
        record = TaskRecord(
            subject=payload.subject,
            status=TaskStatus.PENDING,
            asset_path=payload.asset_path,
        )
        self._write(record)
        return record

    def get(self, task_id: str) -> TaskRecord:
        path = self._path(task_id)
        if not path.exists():
            raise KeyError(f"Task {task_id} not found")
        return TaskRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[TaskRecord]:
        records: list[TaskRecord] = []
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                records.append(
                    TaskRecord.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except Exception:
                continue
        return records

    def update(self, task_id: str, **fields) -> TaskRecord:
        record = self.get(task_id)
        updated = record.model_copy(
            update={"updated_at": datetime.now(timezone.utc), **fields}
        )
        self._write(updated)
        return updated

    def set_problems(self, task_id: str, problems: list[Problem]) -> TaskRecord:
        return self.update(task_id, problems=problems)

    def mark_status(self, task_id: str, status: TaskStatus, error: Optional[str] = None) -> TaskRecord:
        fields: dict = {"status": status}
        if error:
            fields["last_error"] = error
        return self.update(task_id, **fields)

    def delete(self, task_id: str) -> None:
        path = self._path(task_id)
        if path.exists():
            path.unlink()
