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
    OptionItem,
    ProblemBlock,
    TaskCreateRequest,
)
from ..config.subjects import VALID_SUBJECT_KEYS, DEFAULT_SUBJECT
from . import utils

logger = logging.getLogger(__name__)

# OCR 模板缓存（建议改用 utils._load_ocr_template）
_OCR_TEMPLATE = None


class OcrExtractor:
    """OCR 提取基类接口；有意禁用占位符回退。"""

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

        # 将相对路径（/assets/xxx.jpg）转换为绝对路径
        image_path = Path(asset.path)
        if not image_path.is_absolute():
            # 存储模块中的相对路径
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

            # 处理 `auto` 学科：传空字符串让 LLM 自动识别
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
                # 业务层按 schema 逻辑调用 AI，不传 response_model。
                # 客户端将依据提示词 JSON 约束返回普通 dict。
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

            # 业务层字段提取（普通 dict）
            problem_text = utils._coerce_str(
                payload_dict.get("problem_text"), fallback=""
            )
            # OCR 应尽量输出规范化的 `question_type`（如单选/多选/填空/解答）
            question_type = utils._coerce_str(payload_dict.get("question_type"), None)
            ocr_has_diagram = bool(payload_dict.get("has_diagram", False))
            # 根据 OCR 结果自动识别学科
            subject = utils._coerce_str(payload_dict.get("subject"), fallback=None)
            # 校验学科值：若用户选了 auto 或 LLM 未识别成功，回退到默认学科
            if subject not in VALID_SUBJECT_KEYS:
                subject = DEFAULT_SUBJECT if payload.subject == "auto" else payload.subject

            # 某些模型在接近 token 上限时会输出大量尾随空白/换行。
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
                    key_val = item.get("key")
                    text_val = item.get("text")
                    if key_val is None or text_val is None:
                        continue
                    key = str(key_val).strip() if key_val is not None else ""
                    text = str(text_val).strip() if text_val is not None else ""
                    if not key or not text:
                        continue
                    normalized_options.append(
                        OptionItem(key=key, text=text)
                    )

            problems.append(
                ProblemBlock(
                    problem_id=uuid4().hex,
                    region_id=region.id,
                    subject=subject,
                    question_no=payload.question_no,
                    question_type=question_type,
                    problem_text=problem_text,
                    ocr_has_diagram=ocr_has_diagram,
                    options=normalized_options,
                    crop_image_url=None,
                    crop_bbox=None,
                    source=payload.notes or None,
                )
            )

        return problems


@dataclass
class OcrRouter:
    """若存在模型覆盖则走 LLM OCR，否则走默认路径。"""

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


# 说明：文本处理辅助函数已迁移至 utils.py
# - _normalize_linebreaks
# - _coerce_str
# - _coerce_str_list
