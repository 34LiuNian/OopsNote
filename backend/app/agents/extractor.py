from __future__ import annotations

import mimetypes
from io import BytesIO
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import time
from typing import Callable
from uuid import uuid4

from ..clients import AIClient
from ..llm_schemas import OcrOutput
from ..models import AssetMetadata, CropRegion, DetectionOutput, ProblemBlock, TaskCreateRequest
from .agent_flow import PromptTemplate

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_OCR_TEMPLATE: PromptTemplate | None = None
_OCR_RETRY_TEMPLATE: PromptTemplate | None = None


def _load_ocr_templates() -> tuple[PromptTemplate, PromptTemplate]:
    global _OCR_TEMPLATE, _OCR_RETRY_TEMPLATE
    if _OCR_TEMPLATE is None:
        _OCR_TEMPLATE = PromptTemplate.from_file(_PROMPT_DIR / "ocr.txt")
    if _OCR_RETRY_TEMPLATE is None:
        _OCR_RETRY_TEMPLATE = PromptTemplate.from_file(_PROMPT_DIR / "ocr_retry.txt")
    return _OCR_TEMPLATE, _OCR_RETRY_TEMPLATE


class OcrExtractor:
    """Placeholder OCR/structure extractor that converts regions into problem drafts."""

    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> list[ProblemBlock]:
        regions = detection.regions or [
            CropRegion(id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full")
        ]
        problems: list[ProblemBlock] = []
        for idx, region in enumerate(regions, start=1):
            latex = r"$$ F = ma $$" if payload.subject.lower().startswith("phy") else r"$$ a^2 + b^2 = c^2 $$"
            if on_delta is not None:
                try:
                    on_delta(
                        f'{{"stage_message":"OCR 占位","region":"{region.id}","idx":{idx},"count":{len(regions)}}}'
                    )
                except Exception:
                    pass
            problems.append(
                ProblemBlock(
                    problem_id=uuid4().hex,
                    region_id=region.id,
                    question_no=payload.question_no,
                    problem_text=(
                        "根据图示求解未知量" if payload.subject.lower().startswith("phy") else "求解直角三角形未知边"
                    ),
                    latex_blocks=[latex],
                    ocr_text="草稿 OCR 文本占位",
                    crop_image_url=str(getattr(asset, "path", None) or getattr(asset, "original_reference", "")) or None,
                    crop_bbox=region.bbox,
                    source=payload.notes or None,
                )
            )
        return problems


@dataclass
class LLMOcrExtractor:
    client: AIClient

    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> list[ProblemBlock]:
        # If we can't access a local image file, fallback to placeholder extractor.
        if not asset or not asset.path:
            return OcrExtractor().run(payload, detection, asset)

        image_path = Path(asset.path)
        if not image_path.exists():
            return OcrExtractor().run(payload, detection, asset)

        image_bytes = image_path.read_bytes()
        mime_type = asset.mime_type or mimetypes.guess_type(str(image_path))[0] or "image/png"

        logger.info(
            "LLM-OCR start model=%s mime=%s bytes=%s regions=%s",
            getattr(self.client, "model", None),
            mime_type,
            len(image_bytes),
            len(detection.regions or []),
        )

        regions = detection.regions or [
            CropRegion(id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full")
        ]

        ocr_template, ocr_retry_template = _load_ocr_templates()

        problems: list[ProblemBlock] = []
        for idx, region in enumerate(regions, start=1):
            started = time.perf_counter()
            ctx = {
                "subject": payload.subject,
                "grade": payload.grade or "",
                "notes": payload.notes or "",
                "bbox": str(region.bbox),
            }

            system_prompt, user_prompt = ocr_template.render(ctx)
            retry_system_prompt, retry_prompt = ocr_retry_template.render(ctx)

            logger.info(
                "LLM-OCR request region=%s idx=%s/%s bbox=%s model=%s mime=%s img_bytes=%s approx_chars=%s",
                region.id,
                idx,
                len(regions),
                region.bbox,
                getattr(self.client, "model", None),
                mime_type,
                len(image_bytes),
                len(system_prompt) + len(user_prompt),
            )

            # IMPORTANT: bbox is only meaningful if we actually crop the image.
            # Otherwise the model may extract multiple questions from the full page.
            crop_enabled = os.getenv("AI_OCR_CROP_ENABLED", "false").lower() == "true"
            if crop_enabled:
                region_image_bytes, region_mime_type = _try_crop_image_bytes(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    bbox=region.bbox,
                )
            else:
                region_image_bytes, region_mime_type = image_bytes, mime_type

            try:
                payload_dict = self.client.structured_chat_with_image(
                    system_prompt,
                    user_prompt,
                    region_image_bytes,
                    region_mime_type,
                    response_model=OcrOutput,
                    on_delta=on_delta,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                keys = sorted([str(k) for k in payload_dict.keys()]) if isinstance(payload_dict, dict) else []
                logger.info(
                    "LLM-OCR done region=%s ms=%.1f keys=%s",
                    region.id,
                    elapsed_ms,
                    keys,
                )
            except Exception:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.exception("LLM-OCR failed region=%s ms=%.1f; retry with reduced schema", region.id, elapsed_ms)
                try:
                    logger.info(
                        "LLM-OCR retry request region=%s model=%s approx_chars=%s",
                        region.id,
                        getattr(self.client, "model", None),
                        len(retry_system_prompt) + len(retry_prompt),
                    )
                    payload_dict = self.client.structured_chat_with_image(
                        retry_system_prompt,
                        retry_prompt,
                        region_image_bytes,
                        region_mime_type,
                        response_model=None,
                        on_delta=on_delta,
                    )
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    keys = sorted([str(k) for k in payload_dict.keys()]) if isinstance(payload_dict, dict) else []
                    logger.info(
                        "LLM-OCR retry ok region=%s ms=%.1f keys=%s",
                        region.id,
                        elapsed_ms,
                        keys,
                    )
                except Exception:
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    logger.exception(
                        "LLM-OCR retry failed region=%s ms=%.1f; fallback to placeholder",
                        region.id,
                        elapsed_ms,
                    )
                    payload_dict = {}

            problem_text = _coerce_str(payload_dict.get("problem_text"), fallback="")
            latex_blocks = _coerce_str_list(payload_dict.get("latex_blocks"))
            ocr_text = _coerce_str(payload_dict.get("ocr_text"), fallback=None)

            # Some models spam trailing whitespace/newlines when hitting max tokens.
            # Trim tail to prevent UI looking like it's "infinitely printing".
            rstrip_enabled = os.getenv("AI_OCR_RSTRIP_OUTPUT", "false").lower() == "true"
            if rstrip_enabled:
                if isinstance(problem_text, str):
                    problem_text = problem_text.rstrip()
                if isinstance(ocr_text, str):
                    ocr_text = ocr_text.rstrip()
            options = payload_dict.get("options")
            if not isinstance(options, list):
                options = []

            # Minimal coercion for options; keep only well-formed entries.
            normalized_options = []
            for item in options:
                if not isinstance(item, dict):
                    continue
                key = _coerce_str(item.get("key"), fallback="").strip()
                raw_text = _coerce_str(item.get("text"), fallback="")
                if rstrip_enabled:
                    raw_text = raw_text.rstrip()
                text = raw_text.strip()
                if not key or not text:
                    continue
                normalized_options.append(
                    {
                        "key": key,
                        "text": text,
                        "latex_blocks": _coerce_str_list(item.get("latex_blocks")),
                    }
                )

            # If the model returns empty content, fallback for this region.
            if not problem_text:
                fallback = OcrExtractor().run(payload, DetectionOutput(action="single", regions=[region]), asset)[0]
                problem_text = fallback.problem_text
                latex_blocks = fallback.latex_blocks
                ocr_text = fallback.ocr_text

            problems.append(
                ProblemBlock(
                    problem_id=uuid4().hex,
                    region_id=region.id,
                    question_no=payload.question_no,
                    problem_text=problem_text,
                    latex_blocks=latex_blocks,
                    ocr_text=ocr_text,
                    options=normalized_options,
                    crop_image_url=str(getattr(asset, "path", None) or getattr(asset, "original_reference", ""))
                    or None,
                    crop_bbox=region.bbox,
                    source=payload.notes or None,
                )
            )

        return problems


def _try_crop_image_bytes(*, image_bytes: bytes, mime_type: str, bbox: list[float]) -> tuple[bytes, str]:
    """Crop by normalized [x, y, width, height] bbox.

    Returns (bytes, mime_type). On any failure, returns the original image.
    """

    try:
        from PIL import Image
    except Exception:
        return image_bytes, mime_type

    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img.load()
            w, h = img.size
            if w <= 0 or h <= 0:
                return image_bytes, mime_type
            if not (isinstance(bbox, list) and len(bbox) == 4):
                return image_bytes, mime_type

            x, y, bw, bh = bbox
            left = int(max(0, min(1, x)) * w)
            top = int(max(0, min(1, y)) * h)
            right = int(max(0, min(1, x + bw)) * w)
            bottom = int(max(0, min(1, y + bh)) * h)
            if right <= left or bottom <= top:
                return image_bytes, mime_type

            cropped = img.crop((left, top, right, bottom))
            out = BytesIO()
            # Use PNG to avoid format edge cases with gateways.
            cropped.save(out, format="PNG")
            return out.getvalue(), "image/png"
    except Exception:
        return image_bytes, mime_type


@dataclass
class OcrRouter:
    """Select LLM OCR when a model override is configured, else fallback."""

    base_extractor: OcrExtractor
    llm_extractor: LLMOcrExtractor
    model_resolver: object | None = None

    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> list[ProblemBlock]:
        override = None
        if self.model_resolver:
            try:
                override = self.model_resolver("OCR")  # type: ignore[operator]
            except Exception:
                override = None

        if override:
            logger.info("OCR router using override model=%s", override)
            try:
                original = getattr(self.llm_extractor.client, "model", None)
                self.llm_extractor.client.model = str(override)
                return self.llm_extractor.run(payload, detection, asset, on_delta=on_delta)
            finally:
                if original is not None:
                    self.llm_extractor.client.model = original

        logger.info("OCR router using base extractor (no override)")
        return self.base_extractor.run(payload, detection, asset, on_delta=on_delta)


def _coerce_str(value: object, fallback: str | None) -> str | None:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value
    return str(value)


def _coerce_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        out = []
        for item in value:
            if item is None:
                continue
            out.append(str(item))
        return out
    if isinstance(value, str) and value.strip():
        return [value]
    return []
