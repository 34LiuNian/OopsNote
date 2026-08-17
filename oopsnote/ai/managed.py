"""Shared lifecycle for managed OopsNote AI task workers."""

from __future__ import annotations

import contextlib
import threading
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from oopsnote.ai.dispatcher import ManagedTaskDispatcher
from oopsnote.ai.run_control import ActiveRunControl
from oopsnote.core import (
    DiagramRunMode,
    DiagramRunStep,
    DiagramStatus,
    RunPurpose,
    RunStatus,
    RunStore,
    StateConflict,
    TaskRun,
    TaskStage,
    TaskStatus,
    TaskStore,
)


class LifecycleAdmissionError(RuntimeError):
    """A stable lifecycle-owned rejection before a run is scheduled."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ManagedAiRunner(ABC):
    """Own task/run state independently from a specific agent process."""

    _RETRYABLE_ERROR_CODES = frozenset(
        {
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
            "renderer_timeout",
            "renderer_unavailable",
            "service_unavailable",
            "429",
            "503",
        }
    )

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
        self._active_controls: dict[str, ActiveRunControl] = {}
        self._lock = threading.RLock()
        worker_count = max(1, int(getattr(self, "max_concurrent_tasks", 1)))
        self._dispatcher = ManagedTaskDispatcher(self, worker_count)

    def _run_metadata(self, task_id: str) -> dict[str, Any]:
        del task_id
        return {}

    def _retry_run_metadata(self, previous: TaskRun) -> dict[str, Any]:
        """Return immutable metadata for a fresh retry of the same execution choice."""
        return self._run_metadata(previous.task_id)

    def _diagram_run_metadata(self, task_id: str) -> dict[str, Any]:
        del task_id
        raise RuntimeError(f"{self.backend_name} does not support diagram reconstruction")

    def enqueue(
        self,
        task_id: str,
        *,
        retry_of: TaskRun | None = None,
    ) -> TaskRun:
        """Create a run and move a task into the managed processing state."""
        # One local API process may receive concurrent requests for the same
        # task through different runtime runners. Admission is one transaction
        # at the lifecycle level even though task/run JSON files are separate.
        with self._admission_lock:
            task = self.task_store.get(task_id)
            active = self.run_store.active_for_task(task_id)
            if active:
                raise LifecycleAdmissionError(
                    "task_busy", f"Task already has active run {active.id}"
                )
            if task.status == TaskStatus.PROCESSING:
                raise LifecycleAdmissionError(
                    "task_busy",
                    "Task is already processing without a managed run",
                )
            metadata = (
                self._retry_run_metadata(retry_of)
                if retry_of is not None
                else self._run_metadata(task_id)
            )
            run = self.run_store.create(
                task_id,
                backend=self.backend_name,
                retry_of=retry_of,
                **metadata,
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

    def enqueue_diagram(
        self,
        task_id: str,
        item_id: str,
        *,
        mode: DiagramRunMode = DiagramRunMode.AUTO,
        instruction: str | None = None,
        max_candidates: int = 4,
    ) -> TaskRun:
        """Admit an independent diagram run without changing problem-task status."""
        priority = 10 if mode in {DiagramRunMode.CONTINUE, DiagramRunMode.REBUILD} else 20
        with self._admission_lock:
            task = self.task_store.get(task_id)
            item = next((item for item in task.diagram_items if item.id == item_id), None)
            if item is None:
                raise KeyError(f"Diagram item {item_id} not found")
            active = self.run_store.active_for_task(
                task_id,
                purpose=RunPurpose.DIAGRAM,
                diagram_item_id=item_id,
            )
            if active or item.active_run_id:
                active_id = active.id if active else item.active_run_id
                raise LifecycleAdmissionError(
                    "diagram_run_active",
                    f"Diagram already has active run {active_id}",
                )
            metadata = self._diagram_run_metadata(task_id)
            run = self.run_store.create(
                task_id,
                backend=self.backend_name,
                purpose=RunPurpose.DIAGRAM,
                priority=priority,
                diagram_item_id=item_id,
                diagram_mode=mode,
                diagram_instruction=(instruction or "").strip() or None,
                diagram_max_candidates=max_candidates,
                diagram_step=DiagramRunStep.GENERATE,
                **metadata,
            )
            try:
                self.task_store.update_diagram_item(
                    task_id,
                    item_id,
                    expected_active_run_id=None,
                    active_run_id=run.id,
                    status=DiagramStatus.QUEUED,
                    needs_review=False,
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
                raise LifecycleAdmissionError("admission_conflict", str(error)) from error
            return self.run_store.observe_stage(
                run.id,
                TaskStage.DIAGRAM_GENERATING,
                f"Waiting for {self.backend_name} diagram worker",
            )

    def submit(self, task_id: str) -> TaskRun:
        """Persist and schedule a run without tying execution to an HTTP request."""
        return self._dispatcher.submit(task_id)

    def submit_diagram(
        self,
        task_id: str,
        item_id: str,
        *,
        mode: DiagramRunMode = DiagramRunMode.AUTO,
        instruction: str | None = None,
        max_candidates: int = 4,
    ) -> TaskRun:
        run = self.enqueue_diagram(
            task_id,
            item_id,
            mode=mode,
            instruction=instruction,
            max_candidates=max_candidates,
        )
        self._dispatcher.schedule(task_id, run.id)
        return run

    def is_run_dispatchable(self, run: TaskRun) -> bool:
        try:
            task = self.task_store.get(run.task_id)
        except KeyError:
            return False
        if run.purpose == RunPurpose.PROBLEM:
            return task.status == TaskStatus.PROCESSING and task.active_run_id == run.id
        item = next(
            (item for item in task.diagram_items if item.id == run.diagram_item_id),
            None,
        )
        return item is not None and item.active_run_id == run.id

    def handle_dispatcher_error(
        self,
        task_id: str,
        run_id: str,
        error: Exception,
    ) -> None:
        try:
            run = self.run_store.get(run_id)
        except KeyError:
            return
        if run.purpose == RunPurpose.DIAGRAM and run.diagram_item_id:
            with contextlib.suppress(KeyError, StateConflict):
                self.task_store.update_diagram_item(
                    task_id,
                    run.diagram_item_id,
                    expected_active_run_id=run_id,
                    status=DiagramStatus.FAILED,
                    active_run_id=None,
                    needs_review=False,
                    last_error=str(error),
                    last_error_code="dispatcher_error",
                )
            return
        try:
            task = self.task_store.get(task_id)
            if task.active_run_id == run_id:
                self.task_store.transition(
                    task_id,
                    expected_statuses={TaskStatus.PROCESSING},
                    expected_active_run_id=run_id,
                    status=TaskStatus.FAILED,
                    active_run_id=None,
                    stage_message=str(error),
                    last_error=str(error),
                    last_error_code="dispatcher_error",
                )
        except (KeyError, RuntimeError):
            pass

    def start_dispatcher(self) -> None:
        self._dispatcher.start()

    def recover_queued(self) -> int:
        return self._dispatcher.recover_queued()

    def shutdown_dispatcher(self) -> None:
        self._dispatcher.shutdown()

    def dispatcher_status(self) -> dict[str, int]:
        return self._dispatcher.status()

    @abstractmethod
    def run(self, task_id: str, run_id: str) -> None:
        """Execute one managed run and persist its terminal state."""
        ...

    def cancel(self, task_id: str) -> None:
        with self._lock:
            control = self._active_controls.get(task_id)
        if control and control.is_active():
            control.cancel()
        self._mark_cancelled(task_id, control.exit_code if control else None)

    def cancel_diagram(self, task_id: str, item_id: str) -> None:
        active = self.run_store.active_for_task(
            task_id,
            purpose=RunPurpose.DIAGRAM,
            diagram_item_id=item_id,
        )
        if active is None:
            return
        control_key = f"diagram:{active.id}"
        with self._lock:
            control = self._active_controls.get(control_key)
        if control and control.is_active():
            control.cancel()
        try:
            self.task_store.update_diagram_item(
                task_id,
                item_id,
                expected_active_run_id=active.id,
                status=DiagramStatus.CANCELLED,
                active_run_id=None,
                needs_review=False,
                last_error=None,
                last_error_code=None,
            )
        except (KeyError, StateConflict):
            return
        self.run_store.finish(active.id, RunStatus.CANCELLED)

    def _mark_cancelled(self, task_id: str, exit_code: int | None = None) -> None:
        """Apply the shared cancellation terminal transition."""
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
                exit_code=exit_code,
            )
        else:
            # Cancellation is idempotent after any terminal transition.  In
            # particular, a late request must never rewrite a successful
            # finalize or turn an already diagnosed failure into a new state.
            task = self.task_store.get(task_id)
            if task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                return
            if task.status == TaskStatus.PROCESSING:
                raise RuntimeError("Task is processing without an active managed run")
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
        """Fail abandoned managed runs after the stale window."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self.stale_seconds)
        recovered = 0
        for run in self.run_store.list_all():
            if run.backend != self.backend_name or run.status not in {
                RunStatus.QUEUED,
                RunStatus.RUNNING,
            }:
                continue
            try:
                task = self.task_store.get(run.task_id)
            except KeyError:
                task = None
            control_key = f"diagram:{run.id}" if run.purpose == RunPurpose.DIAGRAM else run.task_id
            with self._lock:
                locally_managed = control_key in self._active_controls
            if locally_managed or run.heartbeat_at >= cutoff:
                continue
            if run.purpose == RunPurpose.DIAGRAM:
                message = "Diagram run heartbeat expired"
                self.run_store.finish(
                    run.id,
                    RunStatus.TIMED_OUT,
                    error_code="stale_heartbeat",
                    error_message=message,
                )
                if run.diagram_item_id:
                    with contextlib.suppress(KeyError, StateConflict):
                        self.task_store.update_diagram_item(
                            run.task_id,
                            run.diagram_item_id,
                            expected_active_run_id=run.id,
                            status=DiagramStatus.FAILED,
                            active_run_id=None,
                            needs_review=False,
                            last_error=message,
                            last_error_code="stale_heartbeat",
                        )
                recovered += 1
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
            with contextlib.suppress(KeyError, StateConflict):
                self.task_store.transition(
                    run.task_id,
                    expected_statuses={TaskStatus.PROCESSING},
                    expected_active_run_id=run.id,
                    status=TaskStatus.FAILED,
                    active_run_id=None,
                    stage_message=message,
                    last_error=message,
                    last_error_code="stale_heartbeat",
                )
            recovered += 1

        return recovered

    def recover_orphaned_running(self) -> int:
        """Close runs whose worker process disappeared with the last app process.

        QUEUED runs remain durable and are rescheduled separately. A RUNNING
        run cannot be resumed safely because its provider request state no
        longer exists; retries must always get a fresh run id.
        """
        recovered = 0
        for run in self.run_store.list_all():
            if run.backend != self.backend_name or run.status != RunStatus.RUNNING:
                continue
            try:
                task = self.task_store.get(run.task_id)
            except KeyError:
                task = None
            if run.purpose == RunPurpose.DIAGRAM:
                message = "Diagram worker was lost during application restart"
                self.run_store.finish(
                    run.id,
                    RunStatus.FAILED,
                    error_code="worker_lost",
                    error_message=message,
                )
                self.run_store.update(run.id, retryable=True)
                if task is not None and run.diagram_item_id:
                    with contextlib.suppress(KeyError, StateConflict):
                        self.task_store.update_diagram_item(
                            task.id,
                            run.diagram_item_id,
                            expected_active_run_id=run.id,
                            status=DiagramStatus.FAILED,
                            active_run_id=None,
                            needs_review=False,
                            last_error=message,
                            last_error_code="worker_lost",
                        )
                recovered += 1
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
                    with contextlib.suppress(StateConflict):
                        self.task_store.transition(
                            task.id,
                            expected_statuses={TaskStatus.PROCESSING},
                            expected_active_run_id=run.id,
                            status=TaskStatus.FAILED,
                            active_run_id=None,
                            stage_message=message,
                            last_error=message,
                            last_error_code="worker_lost",
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
            self.task_store.transition(
                task_id,
                expected_statuses={TaskStatus.PROCESSING},
                expected_active_run_id=run_id,
                status=TaskStatus.FAILED,
                active_run_id=None,
                stage_message=message,
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

    def retry_if_eligible(
        self,
        task_id: str,
        run_id: str,
        *,
        execute_inline: bool = False,
    ) -> TaskRun | None:
        """Schedule a bounded fresh retry under the same managed backend.

        The failed run remains terminal evidence. This never switches provider
        or backend and never retries deterministic validation/state failures.
        """
        completed = self.run_store.get(run_id)
        if not completed.retryable or completed.retry_count >= 2:
            return None
        task = self.task_store.get(task_id)
        if task.status != TaskStatus.FAILED or task.active_run_id:
            return None
        retry = self.enqueue(task_id, retry_of=completed)
        if execute_inline:
            self.run(task_id, retry.id)
        else:
            self._dispatcher.schedule(task_id, retry.id)
        return retry

    def retry_diagram_if_eligible(self, task_id: str, run_id: str) -> TaskRun | None:
        """Retry only a classified transient diagram failure as a fresh managed run."""
        completed = self.run_store.get(run_id)
        if (
            completed.purpose != RunPurpose.DIAGRAM
            or not completed.retryable
            or completed.retry_count >= 2
            or not completed.diagram_item_id
            or not completed.diagram_mode
            or not completed.diagram_max_candidates
        ):
            return None
        with self._admission_lock:
            task = self.task_store.get(task_id)
            item = next(
                (item for item in task.diagram_items if item.id == completed.diagram_item_id),
                None,
            )
            if item is None or item.active_run_id:
                return None
            retry = self.run_store.create(
                task_id,
                backend=completed.backend,
                purpose=RunPurpose.DIAGRAM,
                priority=completed.priority,
                diagram_item_id=completed.diagram_item_id,
                diagram_mode=completed.diagram_mode,
                diagram_instruction=completed.diagram_instruction,
                diagram_max_candidates=completed.diagram_max_candidates,
                diagram_step=completed.diagram_step,
                diagram_transport=completed.diagram_transport,
                provider=completed.provider,
                model=completed.model,
                prompt_version=completed.prompt_version,
                provider_profile_snapshot=completed.provider_profile_snapshot,
                retry_of=completed,
            )
            retry = self.run_store.update(
                retry.id,
                diagram_candidate_id=completed.diagram_candidate_id,
            )
            self.task_store.update_diagram_item(
                task_id,
                completed.diagram_item_id,
                expected_active_run_id=None,
                active_run_id=retry.id,
                status=DiagramStatus.QUEUED,
                needs_review=False,
                last_error=None,
                last_error_code=None,
            )
        self._dispatcher.schedule(task_id, retry.id)
        return retry

    @staticmethod
    def is_retryable_error(
        error_code: str | None,
        message: str | None = None,
    ) -> bool:
        """Retry only explicitly classified transient transport failures.

        Lifecycle timeouts and generic runner errors stay terminal even when
        their human-readable message contains a transport-related word.
        Backends must map provider responses to one of the codes above.
        """
        del message
        return (error_code or "").lower() in ManagedAiRunner._RETRYABLE_ERROR_CODES

    def _register_control(self, task_id: str, control: ActiveRunControl) -> None:
        with self._lock:
            self._active_controls[task_id] = control

    def _clear_control(self, task_id: str, control: ActiveRunControl) -> None:
        with self._lock:
            if self._active_controls.get(task_id) is control:
                self._active_controls.pop(task_id, None)


__all__ = ["ManagedAiRunner"]
