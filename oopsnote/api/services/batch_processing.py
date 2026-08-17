"""Crash-recoverable orchestration for the one-command batch processing API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oopsnote.core import (
    AssetStore,
    BatchProcessJob,
    BatchProcessJobStore,
    BatchProcessSegmentState,
    BatchSessionRecord,
    BatchSessionStore,
    BatchSessionUpdateRequest,
    BatchSourceRenderer,
    TaskCreateRequest,
    TaskStatus,
    TaskStore,
)


class BatchProcessError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class BatchProcessingContext:
    task_store: TaskStore
    asset_store: AssetStore
    session_store: BatchSessionStore
    job_store: BatchProcessJobStore
    session_view: Callable[[BatchSessionRecord], dict[str, Any]]


def _metadata(
    context: BatchProcessingContext,
    record: BatchSessionRecord,
    segment: Any,
    asset_path: str,
) -> dict[str, Any]:
    first_page = min(part.page_index for part in segment.parts)
    filename = Path(asset_path).name
    return {
        "subject": record.subject,
        "notes": record.notes,
        "question_no": str(segment.question_no),
        "source": record.filename,
        "question_type": None,
        "difficulty": None,
        "knowledge_tags": [],
        "error_tags": [],
        "user_tags": [],
        "batch_session_hash": record.file_hash,
        "batch_segment_id": segment.id,
        "batch_page_index": first_page,
        "batch_question_no": segment.question_no,
        "mime_type": "image/png",
        "source_page": first_page + 1,
        "trace": {
            "kind": "batch_segment",
            "source_file_hash": record.file_hash,
            "source_file_name": record.filename,
            "source_file_path": record.asset_path,
            "page_index": first_page,
            "question_no": segment.question_no,
            "segment_id": segment.id,
            "screenshot_path": asset_path,
            "screenshot_filename": filename,
        },
        "selection_snapshot": {
            "schema_version": 1,
            "source_file_hash": record.file_hash,
            "source_file_name": record.filename,
            "source_file_path": record.asset_path,
            "page_count": record.page_count,
            "crop_rect": record.crop_rect.model_dump(mode="json"),
            "column_layout": record.column_layout.model_dump(mode="json"),
            "excluded_page_indices": list(record.excluded_page_indices),
            "segment_id": segment.id,
            "question_no": segment.question_no,
            "parts": [part.model_dump(mode="json") for part in segment.parts],
        },
    }


def _replace_job_segment(
    context: BatchProcessingContext,
    job: BatchProcessJob,
    segment_id: str,
    **updates: Any,
) -> BatchProcessJob:
    states = [
        state.model_copy(update=updates) if state.segment_id == segment_id else state
        for state in job.segments
    ]
    return context.job_store.save(job.model_copy(update={"segments": states}))


def _replace_session_segment(
    context: BatchProcessingContext,
    record: BatchSessionRecord,
    segment_id: str,
    **updates: Any,
) -> BatchSessionRecord:
    segments = [
        segment.model_copy(update=updates) if segment.id == segment_id else segment
        for segment in record.segments
    ]
    return context.session_store.update(
        record.file_hash,
        BatchSessionUpdateRequest(segments=segments),
        expected_revision=record.revision,
    )


def _bootstrap_tasks(
    context: BatchProcessingContext,
    record: BatchSessionRecord,
    job: BatchProcessJob,
) -> dict[str, Any]:
    """Use persisted links normally; scan tasks only after an interrupted cross-store write."""
    task_ids = {segment.id: segment.task_id for segment in record.segments if segment.task_id}
    task_ids.update({state.segment_id: state.task_id for state in job.segments if state.task_id})
    tasks: dict[str, Any] = {}
    missing_ids: set[str] = set()
    for segment_id, task_id in task_ids.items():
        try:
            tasks[segment_id] = context.task_store.get(task_id)
        except KeyError:
            missing_ids.add(segment_id)
    needed = {
        segment.id
        for segment in record.segments
        if segment.status == "pending" and segment.id not in tasks
    }
    if needed or missing_ids:
        for task in sorted(context.task_store.list_all(), key=lambda item: item.created_at):
            if task.metadata.get("batch_session_hash") != record.file_hash:
                continue
            segment_id = str(task.metadata.get("batch_segment_id") or "")
            if segment_id in needed or segment_id in missing_ids:
                tasks[segment_id] = task
    return tasks


def process_batch_session(
    context: BatchProcessingContext,
    file_hash: str,
    backend: str,
    runner: Any,
    *,
    expected_revision: int,
    retry_segment_id: str | None = None,
) -> dict[str, Any]:
    runner.recover_stale()
    with context.session_store.session_lock(file_hash):
        try:
            record = context.session_store.get(file_hash)
        except KeyError as error:
            raise BatchProcessError(
                404, "batch_session_not_found", "Batch session not found"
            ) from error
        if record.revision != expected_revision:
            raise BatchProcessError(
                409,
                "batch_revision_conflict",
                f"Batch session revision is {record.revision}, expected {expected_revision}",
                retryable=True,
            )
        if not context.asset_store.matches_sha256(record.asset_path, record.file_hash):
            raise BatchProcessError(
                409,
                "batch_source_unavailable",
                "原始批量文件不可用，请重新导入相同内容的文件以恢复批量扫描",
            )
        retrying_segment = None
        if retry_segment_id is not None:
            retrying_segment = next(
                (segment for segment in record.segments if segment.id == retry_segment_id),
                None,
            )
            if retrying_segment is None:
                raise BatchProcessError(404, "batch_segment_not_found", "Batch segment not found")

            if retrying_segment.task_id:
                try:
                    context.task_store.get(retrying_segment.task_id)
                except KeyError:
                    # A batch segment owns this reference. Remove the stale link
                    # before entering the existing task-creation pipeline.
                    record = context.session_store.clear_stale_task_link(
                        record.file_hash,
                        retrying_segment.id,
                        retrying_segment.task_id,
                        expected_revision=record.revision,
                    )
                else:
                    record = _replace_session_segment(
                        context,
                        record,
                        retrying_segment.id,
                        status="pending",
                        review_reason=None,
                        review_previous_status=None,
                        review_resolved=False,
                        error=None,
                    )
            else:
                record = _replace_session_segment(
                    context,
                    record,
                    retrying_segment.id,
                    status="pending",
                    review_reason=None,
                    review_previous_status=None,
                    review_resolved=False,
                    error=None,
                )

        pending = [
            segment
            for segment in record.segments
            if segment.status == "pending"
            and (retry_segment_id is None or segment.id == retry_segment_id)
        ]
        requested_count = len(pending)
        if not pending:
            return {
                "requested": 0,
                "created": 0,
                "queued": 0,
                "failed": 0,
                "items": [],
                "session": context.session_view(record),
            }
        if not record.crop_confirmed:
            raise BatchProcessError(
                409,
                "batch_crop_unconfirmed",
                "Batch crop must be confirmed before processing",
            )
        number_counts: dict[int, int] = {}
        for segment in pending:
            if segment.question_no is not None:
                number_counts[segment.question_no] = number_counts.get(segment.question_no, 0) + 1
        invalid_numbers: dict[str, str] = {}
        for segment in pending:
            if segment.question_no is None:
                invalid_numbers[segment.id] = "请先标注题号后再处理"
            elif number_counts[segment.question_no] > 1:
                invalid_numbers[segment.id] = f"题号 {segment.question_no} 与其他待处理选框重复"
        review_items: list[dict[str, Any]] = []
        for segment in pending:
            error = invalid_numbers.get(segment.id)
            if error is None:
                continue
            record = _replace_session_segment(
                context,
                record,
                segment.id,
                status="needs_review",
                review_reason="other",
                review_previous_status="pending",
                review_resolved=False,
                error=error,
            )
            review_items.append(
                {
                    "segment_id": segment.id,
                    "question_no": segment.question_no,
                    "task_id": None,
                    "run_id": None,
                    "status": "needs_review",
                    "error": error,
                }
            )
        pending = [segment for segment in record.segments if segment.status == "pending"]
        if not pending:
            return {
                "requested": requested_count,
                "created": 0,
                "queued": 0,
                "failed": 0,
                "needs_review": len(review_items),
                "items": review_items,
                "session": context.session_view(record),
            }

        try:
            job = context.job_store.get(file_hash)
        except KeyError:
            job = BatchProcessJob(file_hash=file_hash, backend=backend)
        known = {state.segment_id for state in job.segments}
        new_states = [
            BatchProcessSegmentState(segment_id=segment.id, question_no=segment.question_no)
            for segment in pending
            if segment.id not in known
        ]
        job = context.job_store.save(
            job.model_copy(
                update={
                    "backend": backend,
                    "status": "running",
                    "segments": [*job.segments, *new_states],
                }
            )
        )
        tasks = _bootstrap_tasks(context, record, job)
        needs_render = [segment for segment in pending if segment.id not in tasks]

        try:
            source_path = context.asset_store.resolve(record.asset_path)
            with BatchSourceRenderer(source_path, record.mime_type) as renderer:
                if record.page_count and renderer.page_count != record.page_count:
                    raise ValueError(
                        f"Saved page count is {record.page_count}, source contains {renderer.page_count}"
                    )
                for segment in needs_render:
                    renderer.validate_segment(segment, record.crop_rect)

                created_count = 0
                queued_count = 0
                failed_count = 0
                items: list[dict[str, Any]] = list(review_items)
                for segment in pending:
                    task = tasks.get(segment.id)
                    if task is None:
                        job = _replace_job_segment(
                            context, job, segment.id, status="rendering", error=None
                        )
                        image = renderer.render_segment(segment, record.crop_rect)
                        stable_name = (
                            f"batch-{record.file_hash}-{segment.id}-q{segment.question_no}"
                        )
                        asset_path = context.asset_store.save_bytes(
                            image,
                            f"{stable_name}.png",
                            stable_name=stable_name,
                        )
                        job = _replace_job_segment(
                            context, job, segment.id, status="asset_saved", asset_path=asset_path
                        )
                        metadata = _metadata(context, record, segment, asset_path)
                        task = context.task_store.create(
                            TaskCreateRequest(
                                subject=record.subject,
                                asset_path=asset_path,
                                metadata=metadata,
                            )
                        )
                        tasks[segment.id] = task
                        created_count += 1
                        job = _replace_job_segment(
                            context, job, segment.id, status="task_created", task_id=task.id
                        )
                    elif not any(
                        state.segment_id == segment.id and state.task_id == task.id
                        for state in job.segments
                    ):
                        job = _replace_job_segment(
                            context, job, segment.id, status="task_created", task_id=task.id
                        )

                    run_id = task.active_run_id
                    error_message: str | None = None
                    if task.status == TaskStatus.PENDING or (
                        retrying_segment is not None
                        and segment.id == retrying_segment.id
                        and task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}
                    ):
                        try:
                            run = runner.submit(task.id)
                            run_id = run.id
                            task = context.task_store.get(task.id)
                            queued_count += 1
                        except RuntimeError as runtime_error:
                            task = context.task_store.get(task.id)
                            if task.status != TaskStatus.PROCESSING:
                                error_message = str(runtime_error)
                    if task.status == TaskStatus.COMPLETED:
                        status = "completed"
                    elif task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED} or error_message:
                        status = "failed"
                        error_message = (
                            error_message or task.last_error or "Task could not be queued"
                        )
                        failed_count += 1
                    else:
                        status = "processing"
                    job = _replace_job_segment(
                        context,
                        job,
                        segment.id,
                        status=status,
                        task_id=task.id,
                        run_id=run_id,
                        error=error_message,
                    )
                    record = _replace_session_segment(
                        context,
                        record,
                        segment.id,
                        task_id=task.id,
                        status=status,
                        error=error_message,
                    )
                    items.append(
                        {
                            "segment_id": segment.id,
                            "question_no": segment.question_no,
                            "task_id": task.id,
                            "run_id": run_id,
                            "status": status,
                            "error": error_message,
                        }
                    )
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as error:
            context.job_store.save(job.model_copy(update={"status": "failed"}))
            raise BatchProcessError(
                500,
                "batch_processing_failed",
                f"Batch rendering or processing failed: {error}",
            ) from error

        final_status = "partial" if failed_count else "submitted"
        job = context.job_store.save(job.model_copy(update={"status": final_status}))
        return {
            "job_id": job.id,
            "job_status": job.status,
            "requested": requested_count,
            "created": created_count,
            "queued": queued_count,
            "failed": failed_count,
            "needs_review": len(review_items),
            "items": items,
            "session": context.session_view(record),
        }


__all__ = ["BatchProcessError", "BatchProcessingContext", "process_batch_session"]
