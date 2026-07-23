"""Shared lifecycle for managed OopsNote AI task workers."""

from __future__ import annotations

import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

from oopsnote.core import RunStatus, RunStore, TaskRun, TaskStage, TaskStatus, TaskStore


class AgentBackend(Protocol):
    """The process-specific command contract used by a managed task runner."""

    name: str

    def build_command(self, task_id: str, run_id: str) -> list[str]: ...


class ManagedAiRunner:
    """Own task/run state independently from a specific agent process."""

    backend_name = "unknown"

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

    def _run_metadata(self) -> dict[str, Any]:
        return {}

    def enqueue(self, task_id: str) -> TaskRun:
        """Create a run and move a task into the managed processing state."""
        task = self.task_store.get(task_id)
        active = self.run_store.active_for_task(task_id)
        if active:
            raise RuntimeError(f"Task already has active run {active.id}")
        if task.status == TaskStatus.PROCESSING:
            raise RuntimeError("Task is already processing without a managed run")
        run = self.run_store.create(
            task_id,
            backend=self.backend_name,
            **self._run_metadata(),
        )
        self.task_store.update(
            task.id,
            status=TaskStatus.PROCESSING,
            stage=TaskStage.QUEUED,
            stage_message=f"Waiting for {self.backend_name} worker",
            active_run_id=run.id,
            last_error=None,
        )
        return run

    def build_command(self, task_id: str, run_id: str) -> list[str]:
        raise NotImplementedError

    def run(self, task_id: str, run_id: str) -> None:
        raise NotImplementedError

    def cancel(self, task_id: str) -> None:
        with self._lock:
            process = self._processes.get(task_id)
        if process and process.poll() is None:
            self._terminate(process)
        active = self.run_store.active_for_task(task_id)
        self.task_store.mark_status(task_id, TaskStatus.CANCELLED)
        if active:
            self.run_store.finish(
                active.id,
                RunStatus.CANCELLED,
                exit_code=process.poll() if process else None,
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
            with self._lock:
                locally_managed = run.task_id in self._processes
            if locally_managed or run.heartbeat_at >= cutoff:
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
                        "pipeline_failed"
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
                self.task_store.mark_status(run.task_id, TaskStatus.FAILED, message)
            except KeyError:
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
                )
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
            self.task_store.mark_status(task_id, TaskStatus.FAILED, message)
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
        """Only transport and provider throttling failures are safe to retry."""
        text = f"{error_code or ''} {message or ''}".lower()
        return any(
            marker in text
            for marker in (
                "network",
                "connection",
                "timeout",
                "rate_limit",
                "rate limit",
                "429",
                "503",
            )
        )

    @staticmethod
    def _terminate(process: subprocess.Popen[Any]) -> None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


__all__ = ["AgentBackend", "ManagedAiRunner"]
