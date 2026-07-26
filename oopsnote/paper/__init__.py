"""Paper composition helpers."""

from .difficulty import (
    DIFFICULTY_BOUNDS,
    QUESTION_TYPE_ORDER,
    candidate_tasks,
    difficulty_band,
    infer_difficulty_coefficients,
    select_paper_items,
)
from .compiler import PaperCompileError, build_paper_tex, compile_paper_pdf

__all__ = [
    "DIFFICULTY_BOUNDS",
    "QUESTION_TYPE_ORDER",
    "PaperCompileError",
    "build_paper_tex",
    "candidate_tasks",
    "compile_paper_pdf",
    "difficulty_band",
    "infer_difficulty_coefficients",
    "select_paper_items",
]
