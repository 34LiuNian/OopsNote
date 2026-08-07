"""JSON execution projection coordinated with the quota control plane."""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from oopsnote.core.models import (
    DiagramRunMode,
    DiagramRunStep,
    RunPurpose,
    RunStatus,
    TaskRun,
)
from oopsnote.core.store import RunStore
from oopsnote.core.workspace import WorkspaceId

from .quota import QuotaError, QuotaService


class QuotaAwareRunStore(RunStore):
    """Keep JSON telemetry as a projection while control SQLite owns admission."""

    def __init__(self, base_dir, *, workspace_id: WorkspaceId, quota: QuotaService) -> None:
        super().__init__(base_dir)
        self.workspace_id = WorkspaceId.parse(workspace_id)
        self.quota = quota

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
        previous_runs = [
            run for run in self.list_for_task(task_id)
            if run.purpose == purpose and run.diagram_item_id == diagram_item_id
        ]
        attempt = 1 + max((run.attempt for run in previous_runs), default=0)
        run_id = uuid4().hex
        if retry_of is None:
            operation_key = (
                f"task:{task_id}:purpose:{purpose.value}:item:{diagram_item_id or '-'}:attempt:{attempt}"
            )
            admission = self.quota.admit_run(
                self.workspace_id,
                task_id=task_id,
                purpose=purpose,
                idempotency_key=operation_key,
                run_id=run_id,
            )
        else:
            reservation_id = retry_of.quota_reservation_id
            if not reservation_id:
                raise QuotaError("retry_not_eligible", "Retry source has no quota reservation")
            admission = self.quota.admit_retry(
                self.workspace_id,
                previous_run_id=retry_of.id,
                task_id=task_id,
                purpose=purpose,
                run_id=run_id,
            )
        try:
            run = super().create(
                task_id,
                prompt_version,
                backend=backend,
                runtime_kind=runtime_kind,
                runtime_version=runtime_version,
                provider=provider,
                model=model,
                provider_profile_snapshot=provider_profile_snapshot,
                retry_of=retry_of,
                purpose=purpose,
                priority=priority,
                diagram_item_id=diagram_item_id,
                diagram_mode=diagram_mode,
                diagram_instruction=diagram_instruction,
                diagram_max_candidates=diagram_max_candidates,
                diagram_step=diagram_step,
                run_id=admission.run_id,
                workspace_id=self.workspace_id,
                quota_reservation_id=admission.reservation_id,
            )
        except Exception:
            self.quota.settle_run(
                self.workspace_id,
                admission.run_id,
                status="failed",
                reason="json_projection_create_failed",
            )
            raise
        return run

    def finish(
        self,
        run_id: str,
        status: RunStatus,
        *,
        exit_code: Optional[int] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> TaskRun:
        run = super().finish(
            run_id,
            status,
            exit_code=exit_code,
            error_code=error_code,
            error_message=error_message,
        )
        if status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        } and run.quota_reservation_id:
            self.quota.settle_run(
                self.workspace_id,
                run_id,
                status=status.value,
                reason=error_code or error_message,
            )
        return run

    def start(
        self,
        run_id: str,
        pid: Optional[int],
        log_path: str,
        *,
        worker_id: Optional[str] = None,
    ) -> TaskRun:
        if not self.claim_execution(run_id):
            raise QuotaError("concurrency_exceeded", "Concurrent run limit exceeded")
        try:
            return super().start(run_id, pid, log_path, worker_id=worker_id)
        except Exception:
            self.defer_execution(run_id)
            raise

    def claim_execution(self, run_id: str) -> bool:
        try:
            self.quota.start_run(self.workspace_id, run_id)
        except QuotaError as error:
            if error.code == "concurrency_exceeded":
                return False
            raise
        return True

    def defer_execution(self, run_id: str) -> None:
        self.quota.defer_run(self.workspace_id, run_id)

    def yield_run(self, run_id: str) -> TaskRun:
        run = super().yield_run(run_id)
        self.defer_execution(run_id)
        return run

    def reconcile_control_runs(self) -> int:
        """Settle control rows from terminal JSON projections after a restart."""
        reconciled = 0
        for run in self.list_all():
            if run.quota_reservation_id and run.status in {
                RunStatus.COMPLETED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                self.quota.settle_run(
                    self.workspace_id,
                    run.id,
                    status=run.status.value,
                    reason=run.error_code or run.error_message,
                )
                reconciled += 1
        return reconciled
