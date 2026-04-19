from __future__ import annotations

import base64
import io
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image
from pydantic import HttpUrl, ValidationError

from ..agents import utils as agent_utils

from ..models import (
    ProblemSummary,
    ProblemsResponse,
    TaggingResult,
    TaskCreateRequest,
    TaskStatus,
    TaskSummary,
    TasksResponse,
)
from .tag_sync_service import TagSyncService

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
    def __init__(
        self,
        *,
        repository,
        pipeline,
        asset_store,
        tag_store,
        tag_sync_service: TagSyncService | None = None,
    ) -> None:
        self.repository = repository
        self.pipeline = pipeline
        self.asset_store = asset_store
        self.tag_store = tag_store
        self.tag_sync_service = tag_sync_service or TagSyncService(
            tag_store=self.tag_store
        )

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
        self.demo_batches_dir = self.streams_dir.parent / "demo_batches"
        self.demo_batches_dir.mkdir(parents=True, exist_ok=True)
        self._demo_batch_lock = threading.Lock()

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

    def emit_stream_event(self, task_id: str, event: str, payload: dict[str, Any]) -> None:
        """Emit a task stream event through the public service API."""
        self._write_stream_event(task_id, event, payload)

    def apply_runtime_settings(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        debug_payload: bool | None = None,
    ) -> dict[str, int]:
        """Apply runtime settings to active pipeline clients.

        The method is intentionally best-effort to avoid blocking settings APIs
        when a single client instance fails to reconfigure.
        """

        collector = getattr(self.pipeline, "list_runtime_clients", None)
        if not callable(collector):
            logger.warning("Pipeline does not expose runtime client collector")
            return {"clients_total": 0, "clients_updated": 0}

        clients = list(collector() or [])
        updated = 0

        for client in clients:
            reconfigure = getattr(client, "reconfigure", None)
            kwargs: dict[str, Any] = {}
            if base_url is not None:
                kwargs["base_url"] = base_url
            if api_key is not None:
                kwargs["api_key"] = api_key
            if model is not None:
                kwargs["model"] = model
            if temperature is not None:
                kwargs["temperature"] = temperature
            if debug_payload is not None:
                kwargs["debug_payload"] = debug_payload

            if callable(reconfigure):
                if not kwargs:
                    continue
                try:
                    reconfigure(**kwargs)
                    updated += 1
                    continue
                except TypeError:
                    # Backward compatibility: some clients may not accept
                    # debug_payload in reconfigure.
                    fallback_kwargs = dict(kwargs)
                    fallback_kwargs.pop("debug_payload", None)
                    try:
                        if fallback_kwargs:
                            reconfigure(**fallback_kwargs)
                        if debug_payload is not None and hasattr(client, "debug_payload"):
                            setattr(client, "debug_payload", debug_payload)
                        updated += 1
                    except Exception as exc:  # pylint: disable=broad-exception-caught
                        logger.warning("Failed to reconfigure client: %s", exc)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.warning("Failed to reconfigure client: %s", exc)
                continue

            changed = False
            if debug_payload is not None and hasattr(client, "debug_payload"):
                setattr(client, "debug_payload", debug_payload)
                changed = True
            if model is not None and hasattr(client, "model"):
                setattr(client, "model", model)
                changed = True
            if temperature is not None and hasattr(client, "temperature"):
                setattr(client, "temperature", temperature)
                changed = True
            if changed:
                updated += 1

        return {"clients_total": len(clients), "clients_updated": updated}

    # -------------------- workers --------------------

    def start_processing_in_background(
        self, task_id: str, existing_problems=None
    ) -> None:
        """Process a task in a background thread without a complex queue."""
        try:
            self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        # Fire and forget thread for simplified background processing
        thread = threading.Thread(
            target=self.process_task_sync,
            args=(task_id, existing_problems),
            kwargs={},
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

        try:
            http_url = HttpUrl(derived_url)
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid image URL")

        payload = TaskCreateRequest(
            image_url=http_url,
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

    def run_debug_multipage_batch(self, upload, *, auto_process: bool = True) -> str:
        """独立 demo：多图分割后自动创建任务，返回 batch_id。"""
        batch_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        batch: dict[str, Any] = {
            "batch_id": batch_id,
            "status": "processing",
            "created_at": now,
            "updated_at": now,
            "total_images": len(upload.images),
            "total_regions": 0,
            "task_ids": [],
            "task_items": [],
            "warnings": [],
        }
        self._save_demo_batch(batch)

        for index, image_input in enumerate(upload.images, start=1):
            page_index = int(image_input.page_index or index)
            try:
                asset = self.asset_store.save_base64(
                    image_input.image_base64,
                    mime_type=image_input.mime_type,
                    filename=image_input.filename,
                )
                image_bytes = self._read_asset_bytes(asset)
                mime_type = asset.mime_type or image_input.mime_type or "image/png"

                regions = self._segment_page_regions(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    subject=upload.subject,
                    notes=upload.notes or "",
                    page_index=page_index,
                )
                if not regions:
                    regions = [{"bbox": [0.0, 0.0, 1.0, 1.0], "label": "full"}]
                    batch["warnings"].append(
                        f"第{page_index}页未识别到题块，已回退整页建任务"
                    )

                for region_index, region in enumerate(regions, start=1):
                    crop_asset = self._create_crop_asset(
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                        bbox=region.get("bbox") or [0.0, 0.0, 1.0, 1.0],
                        page_index=page_index,
                        region_index=region_index,
                    )
                    task = self._create_demo_task_from_crop(
                        upload=upload,
                        crop_asset=crop_asset,
                        page_index=page_index,
                        region_index=region_index,
                    )
                    if auto_process:
                        self.process_task(task.id, background=True)

                    batch["task_ids"].append(task.id)
                    batch["task_items"].append(
                        {
                            "task_id": task.id,
                            "page_index": page_index,
                            "region_index": region_index,
                        }
                    )
                    batch["total_regions"] = int(batch["total_regions"]) + 1
            except Exception as exc:  # pylint: disable=broad-exception-caught
                batch["warnings"].append(f"第{page_index}页处理失败: {exc}")

            batch["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._save_demo_batch(batch)

        batch["status"] = "completed"
        batch["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._save_demo_batch(batch)
        return batch_id

    def get_debug_multipage_batch(self, batch_id: str) -> dict[str, Any]:
        """返回 demo 批次详情和任务状态聚合。"""
        batch = self._load_demo_batch(batch_id)
        items: list[dict[str, Any]] = []
        completed = 0
        failed = 0
        cancelled = 0

        for item in batch.get("task_items", []):
            task_id = str(item.get("task_id") or "")
            if not task_id:
                continue
            try:
                task = self.repository.get(task_id)
                status = str(task.status.value if hasattr(task.status, "value") else task.status)
                if status == "completed":
                    completed += 1
                elif status == "failed":
                    failed += 1
                elif status == "cancelled":
                    cancelled += 1
                items.append(
                    {
                        "task_id": task_id,
                        "page_index": int(item.get("page_index") or 0),
                        "region_index": int(item.get("region_index") or 0),
                        "status": status,
                        "stage": getattr(task, "stage", None),
                        "stage_message": getattr(task, "stage_message", None),
                    }
                )
            except Exception:  # pylint: disable=broad-exception-caught
                failed += 1
                items.append(
                    {
                        "task_id": task_id,
                        "page_index": int(item.get("page_index") or 0),
                        "region_index": int(item.get("region_index") or 0),
                        "status": "missing",
                        "stage": None,
                        "stage_message": "任务不存在或读取失败",
                    }
                )

        total_tasks = len(items)
        status = "processing"
        if total_tasks == 0:
            status = "empty"
        elif completed + failed + cancelled >= total_tasks:
            status = "completed"

        return {
            "batch_id": batch_id,
            "status": status,
            "created_at": batch.get("created_at"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_images": int(batch.get("total_images") or 0),
            "total_regions": int(batch.get("total_regions") or 0),
            "total_tasks": total_tasks,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "cancelled_tasks": cancelled,
            "tasks": items,
            "warnings": [str(x) for x in (batch.get("warnings") or [])],
        }

    def _segment_page_regions(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        subject: str,
        notes: str,
        page_index: int,
    ) -> list[dict[str, Any]]:
        template = agent_utils._load_prompt("segmenter")
        system_prompt, user_prompt = template.render(
            {
                "subject": subject,
                "notes": notes,
                "page_index": page_index,
            }
        )

        client = self._resolve_segmenter_client()
        thinking = self._resolve_segmenter_thinking()
        override_model = self._resolve_segmenter_model()
        original_model = getattr(client, "model", None)

        try:
            if override_model:
                client.model = str(override_model)
            output = client.structured_chat_with_image(
                system_prompt,
                user_prompt,
                image_bytes,
                mime_type,
                thinking=thinking,
            )
        finally:
            if override_model and original_model is not None:
                client.model = original_model

        raw_regions = output.get("regions") if isinstance(output, dict) else None
        if not isinstance(raw_regions, list):
            return []

        regions: list[dict[str, Any]] = []
        for item in raw_regions:
            if not isinstance(item, dict):
                continue
            bbox = item.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            try:
                x, y, w, h = [float(v) for v in bbox]
            except (ValueError, TypeError):
                continue

            x = min(max(x, 0.0), 1.0)
            y = min(max(y, 0.0), 1.0)
            w = min(max(w, 0.01), 1.0 - x)
            h = min(max(h, 0.01), 1.0 - y)
            regions.append(
                {
                    "bbox": [x, y, w, h],
                    "label": str(item.get("label") or "problem"),
                }
            )
        return regions

    def _resolve_segmenter_client(self):
        resolver = getattr(self.pipeline, "get_segmenter_runtime_access", None)
        if not callable(resolver):
            raise RuntimeError("Pipeline does not expose segmenter runtime access")
        runtime = resolver()
        if runtime is None or runtime.client is None:
            raise RuntimeError("Segmenter client is unavailable")
        return runtime.client

    def _resolve_segmenter_model(self) -> str | None:
        runtime_resolver = getattr(self.pipeline, "get_segmenter_runtime_access", None)
        if not callable(runtime_resolver):
            return None
        runtime = runtime_resolver()
        resolver = runtime.model_resolver if runtime is not None else None
        if resolver is None:
            return None
        try:
            return resolver("SEGMENTER")
        except Exception:
            return None

    def _resolve_segmenter_thinking(self) -> bool | None:
        runtime_resolver = getattr(self.pipeline, "get_segmenter_runtime_access", None)
        if not callable(runtime_resolver):
            return None
        runtime = runtime_resolver()
        resolver = runtime.thinking_resolver if runtime is not None else None
        if resolver is None:
            return None
        try:
            return bool(resolver("SEGMENTER"))
        except Exception:
            return None

    def _create_crop_asset(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        bbox: list[float],
        page_index: int,
        region_index: int,
    ):
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            x = int(max(0.0, min(1.0, float(bbox[0]))) * width)
            y = int(max(0.0, min(1.0, float(bbox[1]))) * height)
            w = int(max(1.0 / width, min(1.0, float(bbox[2]))) * width)
            h = int(max(1.0 / height, min(1.0, float(bbox[3]))) * height)
            x2 = min(width, x + w)
            y2 = min(height, y + h)
            crop = img.crop((x, y, x2, y2))

            fmt = "PNG"
            ext = "png"
            if mime_type in {"image/jpeg", "image/jpg"}:
                fmt = "JPEG"
                ext = "jpg"

            buffer = io.BytesIO()
            crop.save(buffer, format=fmt)
            encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
            return self.asset_store.save_base64(
                encoded,
                mime_type=mime_type,
                filename=f"demo-p{page_index}-r{region_index}.{ext}",
            )

    def _create_demo_task_from_crop(
        self,
        *,
        upload,
        crop_asset,
        page_index: int,
        region_index: int,
    ):
        derived_url = f"https://assets.local/{crop_asset.asset_id}"
        try:
            http_url = HttpUrl(derived_url)
        except (ValidationError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid cropped image URL")

        notes_suffix = f"[demo page={page_index} region={region_index}]"
        composed_notes = (
            f"{upload.notes}\n{notes_suffix}" if upload.notes else notes_suffix
        )

        payload = TaskCreateRequest(
            image_url=http_url,
            subject=upload.subject,
            grade=upload.grade,
            notes=composed_notes,
            question_no=None,
            question_type=upload.question_type,
            mock_problem_count=None,
            difficulty=upload.difficulty,
            source=upload.source,
            options=[],
            knowledge_tags=upload.knowledge_tags,
            error_tags=upload.error_tags,
            user_tags=upload.user_tags,
        )
        return self.repository.create(payload, asset=crop_asset)

    def _demo_batch_path(self, batch_id: str) -> Path:
        return self.demo_batches_dir / f"{batch_id}.json"

    def _save_demo_batch(self, batch: dict[str, Any]) -> None:
        batch_id = str(batch.get("batch_id") or "")
        if not batch_id:
            raise ValueError("demo batch missing batch_id")
        path = self._demo_batch_path(batch_id)
        tmp = path.with_suffix(".json.tmp")
        with self._demo_batch_lock:
            tmp.write_text(
                json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(path)

    def _load_demo_batch(self, batch_id: str) -> dict[str, Any]:
        path = self._demo_batch_path(batch_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Demo batch {batch_id} not found")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise HTTPException(
                status_code=500, detail=f"Failed to read demo batch: {exc}"
            ) from exc

    def _read_asset_bytes(self, asset) -> bytes:
        raw_path = getattr(asset, "path", None)
        if not raw_path:
            raise RuntimeError("Asset path is missing")
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / "storage" / "assets" / path.name
        if not path.exists():
            raise RuntimeError(f"Asset file not found: {path}")
        return path.read_bytes()

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
                asset=(
                    {
                        "asset_id": t.asset.asset_id,
                        "path": (
                            f"/assets/{Path(t.asset.path).name}"
                            if t.asset and t.asset.path
                            else None
                        ),
                        "mime_type": t.asset.mime_type,
                    }
                    if t.asset
                    else None
                ),
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

    def process_task(
        self, task_id: str, *, background: bool = False, existing_problems=None
    ):
        """Process a task in foreground or background."""
        if background:
            self.start_processing_in_background(
                task_id, existing_problems=existing_problems
            )
            return self.repository.get(task_id)
        return self.process_task_sync(task_id, existing_problems=existing_problems)

    def retry_task(self, task_id: str, *, background: bool = True):
        """Retry a task (failed or completed).

        This re-runs the full pipeline (OCR, solve, tag) but preserves the original
        problem_id and region_id to overwrite existing problems instead of creating new ones.
        """

        try:
            task = self.repository.get(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if task.status == TaskStatus.PROCESSING:
            return task

        with self._task_cancel_lock:
            self._task_cancelled.discard(task_id)

        # Store existing problems to preserve their IDs during retry
        existing_problems = task.problems.copy() if task.problems else None

        try:
            self.repository.patch_task(
                task_id, stage="retrying", stage_message="准备重试"
            )
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        return self.process_task(
            task_id, background=background, existing_problems=existing_problems
        )

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

        task.tags = self.tag_sync_service.replace_problem_tags(
            task_tags=list(task.tags or []),
            problem_id=problem.problem_id,
            new_tags=[tag],
        )

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

    def rerender_diagram(self, task_id: str, problem_id: str):
        """Re-run diagram reconstruction for a single problem."""
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)

        self._write_stream_event(
            task_id,
            "progress",
            {
                "stage": "diagramming",
                "message": f"图形重建中（题号 {problem.question_no or problem.problem_id}）",
            },
        )

        try:
            updated_problem = self.pipeline.rerender_diagram_for_problem(
                payload=task.payload,
                problem=problem,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self._write_stream_event(
                task_id,
                "progress",
                {
                    "stage": "diagramming",
                    "message": "图形重建失败，建议人工介入",
                },
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        updated_problem.problem_id = problem.problem_id
        updated_problem.region_id = problem.region_id
        updated_problem.locked_tags = problem.locked_tags
        self._update_problem(task, updated_problem)

        updated = self.repository.patch_task(task_id, problems=task.problems)

        msg = "图形重建完成"
        if updated_problem.diagram_render_status == "failed":
            msg = "图形重建失败，建议人工介入"
        self._write_stream_event(
            task_id,
            "progress",
            {"stage": "diagramming", "message": msg},
        )
        return updated

    def override_problem(self, task_id: str, problem_id: str, override):
        """Override problem fields and optionally retag."""
        task = self.repository.get(task_id)
        problem = self._get_problem(task, problem_id)
        updates = problem.model_copy(
            update={
                "question_no": (
                    override.question_no
                    if override.question_no is not None
                    else problem.question_no
                ),
                "question_type": (
                    override.question_type
                    if override.question_type is not None
                    else problem.question_type
                ),
                "problem_text": override.problem_text or problem.problem_text,
                "options": (
                    override.options
                    if override.options is not None
                    else problem.options
                ),
                "locked_tags": (
                    override.locked_tags
                    if override.locked_tags is not None
                    else problem.locked_tags
                ),
                "source": (
                    override.source if override.source is not None else problem.source
                ),
                "knowledge_tags": (
                    override.knowledge_tags
                    if override.knowledge_tags is not None
                    else getattr(problem, "knowledge_tags", [])
                ),
                "error_tags": (
                    override.error_tags
                    if override.error_tags is not None
                    else getattr(problem, "error_tags", [])
                ),
                "user_tags": (
                    override.user_tags
                    if override.user_tags is not None
                    else getattr(problem, "user_tags", [])
                ),
                "crop_bbox": (
                    override.crop_bbox
                    if override.crop_bbox is not None
                    else problem.crop_bbox
                ),
                "crop_image_url": (
                    override.crop_image_url
                    if override.crop_image_url is not None
                    else problem.crop_image_url
                ),
                "diagram_detected": (
                    override.diagram_detected
                    if override.diagram_detected is not None
                    else problem.diagram_detected
                ),
                "diagram_kind": (
                    override.diagram_kind
                    if override.diagram_kind is not None
                    else problem.diagram_kind
                ),
                "diagram_tikz_source": (
                    override.diagram_tikz_source
                    if override.diagram_tikz_source is not None
                    else problem.diagram_tikz_source
                ),
                "diagram_svg": (
                    override.diagram_svg
                    if override.diagram_svg is not None
                    else problem.diagram_svg
                ),
                "diagram_render_status": (
                    override.diagram_render_status
                    if override.diagram_render_status is not None
                    else problem.diagram_render_status
                ),
                "diagram_error": (
                    override.diagram_error
                    if override.diagram_error is not None
                    else problem.diagram_error
                ),
                "diagram_needs_review": (
                    override.diagram_needs_review
                    if override.diagram_needs_review is not None
                    else problem.diagram_needs_review
                ),
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
            new_tag = self.pipeline.classify_problem(
                payload=task.payload, problem=updates
            )
            task.tags = self.tag_sync_service.replace_problem_tags(
                task_tags=list(task.tags or []),
                problem_id=problem_id,
                new_tags=[new_tag],
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

        # Decrease tag reference counts before deletion
        self._sync_tag_counts_after_task_deletion(task)

        try:
            self.repository.delete(task_id)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return task

    def delete_problem(self, task_id: str, problem_id: str):
        """Delete a single problem and its associated outputs."""
        task = self.repository.get(task_id)
        _ = self._get_problem(task, problem_id)

        # Decrease tag reference counts before deletion
        self._sync_tag_counts_after_problem_deletion(task, problem_id)

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

        task.solutions = [s for s in task.solutions if s.problem_id != problem_id] + [
            solution
        ]
        task.tags = [t for t in task.tags if t.problem_id != problem_id] + [tag]
        updated = self.repository.patch_task(
            task_id, solutions=task.solutions, tags=task.tags
        )
        return updated

    def _sync_tag_counts_after_problem_deletion(self, task, problem_id: str):
        """Decrease tag reference counts after deleting a problem."""
        self.tag_sync_service.sync_after_problem_deletion(task, problem_id)

    def _sync_tag_counts_after_task_deletion(self, task):
        """Decrease tag reference counts after deleting a task."""
        self.tag_sync_service.sync_after_task_deletion(task)

    # -------------------- library view --------------------

    def list_problems(
        self,
        *,
        subject: str | None = None,
        tag: str | None = None,
        source: str | list[str] | None = None,
        knowledge_tag: str | list[str] | None = None,
        error_tag: str | list[str] | None = None,
        user_tag: str | list[str] | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
    ) -> ProblemsResponse:  # pylint: disable=too-many-locals
        """Return a flattened library view of problems."""
        tasks = self.repository.list_all().values()
        items: list[ProblemSummary] = []

        # Parse date filters
        date_after: datetime | None = None
        date_before: datetime | None = None
        if created_after is not None:
            try:
                # Support both "YYYY-MM-DD" format (from HTML date input) and ISO 8601
                if len(created_after) == 10 and created_after.count("-") == 2:
                    # Parse "YYYY-MM-DD" format as midnight UTC
                    parsed = datetime.strptime(created_after, "%Y-%m-%d")
                    date_after = parsed.replace(tzinfo=timezone.utc)
                else:
                    # Parse ISO format and ensure it's timezone-aware (assume UTC if no timezone)
                    parsed = datetime.fromisoformat(created_after)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    date_after = parsed
            except ValueError:
                logger.warning("Invalid created_after format: %s", created_after)
        if created_before is not None:
            try:
                # Support both "YYYY-MM-DD" format (from HTML date input) and ISO 8601
                if len(created_before) == 10 and created_before.count("-") == 2:
                    # Parse "YYYY-MM-DD" format as end of day UTC (23:59:59.999999)
                    parsed = datetime.strptime(created_before, "%Y-%m-%d")
                    date_before = parsed.replace(
                        hour=23,
                        minute=59,
                        second=59,
                        microsecond=999999,
                        tzinfo=timezone.utc,
                    )
                else:
                    # Parse ISO format and ensure it's timezone-aware (assume UTC if no timezone)
                    parsed = datetime.fromisoformat(created_before)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    date_before = parsed
            except ValueError:
                logger.warning("Invalid created_before format: %s", created_before)

        # Normalize filters to lists for consistent filtering
        source_list = None
        if source is not None:
            source_list = [source] if isinstance(source, str) else source

        knowledge_tag_list = None
        if knowledge_tag is not None:
            knowledge_tag_list = (
                [knowledge_tag] if isinstance(knowledge_tag, str) else knowledge_tag
            )

        error_tag_list = None
        if error_tag is not None:
            error_tag_list = [error_tag] if isinstance(error_tag, str) else error_tag

        user_tag_list = None
        if user_tag is not None:
            user_tag_list = [user_tag] if isinstance(user_tag, str) else user_tag

        for task in tasks:
            task_subject = task.payload.subject

            tag_index = {t.problem_id: t for t in task.tags}

            for problem in task.problems:
                # Filter by problem-level subject (auto-detected) or fallback to task subject
                problem_subject = getattr(problem, "subject", task_subject)
                if subject is not None and problem_subject != subject:
                    continue
                tag_result = tag_index.get(problem.problem_id)

                manual_knowledge = list(getattr(problem, "knowledge_tags", []) or [])
                manual_error = list(getattr(problem, "error_tags", []) or [])
                manual_custom = list(getattr(problem, "user_tags", []) or [])
                ai_knowledge = (
                    list(getattr(tag_result, "knowledge_points", []))
                    if tag_result
                    else []
                )
                ai_error = (
                    list(getattr(tag_result, "error_hypothesis", []))
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
                combined_error = _merge_unique([*manual_error, *ai_error])

                # Apply filters
                if tag is not None and tag not in combined_knowledge:
                    continue
                if source_list is not None:
                    # Filter by multiple sources (OR logic)
                    if problem.source not in source_list:
                        continue
                if knowledge_tag_list is not None:
                    # Filter by multiple knowledge tags (OR logic) - check combined tags
                    if not any(kt in combined_knowledge for kt in knowledge_tag_list):
                        continue
                if error_tag_list is not None:
                    # Filter by multiple error tags (OR logic) - check combined tags
                    if not any(et in combined_error for et in error_tag_list):
                        continue
                if user_tag_list is not None:
                    # Filter by multiple custom tags (OR logic) - only manual tags
                    if not any(ut in manual_custom for ut in user_tag_list):
                        continue
                if date_after is not None and task.created_at < date_after:
                    continue
                if date_before is not None and task.created_at > date_before:
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
                        subject=getattr(problem, "subject", task_subject),
                        grade=task.payload.grade,
                        source=problem.source,
                        knowledge_points=combined_knowledge,
                        knowledge_tags=manual_knowledge,
                        error_tags=manual_error,
                        user_tags=manual_custom,
                        created_at=task.created_at,
                    )
                )

        items.sort(
            key=lambda item: (
                item.created_at,
                item.task_id,
                item.problem_id,
            ),
            reverse=True,
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
        """Update tag store ref_counts after pipeline run."""
        self.tag_sync_service.sync_after_pipeline(
            manual_knowledge=manual_knowledge,
            manual_error=manual_error,
            manual_source=manual_source,
            tags=tags,
        )

    def process_task_sync(
        self,
        task_id: str,
        existing_problems=None,
        on_progress=None,
    ):
        """Run the full pipeline synchronously for a task."""
        with self._processing_lock:
            if task_id in self._processing_inflight:
                return self.get_task(task_id)
            self._processing_inflight.add(task_id)

        def progress_bridge(stage: str, message: str | None = None):
            # Write progress to stream file for polling
            self._write_stream_event(
                task_id, "progress", {"stage": stage, "message": message}
            )

            # Also update task stage field for real-time status
            self.repository.patch_task(task_id, stage=stage, stage_message=message)

            if on_progress:
                try:
                    on_progress(stage, message)
                except Exception:
                    pass

        done_status = "failed"
        try:
            if self._is_task_cancelled(task_id):
                done_status = "cancelled"
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
                    existing_problems=existing_problems,
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

                done_status = "completed"
                return self._finalize_success(task_id, result)
            except _TaskCancelled:
                done_status = "cancelled"
                return self._finalize_cancelled(task_id)
            except HTTPException:
                raise
            except Exception as exc:  # pylint: disable=broad-exception-caught
                done_status = "failed"
                self._finalize_failed(task_id, exc)
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            # Write done event to stream file
            if task_id in self._task_cancelled:
                self._write_stream_event(task_id, "done", {"status": "cancelled"})
            else:
                try:
                    final_task = self.repository.get(task_id)
                    if final_task.status == TaskStatus.CANCELLED:
                        done_status = "cancelled"
                    elif final_task.status == TaskStatus.FAILED:
                        done_status = "failed"
                    elif final_task.status == TaskStatus.COMPLETED:
                        done_status = "completed"
                except Exception:
                    # Keep the best-effort status inferred from the run path.
                    pass

                self._write_stream_event(task_id, "done", {"status": done_status})

            with self._processing_lock:
                self._processing_inflight.discard(task_id)

    def _write_stream_event(self, task_id: str, event: str, payload: dict):
        """Write an event to the task stream file for polling."""
        data = {
            "event": event,
            "payload": payload,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        path = self.streams_dir / f"{task_id}.txt"
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to write stream: %s", e)
