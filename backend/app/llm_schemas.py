from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .models import OptionItem


class OcrOutput(BaseModel):
    problem_text: str
    latex_blocks: List[str] = Field(default_factory=list)
    options: List[OptionItem] = Field(default_factory=list)
    ocr_text: Optional[str] = None


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
