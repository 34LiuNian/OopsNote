"""Canonical OCR response contract and single-question normalization."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from oopsnote.content import normalize_oopsmark, normalize_option_text

ReviewReason = Literal[
    "unreadable",
    "incomplete",
    "multiple_questions",
    "other",
]

StudentResponseStatus = Literal["answered", "unanswered", "unknown"]


class OcrExtraction(BaseModel):
    """Validated provider output before it enters the managed agent context."""

    model_config = ConfigDict(extra="forbid")

    content_format: Literal["oopsmark-v1"]
    subject: Literal["math", "physics", "chemistry"]
    question_type: Literal["单选题", "多选题", "填空题", "解答题"]
    problem_text: str
    options: list[str]
    has_diagram: bool
    printed_question_no: int | None = Field(default=None, ge=1, le=999)
    printed_chapter: str | None = Field(default=None, max_length=160)
    student_response_status: StudentResponseStatus
    student_response: str
    review_reason: ReviewReason | None = None
    uncertain_regions: list[str]
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_student_response(self) -> OcrExtraction:
        self.problem_text = normalize_oopsmark(self.problem_text)
        if self.printed_chapter is not None:
            self.printed_chapter = self.printed_chapter.strip() or None
        if not self.problem_text and self.review_reason != "unreadable":
            raise ValueError("empty OCR problem_text requires review_reason=unreadable")
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
    "OcrExtraction",
    "StudentResponseStatus",
    "normalize_ocr_result",
]
