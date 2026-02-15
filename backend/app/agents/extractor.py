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
from ..llm_schemas import OcrOutput
from ..models import (
    AssetMetadata,
    CropRegion,
    DetectionOutput,
    ProblemBlock,
    TaskCreateRequest,
)
from .agent_flow import PromptTemplate
from ..llm_logging import append_llm_error_log

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"
_SKILL_DIR = Path(__file__).parent / "skills" / "ocr"
_OCR_TEMPLATE: PromptTemplate | None = None
_OCR_RETRY_TEMPLATE: PromptTemplate | None = None
_CHEMFIG_SKILL: str | None = None

_CHEMFIG_HINT_RE = re.compile(r"chemfig|化学|有机|结构式|分子式|反应", re.IGNORECASE)


def _load_ocr_templates() -> tuple[PromptTemplate, PromptTemplate]:
    global _OCR_TEMPLATE, _OCR_RETRY_TEMPLATE
    if _OCR_TEMPLATE is None:
        _OCR_TEMPLATE = PromptTemplate.from_file(_PROMPT_DIR / "ocr.txt")
    if _OCR_RETRY_TEMPLATE is None:
        _OCR_RETRY_TEMPLATE = PromptTemplate.from_file(_PROMPT_DIR / "ocr_retry.txt")
    return _OCR_TEMPLATE, _OCR_RETRY_TEMPLATE


def _load_chemfig_skill() -> str:
    global _CHEMFIG_SKILL
    if _CHEMFIG_SKILL is None:
        _CHEMFIG_SKILL = (
            (_SKILL_DIR / "chemfig.txt").read_text(encoding="utf-8").strip()
        )
    return _CHEMFIG_SKILL


def _should_inject_chemfig_skill(payload: TaskCreateRequest) -> bool:
    parts = [payload.subject or "", payload.notes or ""]
    return bool(_CHEMFIG_HINT_RE.search(" ".join(parts)))


