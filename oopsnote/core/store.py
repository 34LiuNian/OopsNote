"""JSON 文件存储层。

每个 Task 一个 JSON 文件，原子写入（先写 .tmp 再 replace）。
"""

from __future__ import annotations

import errno
import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from .models import (
    BatchProcessJob,
    BatchSessionRecord,
    BatchSessionUpdateRequest,
    PaperDraft,
    PaperDraftCreateRequest,
    PaperDraftUpdateRequest,
    DiagramCandidate,
    DiagramItem,
    DiagramRunMode,
    DiagramRunStep,
    Problem,
    RunArtifact,
    RunStatus,
    RunPurpose,
    RunValidationError,
    StageRun,
    StageStatus,
    TaskCreateRequest,
    TaskRecord,
    TaskRun,
    SolutionCandidate,
    TaskStage,
    TaskStatus,
    ProblemMergeRecord,
)


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _validated_update(model: _ModelT, fields: dict[str, object]) -> _ModelT:
    """Apply a partial update without bypassing Pydantic validation."""
    model_type = type(model)
    unknown = set(fields) - set(model_type.model_fields)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise TypeError(f"Unknown {model_type.__name__} field(s): {names}")
    payload = model.model_dump(mode="python")
    payload.update(fields)
    return model_type.model_validate(payload)


class StateConflict(RuntimeError):
    """A persisted record no longer matches the caller's expected state."""


class StorageCorruptionError(RuntimeError):
    """Persisted JSON exists but cannot be decoded or validated safely."""

    def __init__(self, path: Path, error: Exception) -> None:
        super().__init__(f"Persisted JSON is corrupt: {path}: {error}")
        self.path = path


