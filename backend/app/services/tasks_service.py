from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import HTTPException

from ..models import (
    CropRegion,
    DetectionOutput,
    PipelineResult,
    ProblemSummary,
    ProblemsResponse,
    TaggingResult,
    TaskCreateRequest,
    TaskStatus,
    TaskSummary,
    TasksResponse,
)
from ..tags import TagDimension

logger = logging.getLogger(__name__)


class _TaskCancelled(Exception):
    pass


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class TasksService:
    def __init__(self, *, repository, pipeline, asset_store, tag_store) -> None:
        self.repository = repository
        self.pipeline = pipeline
        self.asset_store = asset_store
        self.tag_store = tag_store

        self._task_cancel_lock = threading.Lock()
        self._task_cancelled: set[str] = set()

        self._processing_lock = threading.Lock()
        self._processing_inflight: set[str] = set()

        # Track base directory for streams (for backward compatibility)
        self.streams_dir = (
            Path(repository.base_dir).parent / "task_streams"
            if hasattr(repository, "base_dir") and repository.base_dir
            else Path("storage/task_streams")
        )
        self.streams_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _merge_unique_tags(prefix: list[str], tail: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for item in [*prefix, *tail]:
            s = str(item).strip()
            if not s:
                continue
            key = s.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        return out

    # -------------------- workers --------------------

    def start_processing_in_background(self, task_id: str) -> None:
        """Process a task in a background thread without a complex queue."""
        try:
            self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # Fire and forget thread for simplified background processing
        thread = threading.Thread(
            target=self.process_task_sync,
            args=(task_id,),
            name=f"task-bg-{task_id}",
            daemon=True,
        )
        thread.start()

    # -------------------- basic CRUD --------------------

    def iter_tasks(self):
        """Return a snapshot iterable of all task records for read-only API views."""
        return self.repository.list_all().values()

    def create_task(self, payload, *, auto_process: bool = True):
        """Create a task from payload and optionally process it."""
        task = self.repository.create(payload)
        if auto_process:
            task = self.process_task_sync(task.id)
        return task

    def upload_task(self, upload, *, auto_process: bool = True):
        """Create a task from an upload and optionally process it."""
        if upload.image_base64:
            asset = self.asset_store.save_base64(
                upload.image_base64,
                mime_type=upload.mime_type,
                filename=upload.filename,
            )
            derived_url = f"https://assets.local/{asset.asset_id}"
        else:
            assert upload.image_url is not None
            asset = self.asset_store.register_remote(
                str(upload.image_url), upload.mime_type
            )
            derived_url = str(upload.image_url)

        payload = TaskCreateRequest(
            image_url=derived_url,
            subject=upload.subject,
            grade=upload.grade,
            notes=upload.notes,
            question_no=upload.question_no,
            question_type=upload.question_type,
            mock_problem_count=upload.mock_problem_count,
            difficulty=upload.difficulty,
            source=upload.source,
            options=upload.options,
            knowledge_tags=upload.knowledge_tags,
            error_tags=upload.error_tags,
            user_tags=upload.user_tags,
        )

        task = self.repository.create(payload, asset=asset)
        if auto_process:
            task = self.process_task_sync(task.id)
        return task

    def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        active_only: bool = False,
        subject: str | None = None,
    ) -> TasksResponse:
        """List tasks with optional filtering by status and subject."""
        tasks = list(self.repository.list_all().values())

        stale_seconds = _int_env("TASK_STALE_SECONDS", 1800)
        now = datetime.now(timezone.utc)
        for t in tasks:
            try:
                if t.status == TaskStatus.PROCESSING:
                    age = (now - t.updated_at).total_seconds()
                    with self._processing_lock:
                        inflight = t.id in self._processing_inflight
                    if (not inflight) and age > stale_seconds:
                        self.repository.patch_task(
                            t.id,
                            status=TaskStatus.FAILED,
                            last_error="Task processing stale (backend restarted or worker crashed)",
                            stage="failed",
                            stage_message="处理超时（可能后端重启/崩溃），请重新提交或手动重试处理",
                        )
            except Exception:  # pylint: disable=broad-exception-caught
                continue

        tasks = list(self.repository.list_all().values())

        if subject is not None:
            tasks = [t for t in tasks if t.payload.subject == subject]

        if active_only:
            tasks = [
                t
                for t in tasks
                if t.status in (TaskStatus.PENDING, TaskStatus.PROCESSING)
            ]
        elif status is not None:
            tasks = [t for t in tasks if t.status == status]

        tasks.sort(key=lambda t: t.created_at, reverse=True)

        items = [
            TaskSummary(
                id=t.id,
                status=t.status,
                stage=getattr(t, "stage", None),
                stage_message=getattr(t, "stage_message", None),
                created_at=t.created_at,
                updated_at=t.updated_at,
                subject=t.payload.subject,
                question_no=getattr(t.payload, "question_no", None),
                asset={
                    "asset_id": t.asset.asset_id,
                    "path": f"/assets/{Path(t.asset.path).name}" if t.asset and t.asset.path else None,
                    "mime_type": t.asset.mime_type,
                } if t.asset else None,
            )
            for t in tasks
        ]
        return TasksResponse(items=items)

    def get_task(self, task_id: str):
        """Fetch a task by id or raise 404."""
        try:
            return self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def process_task(self, task_id: str, *, background: bool = False):
        """Process a task in foreground or background."""
        if background:
            self.start_processing_in_background(task_id)
            return self.repository.get(task_id)
        return self.process_task_sync(task_id)

    def retry_task(
        self, task_id: str, *, background: bool = True
    ):
        """Retry a task (failed or completed).

        This is a convenience wrapper around processing that also clears cancellation
        flags.
        """

        try:
            task = self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if task.status == TaskStatus.PROCESSING:
            return task

        with self._task_cancel_lock:
            self._task_cancelled.discard(task_id)

        try:
            self.repository.patch_task(
                task_id, stage="retrying", stage_message="准备重试"
            )
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        return self.process_task(task_id, background=background)

    # -------------------- per-problem operations --------------------

    def _get_problem(self, task, problem_id: str):
        for problem in task.problems:
            if problem.problem_id == problem_id:
                return problem
        raise HTTPException(
            status_code=404, detail=f"Problem {problem_id} not found in task {task.id}"
        )

    def _update_problem(self, task, updated_problem) -> None:
        task.problems = [
            updated_problem if p.problem_id == updated_problem.problem_id else p
            for p in task.problems
        ]

    def _retag_single(self, task, problem, *, force: bool = False) -> None:
        if problem.locked_tags and not force:
            return
        solutions = {s.problem_id: s for s in task.solutions}
        solution = solutions.get(problem.problem_id)
        tag = self.pipeline.retag_problem(
            payload=task.payload,
            problem=problem,
            solution=solution,
        )
        task.tags = [t for t in task.tags if t.problem_id != problem.problem_id] + [tag]

    def rerun_ocr(self, task_id: str, problem_id: str):
        """Re-run OCR for a single problem and retag."""
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        region_id = problem.region_id or problem.problem_id
        extracted = self.pipeline.rerun_ocr_for_problem(
            payload=task.payload,
            asset=task.asset,
            region_id=region_id,
            crop_bbox=problem.crop_bbox,
        )
        extracted.problem_id = problem.problem_id
        extracted.region_id = problem.region_id
        extracted.locked_tags = problem.locked_tags
        self._update_problem(task, extracted)
        self._retag_single(task, extracted, force=False)
        updated = self.repository.patch_task(
            task_id, problems=task.problems, tags=task.tags, detection=task.detection
        )
        return updated

    def retag_problem(self, task_id: str, problem_id: str, *, force: bool):
        """Re-run tagging for a single problem."""
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        self._retag_single(task, problem, force=force)
        updated = self.repository.patch_task(task_id, tags=task.tags)
        return updated

    def override_problem(self, task_id: str, problem_id: str, override):
        """Override problem fields and optionally retag."""
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        updates = problem.model_copy(
            update={
                "question_no": override.question_no
                if override.question_no is not None
                else problem.question_no,
                "question_type": override.question_type
                if override.question_type is not None
                else problem.question_type,
                "problem_text": override.problem_text or problem.problem_text,
                "options": override.options
                if override.options is not None
                else problem.options,
                "locked_tags": override.locked_tags
                if override.locked_tags is not None
                else problem.locked_tags,
                "source": override.source
                if override.source is not None
                else problem.source,
                "knowledge_tags": override.knowledge_tags
                if override.knowledge_tags is not None
                else getattr(problem, "knowledge_tags", []),
                "error_tags": override.error_tags
                if override.error_tags is not None
                else getattr(problem, "error_tags", []),
                "user_tags": override.user_tags
                if override.user_tags is not None
                else getattr(problem, "user_tags", []),
                "crop_bbox": override.crop_bbox
                if override.crop_bbox is not None
                else problem.crop_bbox,
                "crop_image_url": override.crop_image_url
                if override.crop_image_url is not None
                else problem.crop_image_url,
            }
        )
        self._update_problem(task, updates)

        if any(
            field is not None
            for field in [
                override.knowledge_points,
                override.question_type,
                override.skills,
                override.error_hypothesis,
                override.recommended_actions,
            ]
        ):
            task.tags = [t for t in task.tags if t.problem_id != problem_id]
            task.tags.append(
                self.pipeline.classify_problem(payload=task.payload, problem=updates)
            )
        elif override.retag:
            self._retag_single(task, updates, force=True)

        updated = self.repository.patch_task(
            task_id, problems=task.problems, tags=task.tags
        )
        return updated

    def delete_task(self, task_id: str):
        """Delete a completed task."""
        try:
            task = self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
            raise HTTPException(
                status_code=409,
                detail="Task is in progress; cancel/finish before delete",
            )

        try:
            self.repository.delete(task_id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return task

    def delete_problem(self, task_id: str, problem_id: str):
        """Delete a single problem and its associated outputs."""
        task = self.repository.get(task_id)
        _ = self._get_problem(task, problem_id)

        task.problems = [p for p in task.problems if p.problem_id != problem_id]
        task.solutions = [s for s in task.solutions if s.problem_id != problem_id]
        task.tags = [t for t in task.tags if t.problem_id != problem_id]
        updated = self.repository.patch_task(
            task_id, problems=task.problems, solutions=task.solutions, tags=task.tags
        )
        return updated

    def retry_problem(self, task_id: str, problem_id: str):
        """Re-solve and retag a single problem."""
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        solution, tag = self.pipeline.solve_and_tag_single(
            payload=task.payload,
            problem=problem,
        )

        task.solutions = [
            s for s in task.solutions if s.problem_id != problem_id
        ] + [solution]
        task.tags = [t for t in task.tags if t.problem_id != problem_id] + [tag]
        updated = self.repository.patch_task(
            task_id, solutions=task.solutions, tags=task.tags
        )
        return updated

    # -------------------- library view --------------------

    def list_problems(
        self,
        *,
        subject: str | None = None,
        tag: str | None = None,
        source: str | None = None,
        knowledge_tag: str | None = None,
        error_tag: str | None = None,
        user_tag: str | None = None,
    ) -> ProblemsResponse:  # pylint: disable=too-many-locals
        """Return a flattened library view of problems."""
        tasks = self.repository.list_all().values()
        items: list[ProblemSummary] = []

        for task in tasks:
            task_subject = task.payload.subject
            if subject is not None and task_subject != subject:
                continue

            tag_index = {t.problem_id: t for t in task.tags}

            for problem in task.problems:
                tag_result = tag_index.get(problem.problem_id)

                manual_knowledge = list(getattr(problem, "knowledge_tags", []) or [])
                manual_error = list(getattr(problem, "error_tags", []) or [])
                manual_custom = list(getattr(problem, "user_tags", []) or [])
                ai_knowledge = (
                    list(getattr(tag_result, "knowledge_points", []))
                    if tag_result
                    else []
                )

                def _merge_unique(values: list[str]) -> list[str]:
                    out: list[str] = []
                    seen: set[str] = set()
                    for it in values:
                        s = str(it).strip()
                        if not s:
                            continue
                        key = s.casefold()
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append(s)
                    return out

                combined_knowledge = _merge_unique([*manual_knowledge, *ai_knowledge])

                # Apply filters
                if tag is not None and tag not in combined_knowledge:
                    continue
                if source is not None and problem.source != source:
                    continue
                if knowledge_tag is not None and knowledge_tag not in manual_knowledge:
                    continue
                if error_tag is not None and error_tag not in manual_error:
                    continue
                if user_tag is not None and user_tag not in manual_custom:
                    continue

                items.append(
                    ProblemSummary(
                        task_id=task.id,
                        problem_id=problem.problem_id,
                        question_no=getattr(problem, "question_no", None),
                        question_type=getattr(problem, "question_type", None)
                        or (tag_result.question_type if tag_result else None),
                        problem_text=problem.problem_text,
                        options=list(getattr(problem, "options", []) or []),
                        subject=task_subject,
                        grade=task.payload.grade,
                        source=problem.source,
                        knowledge_points=combined_knowledge,
                        knowledge_tags=manual_knowledge,
                        error_tags=manual_error,
                        user_tags=manual_custom,
                    )
                )

        return ProblemsResponse(items=items)

    # -------------------- pipeline execution --------------------

    def _mark_processing_started(self, task_id: str) -> None:
        self.repository.mark_processing(task_id)
        self.repository.patch_task(task_id, stage="starting", stage_message="开始处理")

    def _finalize_success(self, task_id: str, result):
        updated = self.repository.save_pipeline_result(task_id, result)
        self.repository.patch_task(task_id, stage="done", stage_message="完成")
        
        return updated

    def _finalize_cancelled(self, task_id: str):
        self.repository.mark_cancelled(task_id, "cancelled")
        updated = self.repository.patch_task(
            task_id, stage="cancelled", stage_message="已作废"
        )
        
        return updated

    def _finalize_failed(self, task_id: str, exc: Exception):
        self.repository.mark_failed(task_id, str(exc))
        updated = self.repository.patch_task(
            task_id, stage="failed", stage_message="处理失败"
        )
        
        return updated

    def cancel_task(self, task_id: str):
        """Cancel an in-progress task."""
        with self._task_cancel_lock:
            self._task_cancelled.add(task_id)
        
        # 立即更新任务状态，让前端可以立即停止轮询
        try:
            task = self.repository.get(task_id)
            if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
                self.repository.patch_task(
                    task_id,
                    status=TaskStatus.CANCELLED,
                    stage="cancelled",
                    stage_message="用户取消任务",
                )
                # 写入流事件，通知前端
                self._write_stream_event(task_id, "done", {"status": "cancelled"})
        except Exception:
            # 如果任务不存在或更新失败，至少保证取消标志已设置
            pass
        
        return self.get_task(task_id)

    def _is_task_cancelled(self, task_id: str) -> bool:
        with self._task_cancel_lock:
            return task_id in self._task_cancelled

    def _apply_manual_payload_to_result(self, task, result):
        """Apply user-provided tags and source from the task payload to the pipeline result."""
        manual_knowledge = [
            t for t in (task.payload.knowledge_tags or []) if str(t).strip()
        ]
        manual_error = [t for t in (task.payload.error_tags or []) if str(t).strip()]
        manual_source = (task.payload.source or "").strip()

        for tag in result.tags:
            tag.knowledge_points = self._merge_unique_tags(
                manual_knowledge, tag.knowledge_points
            )

        for problem in result.problems:
            if manual_source and not problem.source:
                problem.source = manual_source

        return result, manual_knowledge, manual_error, manual_source

    def _sync_tag_store_after_pipeline(
        self,
        *,
        manual_knowledge: list[str],
        manual_error: list[str],
        manual_source: str,
        tags: list[TaggingResult],
    ) -> None:
        """Update the global tag store with tags from the pipeline run."""
        for val in manual_knowledge:
            self.tag_store.upsert(TagDimension.KNOWLEDGE, val)
        for val in manual_error:
            self.tag_store.upsert(TagDimension.ERROR, val)
        if manual_source:
            self.tag_store.upsert(TagDimension.META, manual_source)

        for tag_res in tags:
            for val in tag_res.knowledge_points:
                self.tag_store.upsert(TagDimension.KNOWLEDGE, val)

    def process_task_sync(
        self,
        task_id: str,
        on_progress=None,
    ):
        """Run the full pipeline synchronously for a task."""
        with self._processing_lock:
            if task_id in self._processing_inflight:
                return self.get_task(task_id)
            self._processing_inflight.add(task_id)

        def progress_bridge(stage: str, message: str | None = None):
            # Write progress to stream file for polling
            self._write_stream_event(task_id, "progress", {"stage": stage, "message": message})
            
            # Also update task stage field for real-time status
            self.repository.patch_task(task_id, stage=stage, stage_message=message)
            
            if on_progress:
                try:
                    on_progress(stage, message)
                except Exception:
                    pass

        try:
            if self._is_task_cancelled(task_id):
                return self._finalize_cancelled(task_id)

            self._mark_processing_started(task_id)

            try:
                task = self.repository.get(task_id)
                result = self.pipeline.run(
                    task_id,
                    task.payload,
                    task.asset,
                    on_progress=progress_bridge,
                    is_cancelled=lambda: self._is_task_cancelled(task_id),
                )
                result, manual_knowledge, manual_error, manual_source = (
                    self._apply_manual_payload_to_result(task, result)
                )
                self._sync_tag_store_after_pipeline(
                    manual_knowledge=manual_knowledge,
                    manual_error=manual_error,
                    manual_source=manual_source,
                    tags=result.tags,
                )

                return self._finalize_success(task_id, result)
            except _TaskCancelled:
                return self._finalize_cancelled(task_id)
            except HTTPException:
                raise
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self._finalize_failed(task_id, exc)
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            # Write done event to stream file
            if task_id in self._task_cancelled:
                self._write_stream_event(task_id, "done", {"status": "cancelled"})
            elif task.status == TaskStatus.FAILED:
                self._write_stream_event(task_id, "done", {"status": "failed"})
            else:
                self._write_stream_event(task_id, "done", {"status": "completed"})
            
            with self._processing_lock:
                self._processing_inflight.discard(task_id)

    def _write_stream_event(self, task_id: str, event: str, payload: dict):
        """Write an event to the task stream file for polling."""
        data = {"event": event, "payload": payload, "ts": datetime.now(timezone.utc).isoformat()}
        
        path = self.streams_dir / f"{task_id}.txt"
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to write stream: %s", e)
