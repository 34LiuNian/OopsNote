"""Shared lifecycle for managed OopsNote AI task workers."""

from __future__ import annotations

import subprocess
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from oopsnote.ai.dispatcher import ManagedTaskDispatcher
from oopsnote.core import RunStatus, RunStore, StateConflict, TaskRun, TaskStage, TaskStatus, TaskStore


class AgentBackend(Protocol):
    """The process-specific command contract used by a managed task runner."""

    name: str

    def build_command(self, task_id: str, run_id: str) -> list[str]: ...


class ManagedAiRunner(ABC):
    """Own task/run state independently from a specific agent process."""

    _RETRYABLE_ERROR_CODES = frozenset({
        "connection_error",
        "network_error",
        "ocr_network_error",
        "ocr_provider_unavailable",
        "ocr_rate_limit",
        "ocr_timeout",
        "rate_limit",
        "rate_limit_exceeded",
        "provider_rate_limit",
        "provider_unavailable",
        "service_unavailable",
        "429",
        "503",
    })

    backend_name = "unknown"
    _admission_lock = threading.RLock()

    def __init__(
        self,
        *,
        project_root: Path,
        task_store: TaskStore,
        run_store: RunStore,
        timeout_seconds: int = 600,
        stale_seconds: int = 900,
        heartbeat_seconds: float = 5.0,
        poll_seconds: float = 0.25,
    ) -> None:
        self.project_root = project_root
        self.task_store = task_store
        self.run_store = run_store
        self.timeout_seconds = max(1, timeout_seconds)
        self.stale_seconds = max(1, stale_seconds)
        self.heartbeat_seconds = max(0.05, heartbeat_seconds)
        self.poll_seconds = max(0.05, poll_seconds)
        self._processes: dict[str, subprocess.Popen[Any]] = {}
        self._lock = threading.RLock()
        worker_count = max(1, int(getattr(self, "max_concurrent_tasks", 1)))
        self._dispatcher = ManagedTaskDispatcher(self, worker_count)

    def _run_metadata(self) -> dict[str, Any]:
        return {}

    def enqueue(
        self,
        task_id: str,
        *,
        retry_of: Optional[TaskRun] = None,
    ) -> TaskRun:
        """Create a run and move a task into the managed processing state."""
        # One local API process may receive concurrent requests for the same
        # task through different runtime runners. Admission is one transaction
        # at the lifecycle level even though task/run JSON files are separate.
        with self._admission_lock:
            task = self.task_store.get(task_id)
            active = self.run_store.active_for_task(task_id)
            if active:
                raise RuntimeError(f"Task already has active run {active.id}")
            if task.status == TaskStatus.PROCESSING:
                raise RuntimeError("Task is already processing without a managed run")
            run = self.run_store.create(
                task_id,
                backend=self.backend_name,
                retry_of=retry_of,
                **self._run_metadata(),
            )
            try:
                self.task_store.transition(
                    task.id,
                    expected_statuses={
                        TaskStatus.PENDING,
                        TaskStatus.FAILED,
                        TaskStatus.COMPLETED,
                        TaskStatus.CANCELLED,
                    },
                    expected_active_run_id=None,
                    status=TaskStatus.PROCESSING,
                    stage=TaskStage.QUEUED,
                    stage_message=f"Waiting for {self.backend_name} worker",
                    active_run_id=run.id,
                    last_error=None,
                    last_error_code=None,
                )
            except (KeyError, StateConflict) as error:
                self.run_store.finish(
                    run.id,
                    RunStatus.FAILED,
                    error_code="admission_conflict",
                    error_message=str(error),
                )
                raise RuntimeError(str(error)) from error
            return self.run_store.observe_stage(
                run.id,
                TaskStage.QUEUED,
                f"Waiting for {self.backend_name} worker",
            )

    def _set_stage(
        self,
        task_id: str,
        run_id: str,
        stage: TaskStage,
        message: str,
    ) -> None:
        """Persist one lifecycle-owned stage in both task and run views."""

        self.task_store.transition(
            task_id,
            expected_statuses={TaskStatus.PROCESSING},
            expected_active_run_id=run_id,
            stage=stage,
            stage_message=message,
        )
        self.run_store.observe_stage(run_id, stage, message)

    def submit(self, task_id: str) -> TaskRun:
        """Persist and schedule a run without tying execution to an HTTP request."""
        return self._dispatcher.submit(task_id)

    def start_dispatcher(self) -> None:
        self._dispatcher.start()

    def recover_queued(self) -> int:
        return self._dispatcher.recover_queued()

    def shutdown_dispatcher(self) -> None:
        self._dispatcher.shutdown()

    def dispatcher_status(self) -> dict[str, int]:
        return self._dispatcher.status()

    @abstractmethod
    def build_command(self, task_id: str, run_id: str) -> list[str]:
        """Build the backend command for one managed run."""
        ...

    @abstractmethod
    def run(self, task_id: str, run_id: str) -> None:
        """Execute one managed run and persist its terminal state."""
        ...

    def cancel(self, task_id: str) -> None:
        with self._lock:
            process = self._processes.get(task_id)
        if process and process.poll() is None:
            self._terminate(process)
        active = self.run_store.active_for_task(task_id)
        if active:
            self.task_store.transition(
                task_id,
                expected_statuses={TaskStatus.PROCESSING},
                expected_active_run_id=active.id,
                status=TaskStatus.CANCELLED,
                active_run_id=None,
                last_error=None,
                last_error_code=None,
            )
            self.run_store.finish(
                active.id,
                RunStatus.CANCELLED,
                exit_code=process.poll() if process else None,
            )
        else:
            self.task_store.transition(
                task_id,
                expected_statuses={TaskStatus.PENDING},
                expected_active_run_id=None,
                status=TaskStatus.CANCELLED,
                active_run_id=None,
                last_error=None,
                last_error_code=None,
            )

    def recover_stale(self) -> int:
        """Fail abandoned runs and legacy processing tasks after the stale window."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.stale_seconds)
        recovered = 0
        active_task_ids: set[str] = set()
        for run in self.run_store.list_all():
            if run.status not in {RunStatus.QUEUED, RunStatus.RUNNING}:
                continue
            active_task_ids.add(run.task_id)
            try:
                task = self.task_store.get(run.task_id)
            except KeyError:
                task = None
            with self._lock:
                locally_managed = (
                    task is not None
                    and task.active_run_id == run.id
                    and run.task_id in self._processes
                )
            if locally_managed or run.heartbeat_at >= cutoff:
                continue
            terminal_status = {
                TaskStatus.COMPLETED: RunStatus.COMPLETED,
                TaskStatus.FAILED: RunStatus.FAILED,
                TaskStatus.CANCELLED: RunStatus.CANCELLED,
            }.get(task.status if task else None)
            if terminal_status is not None:
                self.run_store.finish(
                    run.id,
                    terminal_status,
                    error_code=(
                        task.last_error_code or "pipeline_failed"
                        if terminal_status == RunStatus.FAILED
                        else None
                    ),
                    error_message=(task.last_error if task else None),
                )
                recovered += 1
                continue
            message = "AI run heartbeat expired"
            self.run_store.finish(
                run.id,
                RunStatus.TIMED_OUT,
                error_code="stale_heartbeat",
                error_message=message,
            )
            try:
                self.task_store.transition(
                    run.task_id,
                    expected_statuses={TaskStatus.PROCESSING},
                    expected_active_run_id=run.id,
                    status=TaskStatus.FAILED,
                    active_run_id=None,
                    last_error=message,
                    last_error_code="stale_heartbeat",
                )
            except (KeyError, StateConflict):
                pass
            recovered += 1

        for task in self.task_store.list_all():
            if (
                task.status == TaskStatus.PROCESSING
                and task.id not in active_task_ids
                and task.updated_at < cutoff
            ):
                self.task_store.mark_status(
                    task.id,
                    TaskStatus.FAILED,
                    "Legacy processing task expired",
                    error_code="legacy_stale",
                )
                recovered += 1
        return recovered

    def recover_orphaned_running(self) -> int:
        """Close runs whose worker process disappeared with the last app process.

        QUEUED runs remain durable and are rescheduled separately. A RUNNING
        run cannot be resumed safely because its RPC session and subprocess no
        longer exist; retries must always get a fresh run id and clean session.
        """
        recovered = 0
        for run in self.run_store.list_all():
            if run.status != RunStatus.RUNNING:
                continue
            try:
                task = self.task_store.get(run.task_id)
            except KeyError:
                task = None
            terminal_status = {
                TaskStatus.COMPLETED: RunStatus.COMPLETED,
                TaskStatus.FAILED: RunStatus.FAILED,
                TaskStatus.CANCELLED: RunStatus.CANCELLED,
            }.get(task.status if task else None)
            if terminal_status is not None:
                self.run_store.finish(
                    run.id,
                    terminal_status,
                    error_code=(
                        task.last_error_code or "pipeline_failed"
                        if terminal_status == RunStatus.FAILED
                        else None
                    ),
                    error_message=(task.last_error if task else None),
                )
            else:
                message = "AI worker process was lost during application restart"
                self.run_store.finish(
                    run.id,
                    RunStatus.FAILED,
                    error_code="worker_lost",
                    error_message=message,
                )
                self.run_store.update(run.id, retryable=True)
                if task is not None:
                    try:
                        self.task_store.transition(
                            task.id,
                            expected_statuses={TaskStatus.PROCESSING},
                            expected_active_run_id=run.id,
                            status=TaskStatus.FAILED,
                            active_run_id=None,
                            last_error=message,
                            last_error_code="worker_lost",
                        )
                    except StateConflict:
                        pass
            recovered += 1
        return recovered

    def _observe_task(self, run_id: str, task_id: str) -> None:
        task = self.task_store.get(task_id)
        if task.stage:
            self.run_store.observe_stage(run_id, task.stage, task.stage_message)
        else:
            self.run_store.heartbeat(run_id)

    def _fail_start(
        self,
        task_id: str,
        run_id: str,
        message: str,
        error_code: str,
    ) -> None:
        try:
            self.task_store.transition(
                task_id,
                expected_statuses={TaskStatus.PROCESSING},
                expected_active_run_id=run_id,
                status=TaskStatus.FAILED,
                active_run_id=None,
                last_error=message,
                last_error_code=error_code,
            )
        except (KeyError, StateConflict):
            pass
        finally:
            self.run_store.finish(
                run_id,
                RunStatus.FAILED,
                error_code=error_code,
                error_message=message,
            )
            self.run_store.update(
                run_id,
                retryable=self.is_retryable_error(error_code, message),
            )

    @staticmethod
    def is_retryable_error(
        error_code: Optional[str],
        message: Optional[str] = None,
    ) -> bool:
        """Retry only explicitly classified transient transport failures.

        Lifecycle timeouts and generic runner errors stay terminal even when
        their human-readable message contains a transport-related word.
        Backends must map provider responses to one of the codes above.
        """
        del message
        return (error_code or "").lower() in ManagedAiRunner._RETRYABLE_ERROR_CODES

    @staticmethod
    def _terminate(process: subprocess.Popen[Any]) -> None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


__all__ = ["AgentBackend", "ManagedAiRunner"]
