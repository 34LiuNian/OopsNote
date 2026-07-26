"""Canonical OCR response contract and single-question normalization."""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from oopsnote.content import normalize_oopsmark, normalize_option_text


ReviewReason = Literal[
    "unreadable",
    "incomplete",
    "multiple_questions",
    "other",
]

OCR_INSTRUCTION = (
    "Extract only printed content for one independent question. Return one strict JSON object "
    "with exactly these fields: content_format='oopsmark-v1'; "
    "subject='math'|'physics'|'chemistry'; "
    "question_type='单选题'|'多选题'|'填空题'|'解答题'; problem_text:string; "
    "options:string[]; has_diagram:boolean; "
    "review_reason:null|'unreadable'|'incomplete'|'multiple_questions'|'other'; "
    "uncertain_regions:string[]; confidence:number from 0 to 1. "
    "If the image contains two or more independent top-level question numbers, extract only "
    "the first complete top-level question and set review_reason='multiple_questions'. Parts "
    "such as （1）（2） or ①② under one top-level number belong to the same question and must "
    "not trigger multiple_questions. Use OopsMark v1: inline math is $...$, display math is "
    "$$...$$. Represent actual subquestions as separate paragraphs beginning exactly （1）, "
    "（2）, and so on; never use Markdown 1./2. list markers and never invent subquestion "
    "markers for a single-part question. options never appear in problem_text. Each options "
    "entry contains only its body: omit printed labels such as A., A], (A), or 1.; array "
    "position maps to A, B, C, and so on. Never emit raw LaTeX environments "
    "such as array, tabular, enumerate, or tikzpicture. Do not solve or invent unreadable text."
)


class OcrExtraction(BaseModel):
    """Validated provider output before it enters the managed agent context."""

    model_config = ConfigDict(extra="forbid")

    content_format: Literal["oopsmark-v1"]
    subject: Literal["math", "physics", "chemistry"]
    question_type: Literal["单选题", "多选题", "填空题", "解答题"]
    problem_text: str = Field(min_length=1)
    options: list[str]
    has_diagram: bool
    review_reason: Optional[ReviewReason] = None
    uncertain_regions: list[str]
    confidence: float = Field(ge=0, le=1)


_TOP_LEVEL_NUMBER = re.compile(r"(?m)^[ \t]*(\d{1,3})[.．、][ \t]*")


def normalize_ocr_result(
    payload: object,
    *,
    expected_question_no: object = None,
) -> dict[str, object]:
    """Validate OCR and trim a following top-level question when it is detectable."""

    extraction = OcrExtraction.model_validate(payload)
    expected = str(expected_question_no or "").strip()
    matches = list(_TOP_LEVEL_NUMBER.finditer(extraction.problem_text))
    boundary = None
    if expected.isdigit():
        expected_index = next(
            (index for index, match in enumerate(matches) if match.group(1) == expected),
            None,
        )
        if expected_index is not None:
            boundary = next(
                (
                    match.start()
                    for match in matches[expected_index + 1 :]
                    if match.group(1) != expected
                ),
                None,
            )
    if boundary is not None:
        extraction = extraction.model_copy(
            update={
                "problem_text": extraction.problem_text[:boundary].rstrip(),
                "review_reason": extraction.review_reason or "multiple_questions",
            }
        )
    extraction = extraction.model_copy(
        update={
            "problem_text": normalize_oopsmark(extraction.problem_text),
            "options": [normalize_option_text(option) for option in extraction.options],
        }
    )
    return extraction.model_dump(mode="json")


__all__ = ["OCR_INSTRUCTION", "OcrExtraction", "normalize_ocr_result"]
