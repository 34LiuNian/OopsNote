"""JSON 文件存储层。

每个 Task 一个 JSON 文件，原子写入（先写 .tmp 再 replace）。
"""

from __future__ import annotations

import errno
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .models import (
    BatchSessionRecord,
    BatchSessionUpdateRequest,
    PaperDraft,
    PaperDraftCreateRequest,
    PaperDraftUpdateRequest,
    Problem,
    RunStatus,
    StageRun,
    StageStatus,
    TaskCreateRequest,
    TaskRecord,
    TaskRun,
    TaskStage,
    TaskStatus,
)


def _is_transient_file_lock(error: OSError) -> bool:
    return (
        isinstance(error, PermissionError)
        or error.errno in {errno.EACCES, errno.EBUSY}
        or getattr(error, "winerror", None) in {5, 32, 33}
    )


def _read_text_with_retry(path: Path, *, attempts: int = 8) -> str:
    """Tolerate a peer process briefly holding a JSON file on Windows."""
    for attempt in range(attempts):
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            if not _is_transient_file_lock(error) or attempt == attempts - 1:
                raise
            time.sleep(0.02 * (attempt + 1))
    raise AssertionError("unreachable")


def _replace_with_retry(source: Path, destination: Path, *, attempts: int = 8) -> None:
    """Preserve atomic replacement while tolerating transient Windows readers."""
    for attempt in range(attempts):
        try:
            source.replace(destination)
            return
        except OSError as error:
            if not _is_transient_file_lock(error) or attempt == attempts - 1:
                raise
            time.sleep(0.02 * (attempt + 1))
    raise AssertionError("unreachable")


