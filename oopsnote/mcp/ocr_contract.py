"""Canonical OCR response contract and single-question normalization."""

from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from oopsnote.content import normalize_oopsmark, normalize_option_text


ReviewReason = Literal[
    "unreadable",
    "incomplete",
    "multiple_questions",
    "other",
]

StudentResponseStatus = Literal["answered", "unanswered", "unknown"]

OCR_INSTRUCTION = (
    "Extract only printed content for one independent question. Return one strict JSON object "
    "with exactly these fields: content_format='oopsmark-v1'; "
    "subject='math'|'physics'|'chemistry'; "
    "question_type='单选题'|'多选题'|'填空题'|'解答题'; problem_text:string; "
    "options:string[]; has_diagram:boolean; printed_question_no:positive integer|null; "
    "printed_chapter:string|null; "
    "student_response_status:'answered'|'unanswered'|'unknown'; student_response:string; "
    "review_reason:null|'unreadable'|'incomplete'|'multiple_questions'|'other'; "
    "uncertain_regions:string[]; confidence:number from 0 to 1. "
    "If the image contains two or more independent top-level question numbers, extract only "
    "the first complete top-level question and set review_reason='multiple_questions'. Parts "
    "such as （1）（2） or ①② under one top-level number belong to the same question and must "
    "not trigger multiple_questions. Top-level printed numbers are metadata only: never put a "
    "prefix such as '第 N 题', 'N.', or 'N、' into problem_text, and never invent one from "
    "page/order/task context. Use OopsMark v1: inline math is $...$, display math is "
    "$$...$$. Represent actual subquestions as separate paragraphs beginning exactly （1）, "
    "（2）, and so on; never use Markdown 1./2. list markers and never invent subquestion "
    "markers for a single-part question. options never appear in problem_text. Each options "
    "entry contains only its body: omit printed labels such as A., A], (A), or 1.; array "
    "position maps to A, B, C, and so on. A formula-only option still includes $...$ math "
    "delimiters, for example '$\\frac{5}{2}$'. Never emit raw LaTeX environments "
    "such as array, tabular, enumerate, or tikzpicture. student_response contains only visible "
    "student handwriting or answer marks, never printed question text or a generated solution. "
    "Use answered only when a readable student response is visible, unanswered when the question "
    "is readable but no student response is present, and unknown when the response state cannot be "
    "determined. Set printed_question_no or printed_chapter only when that exact identifier is visibly "
    "printed; omit both from problem_text and use null when absent or unclear. Do not solve or invent unreadable text."
)


class OcrExtraction(BaseModel):
    """Validated provider output before it enters the managed agent context."""

    model_config = ConfigDict(extra="forbid")

    content_format: Literal["oopsmark-v1"]
    subject: Literal["math", "physics", "chemistry"]
    question_type: Literal["单选题", "多选题", "填空题", "解答题"]
    problem_text: str
    options: list[str]
    has_diagram: bool
    printed_question_no: Optional[int] = Field(default=None, ge=1, le=999)
    printed_chapter: Optional[str] = Field(default=None, max_length=160)
    student_response_status: StudentResponseStatus
    student_response: str
    review_reason: Optional[ReviewReason] = None
    uncertain_regions: list[str]
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_student_response(self) -> "OcrExtraction":
        self.problem_text = normalize_oopsmark(self.problem_text)
        if self.printed_chapter is not None:
            self.printed_chapter = self.printed_chapter.strip() or None
        if not self.problem_text and self.review_reason != "unreadable":
            raise ValueError(
                "empty OCR problem_text requires review_reason=unreadable"
            )
        self.student_response = normalize_oopsmark(self.student_response)
        if self.student_response_status == "answered" and not self.student_response:
            raise ValueError("answered OCR result requires student_response")
        if self.student_response_status != "answered" and self.student_response:
            raise ValueError(
                "student_response must be empty unless student_response_status=answered"
            )
        return self


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


__all__ = [
    "OCR_INSTRUCTION",
    "OcrExtraction",
    "StudentResponseStatus",
    "normalize_ocr_result",
]