def _inject_skill(system_prompt: str, skill_text: str, skill_name: str) -> str:
    if not skill_text:
        return system_prompt
    return f"{system_prompt}\n\n[Skill: {skill_name}]\n{skill_text}\n"


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
        on_delta: Callable[[str], None] | None = None,
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

        ocr_template, ocr_retry_template = _load_ocr_templates()

        problems: list[ProblemBlock] = []
        for idx, region in enumerate(regions, start=1):
            started = time.perf_counter()
            if on_delta is not None:
                try:
                    on_delta(
                        (
                            f'{{"stage":"ocr","event":"start","region":"{region.id}",'
                            f'"idx":{idx},"count":{len(regions)}}}'
                        )
                    )
                except Exception:
                    pass

            ctx = {
                "subject": payload.subject,
                "grade": payload.grade or "",
                "notes": payload.notes or "",
            }

            system_prompt, user_prompt = ocr_template.render(ctx)
            retry_system_prompt, retry_prompt = ocr_retry_template.render(ctx)
            if _should_inject_chemfig_skill(payload):
                skill_text = _load_chemfig_skill()
                system_prompt = _inject_skill(system_prompt, skill_text, "chemfig")
                retry_system_prompt = _inject_skill(
                    retry_system_prompt, skill_text, "chemfig"
                )

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
                payload_dict = self.client.structured_chat_with_image(
                    system_prompt,
                    user_prompt,
                    region_image_bytes,
                    region_mime_type,
                    response_model=OcrOutput,
                    on_delta=on_delta,
                    thinking=thinking,
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                keys = (
                    sorted([str(k) for k in payload_dict.keys()])
                    if isinstance(payload_dict, dict)
                    else []
                )
                logger.info(
                    "LLM-OCR done region=%s ms=%.1f keys=%s",
                    region.id,
                    elapsed_ms,
                    keys,
                )
                if on_delta is not None:
                    try:
                        on_delta(
                            (
                                f'{{"stage":"ocr","event":"done","region":"{region.id}",'
                                f'"ms":{elapsed_ms:.1f},"keys":{keys}}}'
                            )
                        )
                    except Exception:
                        pass
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.exception(
                    "LLM-OCR failed region=%s ms=%.1f; retry with reduced schema",
                    region.id,
                    elapsed_ms,
                )
                err_msg = str(exc) or exc.__class__.__name__
                tb = traceback.format_exc()
                append_llm_error_log(
                    {
                        "stage": "ocr",
                        "event": "request_failed",
                        "region": region.id,
                        "model": getattr(self.client, "model", None),
                        "error": err_msg,
                        "traceback": tb,
                    }
                )
                if on_delta is not None:
                    try:
                        on_delta(
                            json.dumps(
                                {
                                    "stage": "ocr",
                                    "event": "error",
                                    "region": region.id,
                                    "ms": round(elapsed_ms, 1),
                                    "message": "request_failed",
                                    "error": err_msg,
                                },
                                ensure_ascii=False,
                            )
                        )
                        on_delta(
                            json.dumps(
                                {
                                    "stage": "ocr",
                                    "event": "error_detail",
                                    "region": region.id,
                                    "error": err_msg,
                                    "traceback": tb,
                                },
                                ensure_ascii=False,
                            )
                        )
                    except Exception:
                        pass
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
                        response_model=OcrOutput,
                        on_delta=on_delta,
                        thinking=thinking,
                    )
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    keys = (
                        sorted([str(k) for k in payload_dict.keys()])
                        if isinstance(payload_dict, dict)
                        else []
                    )
                    logger.info(
                        "LLM-OCR retry ok region=%s ms=%.1f keys=%s",
                        region.id,
                        elapsed_ms,
                        keys,
                    )
                except Exception as exc:
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    logger.exception(
                        "LLM-OCR retry failed region=%s ms=%.1f",
                        region.id,
                        elapsed_ms,
                    )
                    err_msg = str(exc) or exc.__class__.__name__
                    tb = traceback.format_exc()
                    append_llm_error_log(
                        {
                            "stage": "ocr",
                            "event": "retry_failed",
                            "region": region.id,
                            "model": getattr(self.client, "model", None),
                            "error": err_msg,
                            "traceback": tb,
                        }
                    )
                    if on_delta is not None:
                        try:
                            on_delta(
                                json.dumps(
                                    {
                                        "stage": "ocr",
                                        "event": "error",
                                        "region": region.id,
                                        "ms": round(elapsed_ms, 1),
                                        "message": "retry_failed",
                                        "error": err_msg,
                                    },
                                    ensure_ascii=False,
                                )
                            )
                            on_delta(
                                json.dumps(
                                    {
                                        "stage": "ocr",
                                        "event": "error_detail",
                                        "region": region.id,
                                        "error": err_msg,
                                        "traceback": tb,
                                    },
                                    ensure_ascii=False,
                                )
                            )
                        except Exception:
                            pass
                    raise RuntimeError("LLM-OCR failed after retry")

            try:
                parsed = OcrOutput.model_validate(payload_dict)
            except Exception as exc:
                raise RuntimeError(f"Invalid OCR output format: {exc}") from exc

            problem_text = parsed.problem_text
            latex_blocks = parsed.latex_blocks
            ocr_text = parsed.ocr_text

            # Some models spam trailing whitespace/newlines when hitting max tokens.
            # Trim tail to prevent UI looking like it's "infinitely printing".
            rstrip_enabled = (
                os.getenv("AI_OCR_RSTRIP_OUTPUT", "false").lower() == "true"
            )
            if rstrip_enabled:
                if isinstance(problem_text, str):
                    problem_text = problem_text.rstrip()
                if isinstance(ocr_text, str):
                    ocr_text = ocr_text.rstrip()

            if not problem_text:
                raise RuntimeError("OCR returned empty problem_text")

            normalized_options = []
            for item in parsed.options or []:
                key = _coerce_str(getattr(item, "key", ""), fallback="").strip()
                text = _coerce_str(getattr(item, "text", ""), fallback="").strip()
                if not key or not text:
                    continue
                normalized_options.append(
                    {
                        "key": key,
                        "text": text,
                        "latex_blocks": _coerce_str_list(
                            getattr(item, "latex_blocks", [])
                        ),
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
        on_delta: Callable[[str], None] | None = None,
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
                    payload, detection, asset, on_delta=on_delta, thinking=thinking
                )
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
