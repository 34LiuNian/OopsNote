from __future__ import annotations

import mimetypes
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import time
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
from . import utils

logger = logging.getLogger(__name__)

# OCR template cache (use utils._load_ocr_template instead)
_OCR_TEMPLATE = None


class OcrExtractor:
    """Base interface for OCR extraction. Placeholders are intentionally disabled."""

    def run(
        self,
        payload: TaskCreateRequest,
        detection: DetectionOutput,
        asset: AssetMetadata | None = None,
        on_delta: Callable[[str], None] | None = None,
        thinking: bool | None = None,
    ) -> list[ProblemBlock]:
        raise RuntimeError(
            "OCR extraction failed: No LLM result available and placeholders are disabled."
        )


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
        if not asset or not asset.path:
            raise RuntimeError("OCR failed: Asset path is missing.")

        # Convert relative path (/assets/xxx.jpg) to absolute path
        image_path = Path(asset.path)
        if not image_path.is_absolute():
            # Relative path from storage module
            image_path = (
                Path(__file__).resolve().parent.parent.parent
                / "storage"
                / "assets"
                / image_path.name
            )

        if not image_path.exists():
            raise RuntimeError(f"OCR failed: Image file not found at {image_path}")

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

        ocr_template = utils._load_ocr_template()

        problems: list[ProblemBlock] = []
        for idx, region in enumerate(regions, start=1):
            started = time.perf_counter()

            # Handle 'auto' subject - pass empty string to let LLM auto-detect
            subject_for_prompt = "" if payload.subject == "auto" else payload.subject

            ctx = {
                "subject": subject_for_prompt,
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
            except Exception:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.exception(
                    "LLM-OCR failed region=%s ms=%.1f",
                    region.id,
                    elapsed_ms,
                )
                raise

            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "LLM-OCR done region=%s ms=%.1f",
                region.id,
                elapsed_ms,
            )

            # Business Layer Extraction (Plain Dict)
            problem_text = utils._coerce_str(
                payload_dict.get("problem_text"), fallback=""
            )
            # OCR should provide a normalized `question_type` when possible (e.g. 单选/多选/填空/解答)
            question_type = utils._coerce_str(payload_dict.get("question_type"), None)
            # Auto-detect subject from OCR
            subject = utils._coerce_str(payload_dict.get("subject"), fallback=None)
            # Validate subject value - if user selected 'auto' or LLM failed to detect, use 'math' as fallback
            if subject not in ("math", "physics", "chemistry"):
                subject = "math" if payload.subject == "auto" else payload.subject

            # Some models spam trailing whitespace/newlines when hitting max tokens.
            rstrip_enabled = (
                os.getenv("AI_OCR_RSTRIP_OUTPUT", "false").lower() == "true"
            )
            if rstrip_enabled:
                if isinstance(problem_text, str):
                    problem_text = problem_text.rstrip()

            if not problem_text:
                raise RuntimeError("OCR returned empty or missing problem_text")

            normalized_options = []
            raw_options = payload_dict.get("options")
            if isinstance(raw_options, list):
                for item in raw_options:
                    if not isinstance(item, dict):
                        continue
                    key = utils._coerce_str(item.get("key"), fallback="").strip()
                    text = utils._coerce_str(item.get("text"), fallback="").strip()
                    if not key or not text:
                        continue
                    normalized_options.append(
                        {
                            "key": key,
                            "text": text,
                        }
                    )

            problems.append(
                ProblemBlock(
                    problem_id=uuid4().hex,
                    region_id=region.id,
                    subject=subject,
                    question_no=payload.question_no,
                    question_type=question_type,
                    problem_text=problem_text,
                    options=normalized_options,
                    crop_image_url=None,
                    crop_bbox=None,
                    source=payload.notes or None,
                )
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

        logger.info("OCR router using default LLM extractor")
        return self.llm_extractor.run(payload, detection, asset, thinking=thinking)


# Note: Text processing helpers moved to utils.py
# - _normalize_linebreaks
# - _coerce_str
# - _coerce_str_list
