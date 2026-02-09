from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import OptionItem


class OcrOutput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": (
                "Return strict JSON with keys: problem_text, latex_blocks, ocr_text, options. "
                "Do not use Chinese key names like 题干/选项."
            )
        },
    )

    problem_text: str
    latex_blocks: List[str] = Field(default_factory=list)
    options: List[OptionItem] = Field(default_factory=list)
    ocr_text: Optional[str] = None

    @model_validator(mode="after")
    def validate_problem_text(self) -> "OcrOutput":
        if not (self.problem_text or "").strip():
            raise ValueError("problem_text must be non-empty")
        return self


class SolverOutput(BaseModel):
    answer: str
    explanation: str
    short_answer: str


class TaggerOutput(BaseModel):
    knowledge_points: List[str] = Field(default_factory=list)
    question_type: str
    skills: List[str] = Field(default_factory=list)
    error_hypothesis: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
