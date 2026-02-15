from __future__ import annotations

import mimetypes
import json
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
import time
import traceback
from typing import Callable
from uuid import uuid4

from ..clients import AIClient
from ..models import (
    AssetMetadata,
    CropRegion,
    DetectionOutput,
    ProblemBlock,
    TaskCreateRequest,
)
from .agent_flow import PromptTemplate

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_OCR_TEMPLATE: PromptTemplate | None = None


def _load_ocr_template() -> PromptTemplate:
    global _OCR_TEMPLATE
    if _OCR_TEMPLATE is None:
        _OCR_TEMPLATE = PromptTemplate.from_file(_PROMPT_DIR / "ocr.txt")
    return _OCR_TEMPLATE


class OcrExtractor:
    """Placeholder OCR/structure extractor that converts regions into problem drafts."""

    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> list[ProblemBlock]:
        regions = detection.regions or [
            CropRegion(id=uuid4().hex, bbox=[0.05, 0.05, 0.9, 0.9], label="full")
        ]

        problems: list[ProblemBlock] = []
        for idx, region in enumerate(regions, start=1):
            # Keep placeholder text stable for tests and demos.
            problem_text = (
                "已知直角三角形ABC中，∠C=90°，AC=3，BC=4，求AB的长度。"
                if idx == 1
                else f"第{idx}题：已知直角三角形ABC中，∠C=90°，AC=3，BC=4，求AB的长度。"
            )

            problems.append(
                ProblemBlock(
                    problem_id=uuid4().hex,
                    region_id=region.id,
                    question_no=payload.question_no,
                    problem_text=problem_text,
                    latex_blocks=[],
                    ocr_text=problem_text,
                    options=[],
                    crop_image_url=None,
                    crop_bbox=None,
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
        thinking: bool | None = None,
    ) -> list[ProblemBlock]:
        # If we can't access a local image file, fallback to placeholder extractor.
        if not asset or not asset.path:
            return OcrExtractor().run(payload, detection, asset)

        image_path = Path(asset.path)
        if not image_path.exists():
            return OcrExtractor().run(payload, detection, asset)

        image_bytes = image_path.read_bytes()
        mime_type = (
            asset.mime_type or mimetypes.guess_type(str(image_path))[0] or "image/png"
        )

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

        ocr_template = _load_ocr_template()

        problems: list[ProblemBlock] = []
        for idx, region in enumerate(regions, start=1):
            started = time.perf_counter()

            ctx = {
                "subject": payload.subject,
                "grade": payload.grade or "",
                "notes": payload.notes or "",
            }

            system_prompt, user_prompt = ocr_template.render(ctx)

            logger.info(
                "LLM-OCR request region=%s idx=%s/%s model=%s mime=%s img_bytes=%s approx_chars=%s",
                region.id,
                idx,
                len(regions),
                getattr(self.client, "model", None),
                mime_type,
                len(image_bytes),
                len(system_prompt) + len(user_prompt),
            )

            region_image_bytes, region_mime_type = image_bytes, mime_type

            try:
                # Call AI without response_model for schema logic (business layer only).
                # The client will return a plain dict based on the prompt's JSON instructions.
                payload_dict = self.client.structured_chat_with_image(
                    system_prompt,
                    user_prompt,
                    region_image_bytes,
                    region_mime_type,
                    thinking=thinking,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "LLM-OCR done region=%s ms=%.1f",
                    region.id,
                    elapsed_ms,
                )
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.exception(
                    "LLM-OCR failed region=%s ms=%.1f",
                    region.id,
                    elapsed_ms,
                )
                err_msg = str(exc) or exc.__class__.__name__
                raise

            # Business Layer Extraction (Plain Dict)
            problem_text = _coerce_str(payload_dict.get("problem_text"), fallback="")
            latex_blocks = _coerce_str_list(payload_dict.get("latex_blocks", []))
            ocr_text = _coerce_str(payload_dict.get("ocr_text"), fallback="")

            # Some models spam trailing whitespace/newlines when hitting max tokens.
            rstrip_enabled = (
                os.getenv("AI_OCR_RSTRIP_OUTPUT", "false").lower() == "true"
            )
            if rstrip_enabled:
                if isinstance(problem_text, str):
                    problem_text = problem_text.rstrip()
                if isinstance(ocr_text, str):
                    ocr_text = ocr_text.rstrip()

            if not problem_text:
                raise RuntimeError("OCR returned empty or missing problem_text")

            normalized_options = []
            raw_options = payload_dict.get("options")
            if isinstance(raw_options, list):
                for item in raw_options:
                    if not isinstance(item, dict):
                        continue
                    key = _coerce_str(item.get("key"), fallback="").strip()
                    text = _coerce_str(item.get("text"), fallback="").strip()
                    if not key or not text:
                        continue
                    normalized_options.append(
                        {
                            "key": key,
                            "text": text,
                            "latex_blocks": _coerce_str_list(item.get("latex_blocks", [])),
                        }
                    )

            problems.append(
                ProblemBlock(
                    problem_id=uuid4().hex,
                    region_id=region.id,
                    question_no=payload.question_no,
                    problem_text=problem_text,
                    latex_blocks=latex_blocks,
                    ocr_text=ocr_text,
                    options=normalized_options,
                    crop_image_url=None,
                    crop_bbox=None,
                    source=payload.notes or None,
                )
            )

            elapsed_ms = (time.perf_counter() - started) * 1000
            _emit_ocr_event(
                on_delta,
                stage="ocr",
                event="done",
                region=region.id,
                ms=round(elapsed_ms, 1),
                option_count=len(normalized_options),
            )

        return problems


@dataclass
class OcrRouter:
    """Select LLM OCR when a model override is configured, else fallback."""

    base_extractor: OcrExtractor
    llm_extractor: LLMOcrExtractor
    model_resolver: object | None = None
    thinking_resolver: Callable[[str], bool] | None = None

    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
    ) -> list[ProblemBlock]:
        thinking = None
        if self.thinking_resolver is not None:
            try:
                thinking = bool(self.thinking_resolver("OCR"))
            except Exception:
                thinking = None
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
                return self.llm_extractor.run(
                    payload, detection, asset, thinking=thinking
                )
            finally:
                if original is not None:
                    self.llm_extractor.client.model = original

        logger.info("OCR router using base extractor (no override)")
        return self.base_extractor.run(payload, detection, asset)


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