class TaskStore:
    """基于文件的任务仓储。"""

    _lock = threading.RLock()

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parents[1] / "storage"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, task_id: str) -> Path:
        return self.base_dir / f"{task_id}.json"

    def _write(self, record: TaskRecord) -> None:
        path = self._path(record.id)
        tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_text(
                record.model_dump_json(indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _replace_with_retry(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def create(self, payload: TaskCreateRequest) -> TaskRecord:
        record = TaskRecord(
            subject=payload.subject,
            status=TaskStatus.PENDING,
            asset_path=payload.asset_path,
            metadata=payload.metadata,
        )
        self._write(record)
        return record

    def get(self, task_id: str) -> TaskRecord:
        path = self._path(task_id)
        if not path.exists():
            raise KeyError(f"Task {task_id} not found")
        return TaskRecord.model_validate_json(_read_text_with_retry(path))

    def list_all(self) -> list[TaskRecord]:
        records: list[TaskRecord] = []
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                records.append(
                    TaskRecord.model_validate_json(_read_text_with_retry(path))
                )
            except Exception:
                continue
        return records

    def update(self, task_id: str, **fields) -> TaskRecord:
        with self._lock:
            record = self.get(task_id)
            updated = record.model_copy(
                update={"updated_at": datetime.now(timezone.utc), **fields}
            )
            self._write(updated)
            return updated

    def set_problem(self, task_id: str, problem: Optional[Problem]) -> TaskRecord:
        return self.update(task_id, problem=problem)

    def mark_status(self, task_id: str, status: TaskStatus, error: Optional[str] = None) -> TaskRecord:
        fields: dict = {"status": status, "last_error": error}
        if status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            fields["active_run_id"] = None
        return self.update(task_id, **fields)

    def delete(self, task_id: str) -> None:
        path = self._path(task_id)
        if path.exists():
            path.unlink()


class RunStore:
    """Atomic JSON persistence for managed AI task runs."""

    _lock = threading.RLock()

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.base_dir / f"{run_id}.json"

    def _write(self, run: TaskRun) -> None:
        path = self._path(run.id)
        tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
            _replace_with_retry(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def create(
        self,
        task_id: str,
        prompt_version: str = "orchestrator-v3",
        *,
        backend: str = "hermes",
        runtime_kind: Optional[str] = None,
        runtime_version: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> TaskRun:
        with self._lock:
            attempt = 1 + max(
                (run.attempt for run in self.list_all() if run.task_id == task_id),
                default=0,
            )
            previous_runs = [run for run in self.list_all() if run.task_id == task_id]
            retry_count = sum(1 for run in previous_runs if run.status in {RunStatus.FAILED, RunStatus.TIMED_OUT})
            run = TaskRun(
                task_id=task_id,
                attempt=attempt,
                prompt_version=prompt_version,
                backend=backend,
                runtime_kind=runtime_kind,
                runtime_version=runtime_version,
                provider=provider,
                model=model,
                retry_count=retry_count,
            )
            self._write(run)
            return run

    def get(self, run_id: str) -> TaskRun:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError(f"Run {run_id} not found")
        return TaskRun.model_validate_json(_read_text_with_retry(path))

    def list_all(self) -> list[TaskRun]:
        runs: list[TaskRun] = []
        for path in self.base_dir.glob("*.json"):
            try:
                runs.append(TaskRun.model_validate_json(_read_text_with_retry(path)))
            except Exception:
                continue
        return runs

    def update(self, run_id: str, **fields) -> TaskRun:
        with self._lock:
            run = self.get(run_id)
            updated = run.model_copy(update=fields)
            self._write(updated)
            return updated

    def active_for_task(self, task_id: str) -> Optional[TaskRun]:
        active = [
            run for run in self.list_all()
            if run.task_id == task_id and run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
        ]
        return max(active, key=lambda run: run.heartbeat_at, default=None)

    def latest_for_task(self, task_id: str) -> Optional[TaskRun]:
        runs = [run for run in self.list_all() if run.task_id == task_id]
        return max(runs, key=lambda run: run.heartbeat_at, default=None)

    def start(
        self,
        run_id: str,
        pid: int,
        log_path: str,
        *,
        worker_id: Optional[str] = None,
    ) -> TaskRun:
        now = datetime.now(timezone.utc)
        return self.update(
            run_id,
            status=RunStatus.RUNNING,
            pid=pid,
            log_path=log_path,
            worker_id=worker_id,
            started_at=now,
            heartbeat_at=now,
        )

    def heartbeat(self, run_id: str) -> TaskRun:
        return self.update(run_id, heartbeat_at=datetime.now(timezone.utc))

    def observe_stage(self, run_id: str, stage: TaskStage, message: Optional[str] = None) -> TaskRun:
        with self._lock:
            run = self.get(run_id)
            now = datetime.now(timezone.utc)
            stages = list(run.stage_runs)
            if stages and stages[-1].stage == stage:
                if stages[-1].message == message:
                    return run
                stages[-1] = stages[-1].model_copy(update={"message": message})
            else:
                if stages and stages[-1].status == StageStatus.RUNNING:
                    started_at = stages[-1].started_at
                    stages[-1] = stages[-1].model_copy(update={
                        "status": StageStatus.COMPLETED,
                        "ended_at": now,
                        "latency_ms": int((now - started_at).total_seconds() * 1000),
                    })
                stages.append(StageRun(stage=stage, message=message, started_at=now))
            updated = run.model_copy(update={"stage_runs": stages, "heartbeat_at": now})
            self._write(updated)
            return updated

    def finish(
        self,
        run_id: str,
        status: RunStatus,
        *,
        exit_code: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> TaskRun:
        with self._lock:
            run = self.get(run_id)
            now = datetime.now(timezone.utc)
            stages = list(run.stage_runs)
            if stages and stages[-1].status == StageStatus.RUNNING:
                stage_status = {
                    RunStatus.COMPLETED: StageStatus.COMPLETED,
                    RunStatus.CANCELLED: StageStatus.CANCELLED,
                }.get(status, StageStatus.FAILED)
                stages[-1] = stages[-1].model_copy(update={
                    "status": stage_status,
                    "ended_at": now,
                    "latency_ms": int((now - stages[-1].started_at).total_seconds() * 1000),
                    "error_code": error_code,
                })
            updated = run.model_copy(update={
                "status": status,
                "stage_runs": stages,
                "heartbeat_at": now,
                "ended_at": now,
                "exit_code": exit_code,
                "error_code": error_code,
                "error_message": error_message,
            })
            self._write(updated)
            return updated


class BatchSessionStore:
    """批量扫描会话的单文件索引，文件哈希是稳定主键。"""

    _lock = threading.RLock()

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, BatchSessionRecord]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return {
                item["file_hash"]: BatchSessionRecord.model_validate(item)
                for item in payload.get("items", [])
            }
        except Exception:
            return {}

    def _write(self, records: dict[str, BatchSessionRecord]) -> None:
        tmp = self.path.with_name(f"{self.path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_text(
                json.dumps(
                    {"items": [record.model_dump(mode="json") for record in records.values()]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            _replace_with_retry(tmp, self.path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def get(self, file_hash: str) -> BatchSessionRecord:
        with self._lock:
            record = self._read().get(file_hash)
        if not record:
            raise KeyError(file_hash)
        return record

    def list_all(self) -> list[BatchSessionRecord]:
        with self._lock:
            return sorted(self._read().values(), key=lambda record: record.updated_at, reverse=True)

    def create(self, record: BatchSessionRecord) -> BatchSessionRecord:
        with self._lock:
            records = self._read()
            existing = records.get(record.file_hash)
            if existing:
                return existing
            records[record.file_hash] = record
            self._write(records)
            return record

    def update(self, file_hash: str, payload: BatchSessionUpdateRequest) -> BatchSessionRecord:
        with self._lock:
            records = self._read()
            current = records.get(file_hash)
            if not current:
                raise KeyError(file_hash)
            update = payload.model_dump(exclude_unset=True)
            updated = BatchSessionRecord.model_validate(
                {**current.model_dump(), "updated_at": datetime.now(timezone.utc), **update}
            )
            records[file_hash] = updated
            self._write(records)
            return updated

    def delete(self, file_hash: str) -> BatchSessionRecord:
        """Delete only the batch workspace record; task assets remain untouched."""
        with self._lock:
            records = self._read()
            record = records.pop(file_hash, None)
            if not record:
                raise KeyError(file_hash)
            self._write(records)
            return record


class PaperDraftStore:
    """One atomic JSON document per persistent paper draft."""

    _lock = threading.RLock()

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, draft_id: str) -> Path:
        return self.base_dir / f"{draft_id}.json"

    def _write(self, draft: PaperDraft) -> None:
        path = self._path(draft.id)
        tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_text(
                draft.model_dump_json(indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _replace_with_retry(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def create(self, payload: PaperDraftCreateRequest, *, items=None) -> PaperDraft:
        with self._lock:
            draft = PaperDraft(
                title=payload.title.strip() or "未命名试卷",
                subject=payload.subject,
                knowledge_tags=payload.knowledge_tags,
                knowledge_node_ids=payload.knowledge_node_ids,
                difficulty_preset=payload.difficulty_preset,
                difficulty_distribution=payload.difficulty_distribution,
                requested_counts=payload.requested_counts,
                items=list(items or []),
            )
            self._write(draft)
            return draft

    def get(self, draft_id: str) -> PaperDraft:
        path = self._path(draft_id)
        if not path.exists():
            raise KeyError(draft_id)
        return PaperDraft.model_validate_json(_read_text_with_retry(path))

    def list_all(self) -> list[PaperDraft]:
        drafts: list[PaperDraft] = []
        for path in self.base_dir.glob("*.json"):
            try:
                drafts.append(PaperDraft.model_validate_json(_read_text_with_retry(path)))
            except Exception:
                continue
        return sorted(drafts, key=lambda draft: draft.updated_at, reverse=True)

    def update(self, draft_id: str, payload: PaperDraftUpdateRequest) -> PaperDraft:
        with self._lock:
            current = self.get(draft_id)
            update = payload.model_dump(exclude_unset=True, exclude_none=True)
            updated = PaperDraft.model_validate(
                {
                    **current.model_dump(),
                    **update,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self._write(updated)
            return updated

    def delete(self, draft_id: str) -> PaperDraft:
        with self._lock:
            draft = self.get(draft_id)
            self._path(draft_id).unlink()
            return draft