_UNSET = object()


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
        record = _validated_update(record, {})
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
            section_question_count=payload.section_question_count,
        )
        self._write(record)
        return record

    def get(self, task_id: str) -> TaskRecord:
        path = self._path(task_id)
        if not path.exists():
            raise KeyError(f"Task {task_id} not found")
        try:
            return TaskRecord.model_validate_json(_read_text_with_retry(path))
        except Exception as error:
            raise StorageCorruptionError(path, error) from error

    def list_all(self) -> list[TaskRecord]:
        records: list[TaskRecord] = []
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                records.append(
                    TaskRecord.model_validate_json(_read_text_with_retry(path))
                )
            except Exception as error:
                raise StorageCorruptionError(path, error) from error
        return records

    def update(self, task_id: str, **fields) -> TaskRecord:
        with self._lock:
            record = self.get(task_id)
            updated = _validated_update(
                record,
                {"updated_at": datetime.now(timezone.utc), **fields},
            )
            self._write(updated)
            return updated

    def transition(
        self,
        task_id: str,
        *,
        expected_statuses: Optional[set[TaskStatus]] = None,
        expected_active_run_id: object = _UNSET,
        expected_problem_id: object = _UNSET,
        **fields,
    ) -> TaskRecord:
        """Atomically compare task state and apply one state transition."""
        with self._lock:
            record = self.get(task_id)
            if expected_statuses is not None and record.status not in expected_statuses:
                raise StateConflict(
                    f"Task {task_id} status is {record.status.value}, expected one of "
                    f"{', '.join(sorted(status.value for status in expected_statuses))}"
                )
            if (
                expected_active_run_id is not _UNSET
                and record.active_run_id != expected_active_run_id
            ):
                raise StateConflict(
                    f"Run {expected_active_run_id!s} is not active for task {task_id}"
                )
            actual_problem_id = record.problem.id if record.problem else None
            if (
                expected_problem_id is not _UNSET
                and actual_problem_id != expected_problem_id
            ):
                raise StateConflict(
                    f"Problem {expected_problem_id!s} is not current for task {task_id}"
                )
            updated = _validated_update(
                record,
                {"updated_at": datetime.now(timezone.utc), **fields},
            )
            self._write(updated)
            return updated

    def set_problem(self, task_id: str, problem: Optional[Problem]) -> TaskRecord:
        return self.update(task_id, problem=problem)

    def add_diagram_item(self, task_id: str, item: DiagramItem) -> TaskRecord:
        """Append one diagram slot without replacing any retained version history."""
        with self._lock:
            record = self.get(task_id)
            if any(existing.id == item.id for existing in record.diagram_items):
                raise StateConflict(f"Diagram item {item.id} already exists")
            return self.update(task_id, diagram_items=[*record.diagram_items, item])

    def update_diagram_item(
        self,
        task_id: str,
        item_id: str,
        *,
        expected_active_run_id: object = _UNSET,
        **fields,
    ) -> TaskRecord:
        """Atomically compare and update one item inside the canonical item list."""
        with self._lock:
            record = self.get(task_id)
            items = list(record.diagram_items)
            index = next((i for i, item in enumerate(items) if item.id == item_id), None)
            if index is None:
                raise KeyError(f"Diagram item {item_id} not found")
            current = items[index]
            if (
                expected_active_run_id is not _UNSET
                and current.active_run_id != expected_active_run_id
            ):
                raise StateConflict(
                    f"Run {expected_active_run_id!s} is not active for diagram {item_id}"
                )
            items[index] = _validated_update(
                current,
                {"updated_at": datetime.now(timezone.utc), **fields},
            )
            return self.update(task_id, diagram_items=items)

    def append_diagram_candidate(
        self,
        task_id: str,
        item_id: str,
        candidate: DiagramCandidate,
        *,
        expected_active_run_id: str,
    ) -> TaskRecord:
        """Retain a candidate exactly once; candidates are never overwritten."""
        with self._lock:
            record = self.get(task_id)
            item = next((item for item in record.diagram_items if item.id == item_id), None)
            if item is None:
                raise KeyError(f"Diagram item {item_id} not found")
            if item.active_run_id != expected_active_run_id:
                raise StateConflict(f"Run {expected_active_run_id} is no longer active")
            if any(existing.id == candidate.id for existing in item.candidates):
                return record
            if any(existing.ordinal == candidate.ordinal for existing in item.candidates):
                raise StateConflict(
                    f"Diagram item {item_id} already has candidate {candidate.ordinal}"
                )
            return self.update_diagram_item(
                task_id,
                item_id,
                expected_active_run_id=expected_active_run_id,
                candidates=[*item.candidates, candidate],
            )

    def update_diagram_candidate(
        self,
        task_id: str,
        item_id: str,
        candidate_id: str,
        *,
        expected_active_run_id: str,
        **fields,
    ) -> TaskRecord:
        """Advance retained candidate evidence without changing its source identity."""
        with self._lock:
            record = self.get(task_id)
            item = next((item for item in record.diagram_items if item.id == item_id), None)
            if item is None:
                raise KeyError(f"Diagram item {item_id} not found")
            if item.active_run_id != expected_active_run_id:
                raise StateConflict(f"Run {expected_active_run_id} is no longer active")
            candidates = list(item.candidates)
            index = next(
                (index for index, candidate in enumerate(candidates) if candidate.id == candidate_id),
                None,
            )
            if index is None:
                raise KeyError(f"Diagram candidate {candidate_id} not found")
            if "tikz_source" in fields or "source_sha256" in fields or "id" in fields:
                raise ValueError("Diagram candidate source identity is immutable")
            candidates[index] = _validated_update(candidates[index], fields)
            return self.update_diagram_item(
                task_id,
                item_id,
                expected_active_run_id=expected_active_run_id,
                candidates=candidates,
            )

    def mark_status(
        self,
        task_id: str,
        status: TaskStatus,
        error: Optional[str] = None,
        *,
        error_code: Optional[str] = None,
    ) -> TaskRecord:
        fields: dict = {
            "status": status,
            "last_error": error,
            "last_error_code": error_code,
        }
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
        self._task_index: dict[str, list[str]] | None = None

    def _path(self, run_id: str) -> Path:
        return self.base_dir / f"{run_id}.json"

    def _write(self, run: TaskRun) -> None:
        run = _validated_update(run, {})
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
        prompt_version: str = "unversioned",
        *,
        backend: str = "pi",
        runtime_kind: Optional[str] = None,
        runtime_version: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        provider_profile_snapshot: Optional[dict[str, Any]] = None,
        retry_of: Optional[TaskRun] = None,
        purpose: RunPurpose = RunPurpose.PROBLEM,
        priority: int = 0,
        diagram_item_id: Optional[str] = None,
        diagram_mode: Optional[DiagramRunMode] = None,
        diagram_instruction: Optional[str] = None,
        diagram_max_candidates: Optional[int] = None,
        diagram_step: Optional[DiagramRunStep] = None,
    ) -> TaskRun:
        with self._lock:
            previous_runs = [
                run for run in self.list_for_task(task_id)
                if run.purpose == purpose and run.diagram_item_id == diagram_item_id
            ]
            attempt = 1 + max((run.attempt for run in previous_runs), default=0)
            run = TaskRun(
                task_id=task_id,
                purpose=purpose,
                priority=priority,
                diagram_item_id=diagram_item_id,
                diagram_mode=diagram_mode,
                diagram_instruction=diagram_instruction,
                diagram_max_candidates=diagram_max_candidates,
                diagram_step=diagram_step,
                attempt=attempt,
                prompt_version=prompt_version,
                backend=backend,
                runtime_kind=runtime_kind,
                runtime_version=runtime_version,
                provider=provider,
                model=model,
                provider_profile_snapshot=provider_profile_snapshot,
                retry_count=(retry_of.retry_count + 1 if retry_of else 0),
                retry_of_run_id=(retry_of.id if retry_of else None),
                retry_root_run_id=(
                    retry_of.retry_root_run_id or retry_of.id
                    if retry_of
                    else None
                ),
            )
            self._write(run)
            if self._task_index is not None:
                self._task_index.setdefault(task_id, []).append(run.id)
            return run

    def get(self, run_id: str) -> TaskRun:
        path = self._path(run_id)
        if not path.exists():
            raise KeyError(f"Run {run_id} not found")
        try:
            return TaskRun.model_validate_json(_read_text_with_retry(path))
        except Exception as error:
            raise StorageCorruptionError(path, error) from error

    def list_all(self) -> list[TaskRun]:
        runs: list[TaskRun] = []
        index: dict[str, list[str]] = {}
        for path in self.base_dir.glob("*.json"):
            try:
                run = TaskRun.model_validate_json(_read_text_with_retry(path))
                runs.append(run)
                index.setdefault(run.task_id, []).append(run.id)
            except Exception as error:
                raise StorageCorruptionError(path, error) from error
        self._task_index = index
        return runs

    def list_for_task(self, task_id: str) -> list[TaskRun]:
        """Use the in-process reverse index after its one authoritative scan."""
        with self._lock:
            if self._task_index is None:
                self.list_all()
            run_ids = list((self._task_index or {}).get(task_id, []))
            try:
                return [self.get(run_id) for run_id in run_ids]
            except KeyError:
                # A manually removed run invalidates only the derived cache.
                return [run for run in self.list_all() if run.task_id == task_id]

    def update(self, run_id: str, **fields) -> TaskRun:
        with self._lock:
            run = self.get(run_id)
            updated = _validated_update(run, fields)
            self._write(updated)
            return updated

    def submit_solution_candidate(
        self,
        run_id: str,
        candidate: SolutionCandidate,
        artifact: Optional[RunArtifact] = None,
    ) -> TaskRun:
        """Persist the sole solver output before an independent verification session."""
        with self._lock:
            run = self.get(run_id)
            if run.solution_candidate is not None:
                raise StateConflict(f"Run {run_id} already has a solution candidate")
            artifacts = list(run.artifacts)
            if artifact is not None:
                if artifact.stage != TaskStage.SOLVING or artifact.kind != "solver_candidate":
                    raise ValueError("solver candidate evidence must describe the solving stage")
                artifacts.append(artifact)
            updated = _validated_update(
                run,
                {"solution_candidate": candidate, "artifacts": artifacts},
            )
            self._write(updated)
            return updated

    def record_artifact(self, run_id: str, artifact: RunArtifact) -> TaskRun:
        """Append one unique immutable output observation without changing task content."""
        with self._lock:
            run = self.get(run_id)
            for existing in run.artifacts:
                if (existing.stage, existing.kind) != (artifact.stage, artifact.kind):
                    continue
                if (
                    existing.raw_output == artifact.raw_output
                    and existing.parsed_output == artifact.parsed_output
                ):
                    return run
                raise StateConflict(
                    f"Run {run_id} already has {artifact.kind} evidence for {artifact.stage.value}"
                )
            updated = _validated_update(run, {"artifacts": [*run.artifacts, artifact]})
            self._write(updated)
            return updated

    def record_validation_error(
        self,
        run_id: str,
        evidence: RunValidationError,
    ) -> TaskRun:
        """Append a deduplicated rejection without replacing the valid prior evidence."""
        with self._lock:
            run = self.get(run_id)
            for existing in run.validation_errors:
                if (
                    existing.stage == evidence.stage
                    and existing.raw_output == evidence.raw_output
                    and existing.message == evidence.message
                ):
                    return run
            updated = _validated_update(
                run,
                {"validation_errors": [*run.validation_errors, evidence]},
            )
            self._write(updated)
            return updated

    def begin_verification(self, run_id: str) -> TaskRun:
        """Record that the runner, not the solver context, opened verification."""
        with self._lock:
            run = self.get(run_id)
            if run.solution_candidate is None:
                raise StateConflict(f"Run {run_id} has no solution candidate")
            if run.verification_started_at is not None:
                return run
            updated = _validated_update(
                run,
                {"verification_started_at": datetime.now(timezone.utc)},
            )
            self._write(updated)
            return updated

    def active_for_task(
        self,
        task_id: str,
        *,
        purpose: RunPurpose = RunPurpose.PROBLEM,
        diagram_item_id: Optional[str] = None,
    ) -> Optional[TaskRun]:
        active = [
            run for run in self.list_for_task(task_id)
            if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
            and run.purpose == purpose
            and (diagram_item_id is None or run.diagram_item_id == diagram_item_id)
        ]
        return max(active, key=lambda run: run.heartbeat_at, default=None)

    def latest_for_task(
        self,
        task_id: str,
        *,
        purpose: RunPurpose = RunPurpose.PROBLEM,
        diagram_item_id: Optional[str] = None,
    ) -> Optional[TaskRun]:
        runs = [
            run for run in self.list_for_task(task_id)
            if run.purpose == purpose
            and (diagram_item_id is None or run.diagram_item_id == diagram_item_id)
        ]
        return max(runs, key=lambda run: run.heartbeat_at, default=None)

    def start(
        self,
        run_id: str,
        pid: Optional[int],
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
            started_at=self.get(run_id).started_at or now,
            heartbeat_at=now,
        )

    def yield_run(self, run_id: str) -> TaskRun:
        """Return a cooperative work quantum to the durable priority queue."""
        run = self.get(run_id)
        if run.status != RunStatus.RUNNING:
            raise StateConflict(f"Run {run_id} is not running")
        return self.update(
            run_id,
            status=RunStatus.QUEUED,
            worker_id=None,
            heartbeat_at=datetime.now(timezone.utc),
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
                stages[-1] = _validated_update(stages[-1], {"message": message})
            else:
                if stages and stages[-1].status == StageStatus.RUNNING:
                    started_at = stages[-1].started_at
                    stages[-1] = _validated_update(
                        stages[-1],
                        {
                            "status": StageStatus.COMPLETED,
                            "ended_at": now,
                            "latency_ms": int(
                                (now - started_at).total_seconds() * 1000
                            ),
                        },
                    )
                stages.append(StageRun(stage=stage, message=message, started_at=now))
            updated = _validated_update(
                run,
                {"stage_runs": stages, "heartbeat_at": now},
            )
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
            terminal = {
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }
            # The first terminal transition wins. A late worker callback must
            # never turn a cancelled run into failed/completed or vice versa.
            if run.status in terminal:
                return run
            now = datetime.now(timezone.utc)
            stages = list(run.stage_runs)
            if stages and stages[-1].status == StageStatus.RUNNING:
                stage_status = {
                    RunStatus.COMPLETED: StageStatus.COMPLETED,
                    RunStatus.CANCELLED: StageStatus.CANCELLED,
                }.get(status, StageStatus.FAILED)
                stages[-1] = _validated_update(
                    stages[-1],
                    {
                        "status": stage_status,
                        "ended_at": now,
                        "latency_ms": int(
                            (now - stages[-1].started_at).total_seconds() * 1000
                        ),
                        "error_code": error_code,
                    },
                )
            updated = _validated_update(
                run,
                {
                    "status": status,
                    "stage_runs": stages,
                    "heartbeat_at": now,
                    "ended_at": now,
                    "duration_ms": max(
                        0,
                        int((now - run.queued_at).total_seconds() * 1000),
                    ),
                    "exit_code": exit_code,
                    "error_code": error_code,
                    "error_message": error_message,
                },
            )
            self._write(updated)
            return updated


class BatchSessionStore:
    """批量扫描会话的单文件索引，文件哈希是稳定主键。"""

    _lock = threading.RLock()

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._record_locks_guard = threading.Lock()
        self._record_locks: dict[str, threading.RLock] = {}

    def session_lock(self, file_hash: str) -> threading.RLock:
        """Return the per-session lock shared by PATCH, processing, and status refresh."""
        with self._record_locks_guard:
            return self._record_locks.setdefault(file_hash, threading.RLock())

    def _read(self) -> dict[str, BatchSessionRecord]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(_read_text_with_retry(self.path))
            return {
                item["file_hash"]: BatchSessionRecord.model_validate(item)
                for item in payload.get("items", [])
            }
        except Exception as error:
            raise StorageCorruptionError(self.path, error) from error

    def _write(self, records: dict[str, BatchSessionRecord]) -> None:
        records = {
            key: _validated_update(record, {})
            for key, record in records.items()
        }
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

    def update(
        self,
        file_hash: str,
        payload: BatchSessionUpdateRequest,
        *,
        expected_revision: int,
    ) -> BatchSessionRecord:
        with self.session_lock(file_hash), self._lock:
            records = self._read()
            current = records.get(file_hash)
            if not current:
                raise KeyError(file_hash)
            if current.revision != expected_revision:
                raise StateConflict(
                    f"Batch session {file_hash} revision is {current.revision}, "
                    f"expected {expected_revision}"
                )
            update = payload.model_dump(exclude_unset=True)
            proposed_segments = (
                payload.segments if "segments" in payload.model_fields_set else None
            )
            if proposed_segments is not None:
                proposed_by_id = {segment.id: segment for segment in proposed_segments}
                for segment in current.segments:
                    if not segment.task_id:
                        continue
                    proposed = proposed_by_id.get(segment.id)
                    if proposed is None or proposed.task_id != segment.task_id:
                        raise StateConflict(
                            f"Task-bound batch segment {segment.id} cannot be removed or rebound"
                        )
            updated = BatchSessionRecord.model_validate(
                {
                    **current.model_dump(),
                    "updated_at": datetime.now(timezone.utc),
                    "revision": current.revision + 1,
                    **update,
                }
            )
            records[file_hash] = updated
            self._write(records)
            return updated

    def clear_stale_task_link(
        self,
        file_hash: str,
        segment_id: str,
        task_id: str,
        *,
        expected_revision: int,
    ) -> BatchSessionRecord:
        """Remove one task link after its absence has been verified by the caller."""
        with self.session_lock(file_hash), self._lock:
            records = self._read()
            current = records.get(file_hash)
            if not current:
                raise KeyError(file_hash)
            if current.revision != expected_revision:
                raise StateConflict(
                    f"Batch session {file_hash} revision is {current.revision}, "
                    f"expected {expected_revision}"
                )
            segments = []
            found = False
            for segment in current.segments:
                if segment.id != segment_id:
                    segments.append(segment)
                    continue
                if segment.task_id != task_id:
                    raise StateConflict(
                        f"Batch segment {segment_id} no longer links task {task_id}"
                    )
                found = True
                segments.append(
                    segment.model_copy(
                        update={
                            "status": "pending",
                            "review_reason": None,
                            "review_previous_status": None,
                            "review_resolved": False,
                            "task_id": None,
                            "problem_ids": [],
                            "error": None,
                        }
                    )
                )
            if not found:
                raise KeyError(segment_id)
            updated = BatchSessionRecord.model_validate(
                {
                    **current.model_dump(),
                    "updated_at": datetime.now(timezone.utc),
                    "revision": current.revision + 1,
                    "segments": segments,
                }
            )
            records[file_hash] = updated
            self._write(records)
            return updated

    def delete(self, file_hash: str) -> BatchSessionRecord:
        """Delete only the batch workspace record; task assets remain untouched."""
        with self.session_lock(file_hash), self._lock:
            records = self._read()
            record = records.pop(file_hash, None)
            if not record:
                raise KeyError(file_hash)
            self._write(records)
            return record


class BatchProcessJobStore:
    """One atomic manifest per source hash for crash-safe batch processing."""

    _lock = threading.RLock()

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, file_hash: str) -> Path:
        safe_key = hashlib.sha256(file_hash.encode("utf-8")).hexdigest()
        return self.base_dir / f"{safe_key}.json"

    def get(self, file_hash: str) -> BatchProcessJob:
        path = self._path(file_hash)
        with self._lock:
            if not path.exists():
                raise KeyError(file_hash)
            try:
                return BatchProcessJob.model_validate_json(_read_text_with_retry(path))
            except Exception as error:
                raise StorageCorruptionError(path, error) from error

    def save(self, job: BatchProcessJob) -> BatchProcessJob:
        updated = _validated_update(
            job,
            {"updated_at": datetime.now(timezone.utc)},
        )
        path = self._path(job.file_hash)
        tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        with self._lock:
            try:
                tmp.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
                _replace_with_retry(tmp, path)
            finally:
                if tmp.exists():
                    tmp.unlink()
        return updated

