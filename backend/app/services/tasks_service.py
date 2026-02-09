from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from starlette.responses import StreamingResponse

from ..models import (
    DetectionOutput,
    ProblemSummary,
    ProblemsResponse,
    TaskResponse,
    TaskStatus,
    TaskSummary,
    TasksResponse,
)
from ..tags import TagDimension


class _TaskCancelled(Exception):
    pass


class TaskEventBroker:
    """In-memory pub/sub for per-task SSE events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[queue.Queue[tuple[str, dict[str, object]]]]] = {}

    def subscribe(self, task_id: str) -> queue.Queue[tuple[str, dict[str, object]]]:
        q: queue.Queue[tuple[str, dict[str, object]]] = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.setdefault(task_id, set()).add(q)
        return q

    def unsubscribe(self, task_id: str, q: queue.Queue[tuple[str, dict[str, object]]]) -> None:
        with self._lock:
            subs = self._subscribers.get(task_id)
            if not subs:
                return
            subs.discard(q)
            if not subs:
                self._subscribers.pop(task_id, None)

    def publish(self, task_id: str, event: str, payload: dict[str, object]) -> None:
        with self._lock:
            subs = list(self._subscribers.get(task_id, set()))

        for q in subs:
            try:
                q.put_nowait((event, payload))
            except Exception:
                pass


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _read_text_tail(path: Path, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return ""
    except Exception:
        return ""

    max_bytes = max_chars * 4
    start = max(0, size - max_bytes)
    try:
        with path.open("rb") as f:
            if start:
                f.seek(start)
            data = f.read()
        text = data.decode("utf-8", errors="ignore")
        return text[-max_chars:] if len(text) > max_chars else text
    except Exception:
        return ""


class TasksService:
    def __init__(self, *, repository, pipeline, asset_store, tag_store) -> None:
        self.repository = repository
        self.pipeline = pipeline
        self.asset_store = asset_store
        self.tag_store = tag_store

        self._event_broker = TaskEventBroker()

        self._task_stream_lock = threading.Lock()
        self._task_stream_cache: dict[str, str] = {}

        self._task_cancel_lock = threading.Lock()
        self._task_cancelled: set[str] = set()

        self._processing_lock = threading.Lock()
        self._processing_inflight: set[str] = set()

        self._task_queue_maxsize = _int_env("TASK_QUEUE_MAXSIZE", 1000)
        self._task_queue: queue.Queue[str] = (
            queue.Queue(maxsize=self._task_queue_maxsize) if self._task_queue_maxsize > 0 else queue.Queue()
        )

        self._workers_lock = threading.Lock()
        self._worker_threads: list[threading.Thread] = []

    # -------------------- stream persistence --------------------

    def _task_stream_dir(self) -> Path:
        configured = os.getenv("TASK_STREAM_DIR")
        if configured:
            return Path(configured)
        return Path(__file__).resolve().parents[2] / "storage" / "task_streams"

    def _task_stream_path(self, task_id: str) -> Path:
        out_dir = self._task_stream_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{task_id}.txt"

    def _append_task_stream(self, task_id: str, delta: str) -> None:
        if not delta:
            return
        max_chars = _int_env("TASK_STREAM_CACHE_MAX_CHARS", 200_000)
        with self._task_stream_lock:
            prev = self._task_stream_cache.get(task_id, "")
            next_text = prev + delta
            if max_chars > 0 and len(next_text) > max_chars:
                next_text = next_text[-max_chars:]
            self._task_stream_cache[task_id] = next_text

            try:
                self._task_stream_path(task_id).open("a", encoding="utf-8").write(delta)
            except Exception:
                pass

    def _get_task_stream(self, task_id: str) -> str:
        with self._task_stream_lock:
            cached = self._task_stream_cache.get(task_id)
            if cached is not None:
                return cached

            max_chars = _int_env("TASK_STREAM_CACHE_MAX_CHARS", 200_000)
            text = _read_text_tail(self._task_stream_path(task_id), max_chars)
            self._task_stream_cache[task_id] = text
            return text

    # -------------------- cancellation --------------------

    def _is_task_cancelled(self, task_id: str) -> bool:
        with self._task_cancel_lock:
            return task_id in self._task_cancelled

    def cancel_task(self, task_id: str):
        try:
            task = self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return task

        with self._task_cancel_lock:
            self._task_cancelled.add(task_id)

        self.repository.mark_failed(task_id, "cancelled")
        updated = self.repository.patch_task(task_id, stage="cancelled", stage_message="已作废")

        try:
            self._event_broker.publish(
                task_id,
                "progress",
                {
                    "task_id": task_id,
                    "status": str(updated.status),
                    "stage": "cancelled",
                    "message": "已作废",
                },
            )
        except Exception:
            pass

        return updated

    # -------------------- workers --------------------

    def _in_tests(self) -> bool:
        import sys

        return ("pytest" in sys.modules) or ("PYTEST_CURRENT_TEST" in os.environ)

    def _task_worker_loop(self) -> None:
        while True:
            try:
                task_id = self._task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if self._is_task_cancelled(task_id):
                    try:
                        self.repository.mark_failed(task_id, "cancelled")
                        self.repository.patch_task(task_id, stage="cancelled", stage_message="已作废")
                    except Exception:
                        pass
                    continue
                self.process_task_sync(task_id)
            except HTTPException:
                pass
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Unexpected worker error task_id=%s", task_id)
            finally:
                with self._processing_lock:
                    self._processing_inflight.discard(task_id)
                try:
                    self._task_queue.task_done()
                except Exception:
                    pass

    def ensure_workers_started(self) -> None:
        if self._in_tests():
            return
        with self._workers_lock:
            if self._worker_threads:
                return

            worker_count = max(1, _int_env("TASK_WORKERS", 2))
            for i in range(worker_count):
                thread = threading.Thread(
                    target=self._task_worker_loop,
                    name=f"task-worker-{i + 1}",
                    daemon=True,
                )
                self._worker_threads.append(thread)
                thread.start()

    def start_processing_in_background(self, task_id: str) -> None:
        self.ensure_workers_started()

        try:
            self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        with self._processing_lock:
            if task_id in self._processing_inflight:
                return
            self._processing_inflight.add(task_id)

        try:
            self._task_queue.put_nowait(task_id)
        except queue.Full as exc:
            with self._processing_lock:
                self._processing_inflight.discard(task_id)
            raise HTTPException(status_code=429, detail="Task queue is full") from exc

        try:
            self.repository.patch_task(task_id, stage="queued", stage_message="已加入队列，等待处理")
            task = self.repository.get(task_id)
            self._event_broker.publish(
                task_id,
                "progress",
                {
                    "task_id": task_id,
                    "status": str(task.status),
                    "stage": "queued",
                    "message": "已加入队列，等待处理",
                },
            )
        except Exception:
            pass

    # -------------------- basic CRUD --------------------

    def create_task(self, payload, *, auto_process: bool = True):
        task = self.repository.create(payload)
        if auto_process:
            task = self.process_task_sync(task.id)
        return task

    def upload_task(self, upload, *, auto_process: bool = True):
        if upload.image_base64:
            asset = self.asset_store.save_base64(
                upload.image_base64,
                mime_type=upload.mime_type,
                filename=upload.filename,
            )
            derived_url = f"https://assets.local/{asset.asset_id}"
        else:
            assert upload.image_url is not None
            asset = self.asset_store.register_remote(str(upload.image_url), upload.mime_type)
            derived_url = str(upload.image_url)

        from ..models import TaskCreateRequest

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

    def list_tasks(self, *, status: TaskStatus | None = None, active_only: bool = False, subject: str | None = None) -> TasksResponse:
        tasks = list(self.repository.list_all().values())

        stale_seconds = _int_env("TASK_STALE_SECONDS", 600)
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
            except Exception:
                continue

        tasks = list(self.repository.list_all().values())

        if subject is not None:
            tasks = [t for t in tasks if t.payload.subject == subject]

        if active_only:
            tasks = [t for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.PROCESSING)]
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
            )
            for t in tasks
        ]
        return TasksResponse(items=items)

    def get_task(self, task_id: str):
        try:
            return self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def process_task(self, task_id: str, *, background: bool = False):
        if background:
            self.start_processing_in_background(task_id)
            return self.repository.get(task_id)
        return self.process_task_sync(task_id)

    def retry_task(self, task_id: str, *, background: bool = True, clear_stream: bool = True):
        """Retry a task (failed or completed).

        This is a convenience wrapper around processing that also clears cancellation
        flags and (optionally) clears previous LLM stream output.
        """

        try:
            task = self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if task.status == TaskStatus.PROCESSING:
            return task

        with self._task_cancel_lock:
            self._task_cancelled.discard(task_id)

        if clear_stream:
            with self._task_stream_lock:
                self._task_stream_cache.pop(task_id, None)
            try:
                self._task_stream_path(task_id).unlink(missing_ok=True)
            except Exception:
                pass

        try:
            self.repository.patch_task(task_id, stage="retrying", stage_message="准备重试")
        except Exception:
            pass

        return self.process_task(task_id, background=background)

    def get_task_stream(self, task_id: str, *, max_chars: int = 200_000) -> dict[str, object]:
        _ = self.get_task(task_id)
        text = self._get_task_stream(task_id)
        if max_chars > 0 and len(text) > max_chars:
            text = text[-max_chars:]
        return {"task_id": task_id, "text": text}

    def task_events(self, task_id: str) -> StreamingResponse:
        async def gen():
            subscriber_q = self._event_broker.subscribe(task_id)
            try:
                try:
                    task = self.repository.get(task_id)
                except KeyError:
                    data = json.dumps({"error": "not_found"}, ensure_ascii=False)
                    yield f"event: error\ndata: {data}\n\n"
                    return

                snapshot = {
                    "task_id": task.id,
                    "status": task.status,
                    "stage": getattr(task, "stage", None),
                    "message": getattr(task, "stage_message", None),
                }
                yield f"event: progress\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"

                stream_snapshot = {"task_id": task.id, "text": self._get_task_stream(task.id)}
                yield f"event: llm_snapshot\ndata: {json.dumps(stream_snapshot, ensure_ascii=False)}\n\n"

                last_snapshot = snapshot
                last_keepalive = time.monotonic()
                last_snapshot_at = time.monotonic()

                while True:
                    try:
                        event, payload = await asyncio.to_thread(subscriber_q.get, True, 0.5)
                        yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    except Exception:
                        pass

                    now = time.monotonic()
                    if now - last_keepalive > 10:
                        yield ": ping\n\n"
                        last_keepalive = now

                    if now - last_snapshot_at > 1.0:
                        try:
                            task = self.repository.get(task_id)
                        except KeyError:
                            data = json.dumps({"error": "not_found"}, ensure_ascii=False)
                            yield f"event: error\ndata: {data}\n\n"
                            return

                        try:
                            stale_seconds = _int_env("TASK_STALE_SECONDS", 600)
                            if task.status == TaskStatus.PROCESSING:
                                age = (datetime.now(timezone.utc) - task.updated_at).total_seconds()
                                with self._processing_lock:
                                    inflight = task.id in self._processing_inflight
                                if (not inflight) and age > stale_seconds:
                                    task = self.repository.patch_task(
                                        task_id,
                                        status=TaskStatus.FAILED,
                                        last_error="Task processing stale (backend restarted or worker crashed)",
                                        stage="failed",
                                        stage_message="处理超时（可能后端重启/崩溃），请重新提交或手动重试处理",
                                    )
                        except Exception:
                            pass

                        snapshot = {
                            "task_id": task.id,
                            "status": task.status,
                            "stage": getattr(task, "stage", None),
                            "message": getattr(task, "stage_message", None),
                        }
                        if snapshot != last_snapshot:
                            yield f"event: progress\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                            last_snapshot = snapshot
                        last_snapshot_at = now

                        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                            yield "event: done\ndata: {}\n\n"
                            return
            finally:
                self._event_broker.unsubscribe(task_id, subscriber_q)

        return StreamingResponse(gen(), media_type="text/event-stream")

    # -------------------- per-problem operations --------------------

    def _get_problem(self, task, problem_id: str):
        for problem in task.problems:
            if problem.problem_id == problem_id:
                return problem
        raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found in task {task.id}")

    def _update_problem(self, task, updated_problem) -> None:
        task.problems = [updated_problem if p.problem_id == updated_problem.problem_id else p for p in task.problems]

    def _retag_single(self, task, problem, *, force: bool = False) -> None:
        if problem.locked_tags and not force:
            return
        solutions = {s.problem_id: s for s in task.solutions}
        solution = solutions.get(problem.problem_id)
        tagger = self.pipeline.deps.tagger
        tags = tagger.run(task.payload, [problem], [solution] if solution else [])
        task.tags = [t for t in task.tags if t.problem_id != problem.problem_id] + tags

    def rerun_ocr(self, task_id: str, problem_id: str):
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        extractor = self.pipeline.deps.ocr_extractor
        if extractor is None:
            raise HTTPException(status_code=400, detail="OCR extractor not configured")

        from ..models import CropRegion

        if task.detection:
            regions = [r for r in task.detection.regions if r.id == problem.region_id]
        else:
            regions = []
        if not regions:
            bbox = problem.crop_bbox or [0.05, 0.05, 0.9, 0.25]
            regions = [CropRegion(id=problem.region_id or problem.problem_id, bbox=bbox, label="full")]
        detection = DetectionOutput(action="single", regions=regions)
        extracted = extractor.run(task.payload, detection, task.asset)[0]
        extracted.problem_id = problem.problem_id
        extracted.region_id = problem.region_id
        extracted.locked_tags = problem.locked_tags
        self._update_problem(task, extracted)
        self._retag_single(task, extracted, force=False)
        updated = self.repository.patch_task(task_id, problems=task.problems, tags=task.tags, detection=task.detection)
        return updated

    def retag_problem(self, task_id: str, problem_id: str, *, force: bool):
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        self._retag_single(task, problem, force=force)
        updated = self.repository.patch_task(task_id, tags=task.tags)
        return updated

    def override_problem(self, task_id: str, problem_id: str, override):
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        updates = problem.model_copy(
            update={
                "question_no": override.question_no if override.question_no is not None else problem.question_no,
                "question_type": override.question_type if override.question_type is not None else problem.question_type,
                "problem_text": override.problem_text or problem.problem_text,
                "latex_blocks": override.latex_blocks if override.latex_blocks is not None else problem.latex_blocks,
                "options": override.options if override.options is not None else problem.options,
                "locked_tags": override.locked_tags if override.locked_tags is not None else problem.locked_tags,
                "source": override.source if override.source is not None else problem.source,
                "knowledge_tags": override.knowledge_tags
                if override.knowledge_tags is not None
                else getattr(problem, "knowledge_tags", []),
                "error_tags": override.error_tags if override.error_tags is not None else getattr(problem, "error_tags", []),
                "user_tags": override.user_tags if override.user_tags is not None else getattr(problem, "user_tags", []),
                "crop_bbox": override.crop_bbox if override.crop_bbox is not None else problem.crop_bbox,
                "crop_image_url": override.crop_image_url if override.crop_image_url is not None else problem.crop_image_url,
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
                self.pipeline.deps.tagger.ai_client.classify_problem(task.payload.subject, updates)
                if hasattr(self.pipeline.deps.tagger, "ai_client")
                else self.pipeline.deps.tagger.run(task.payload, [updates], [])[-1]
            )
        elif override.retag:
            self._retag_single(task, updates, force=True)

        updated = self.repository.patch_task(task_id, problems=task.problems, tags=task.tags)
        return updated

    def delete_task(self, task_id: str):
        try:
            task = self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if task.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
            raise HTTPException(status_code=409, detail="Task is in progress; cancel/finish before delete")

        try:
            self.repository.delete(task_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        try:
            self._task_stream_path(task_id).unlink(missing_ok=True)
        except Exception:
            pass

        return task

    def delete_problem(self, task_id: str, problem_id: str):
        task = self.repository.get(task_id)
        _ = self._get_problem(task, problem_id)

        task.problems = [p for p in task.problems if p.problem_id != problem_id]
        task.solutions = [s for s in task.solutions if s.problem_id != problem_id]
        task.tags = [t for t in task.tags if t.problem_id != problem_id]
        updated = self.repository.patch_task(task_id, problems=task.problems, solutions=task.solutions, tags=task.tags)
        return updated

    def retry_problem(self, task_id: str, problem_id: str):
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        if self.pipeline.orchestrator:
            solutions, tags = self.pipeline.orchestrator.solve_and_tag(task.payload, [problem])
        else:
            solutions = self.pipeline.deps.solution_writer.run(task.payload, [problem])
            tags = self.pipeline.deps.tagger.run(task.payload, [problem], solutions)

        task.solutions = [s for s in task.solutions if s.problem_id != problem_id] + solutions
        task.tags = [t for t in task.tags if t.problem_id != problem_id] + tags
        updated = self.repository.patch_task(task_id, solutions=task.solutions, tags=task.tags)
        return updated

    # -------------------- library view --------------------

    def list_problems(self, *, subject: str | None = None, tag: str | None = None) -> ProblemsResponse:
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
                ai_knowledge = list(getattr(tag_result, "knowledge_points", [])) if tag_result else []

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

                if tag is not None:
                    if tag not in combined_knowledge:
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

    def process_task_sync(self, task_id: str):
        if self._is_task_cancelled(task_id):
            self.repository.mark_failed(task_id, "cancelled")
            self.repository.patch_task(task_id, stage="cancelled", stage_message="已作废")
            return self.repository.get(task_id)

        self.repository.mark_processing(task_id)
        self.repository.patch_task(task_id, stage="starting", stage_message="开始处理")
        self._event_broker.publish(
            task_id,
            "progress",
            {
                "task_id": task_id,
                "status": "processing",
                "stage": "starting",
                "message": "开始处理",
            },
        )

        def _progress(stage: str, message: str | None) -> None:
            if self._is_task_cancelled(task_id):
                raise _TaskCancelled()
            self.repository.patch_task(task_id, stage=stage, stage_message=message)
            self._event_broker.publish(
                task_id,
                "progress",
                {
                    "task_id": task_id,
                    "status": self.repository.get(task_id).status,
                    "stage": stage,
                    "message": message,
                },
            )

        def _llm_delta(problem_id: str, kind: str, delta: str) -> None:
            if not delta:
                return
            if self._is_task_cancelled(task_id):
                raise _TaskCancelled()

            self._append_task_stream(task_id, delta)
            self._event_broker.publish(
                task_id,
                "llm_delta",
                {
                    "task_id": task_id,
                    "problem_id": problem_id,
                    "kind": kind,
                    "delta": delta,
                },
            )

        try:
            task = self.repository.get(task_id)
            result = self.pipeline.run(
                task_id,
                task.payload,
                task.asset,
                on_progress=_progress,
                on_llm_delta=_llm_delta,
            )

            manual_knowledge = [str(t).strip() for t in (task.payload.knowledge_tags or []) if str(t).strip()]
            manual_error = [str(t).strip() for t in (task.payload.error_tags or []) if str(t).strip()]
            manual_source = (task.payload.source or "").strip()

            def _merge_unique(prefix: list[str], tail: list[str]) -> list[str]:
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

            if manual_source:
                result = result.model_copy(
                    update={
                        "problems": [p.model_copy(update={"source": p.source or manual_source}) for p in result.problems]
                    }
                )

            if manual_knowledge or manual_error:
                patched_tags = []
                for t in result.tags:
                    patched_tags.append(
                        t.model_copy(
                            update={
                                "knowledge_points": _merge_unique(manual_knowledge, t.knowledge_points),
                                "error_hypothesis": _merge_unique(manual_error, t.error_hypothesis),
                            }
                        )
                    )
                result = result.model_copy(update={"tags": patched_tags})

            try:
                self.tag_store.ensure(TagDimension.KNOWLEDGE, manual_knowledge)
                self.tag_store.ensure(TagDimension.ERROR, manual_error)
                if manual_source:
                    self.tag_store.ensure(TagDimension.META, [manual_source])

                discovered_knowledge: list[str] = []
                discovered_error: list[str] = []
                for t in result.tags:
                    discovered_knowledge.extend(t.knowledge_points or [])
                    for e in (t.error_hypothesis or []):
                        s = str(e).strip()
                        if not s or len(s) > 40 or "\n" in s:
                            continue
                        discovered_error.append(s)
                self.tag_store.ensure(TagDimension.KNOWLEDGE, discovered_knowledge)
                self.tag_store.ensure(TagDimension.ERROR, discovered_error)
            except Exception:
                pass

            updated = self.repository.save_pipeline_result(task_id, result)
            self.repository.patch_task(task_id, stage="done", stage_message="完成")
            self._event_broker.publish(
                task_id,
                "progress",
                {
                    "task_id": task_id,
                    "status": "completed",
                    "stage": "done",
                    "message": "完成",
                },
            )

            return updated
        except _TaskCancelled:
            self.repository.mark_failed(task_id, "cancelled")
            updated = self.repository.patch_task(task_id, stage="cancelled", stage_message="已作废")
            return updated
        except HTTPException:
            raise
        except Exception as exc:
            # Persist failure state.
            self.repository.mark_failed(task_id, str(exc))
            updated = self.repository.patch_task(task_id, stage="failed", stage_message="处理失败")
            try:
                self._append_task_stream(task_id, f'{{"stage":"failed","message":"{str(exc)}"}}')
                self._event_broker.publish(
                    task_id,
                    "progress",
                    {
                        "task_id": task_id,
                        "status": "failed",
                        "stage": "failed",
                        "message": str(exc),
                    },
                )
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=str(exc)) from exc