class PaperDraftStore:
    """One atomic JSON document per persistent paper draft."""

    _lock = threading.RLock()

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, draft_id: str) -> Path:
        return self.base_dir / f"{draft_id}.json"

    def _write(self, draft: PaperDraft) -> None:
        draft = _validated_update(draft, {})
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
        try:
            return PaperDraft.model_validate_json(_read_text_with_retry(path))
        except Exception as error:
            raise StorageCorruptionError(path, error) from error

    def list_all(self) -> list[PaperDraft]:
        drafts: list[PaperDraft] = []
        for path in self.base_dir.glob("*.json"):
            try:
                drafts.append(PaperDraft.model_validate_json(_read_text_with_retry(path)))
            except Exception as error:
                raise StorageCorruptionError(path, error) from error
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


class ProblemMergeStore:
    """Atomic, idempotent source-to-target map for confirmed duplicate tasks."""

    _lock = threading.RLock()

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[ProblemMergeRecord]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(_read_text_with_retry(self.path))
            return [ProblemMergeRecord.model_validate(item) for item in payload.get("items", [])]
        except Exception as error:
            raise StorageCorruptionError(self.path, error) from error

    def _write(self, items: list[ProblemMergeRecord]) -> None:
        items = [_validated_update(item, {}) for item in items]
        tmp = self.path.with_name(f"{self.path.name}.{uuid4().hex}.tmp")
        try:
            tmp.write_text(json.dumps({"items": [item.model_dump(mode="json") for item in items]}, ensure_ascii=False, indent=2), encoding="utf-8")
            _replace_with_retry(tmp, self.path)
        finally:
            if tmp.exists():
                tmp.unlink()

    def canonical_for(self, problem_id: str) -> str:
        with self._lock:
            items = self._read()
        mapping = {item.source_problem_id: item.target_problem_id for item in items}
        current = problem_id
        visited: set[str] = set()
        while current in mapping:
            if current in visited:
                raise StorageCorruptionError(self.path, ValueError("Problem merge cycle detected"))
            visited.add(current)
            current = mapping[current]
        return current

    def merge(self, source_problem_id: str, target_problem_id: str) -> ProblemMergeRecord:
        with self._lock:
            if source_problem_id == target_problem_id:
                raise ValueError("A problem cannot be merged into itself")
            items = self._read()
            source_root = self.canonical_for(source_problem_id)
            target_root = self.canonical_for(target_problem_id)
            if source_root == target_root:
                raise ValueError("Problems are already merged")
            if target_root == source_problem_id:
                raise ValueError("Merge would create a cycle")
            existing = next((item for item in items if item.source_problem_id == source_root), None)
            if existing:
                if existing.target_problem_id == target_root:
                    return existing
                raise ValueError("Source problem is already merged into another problem")
            record = ProblemMergeRecord(source_problem_id=source_root, target_problem_id=target_root)
            items.append(record)
            self._write(items)
            return record
