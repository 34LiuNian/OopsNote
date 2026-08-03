"""Paper composition helpers."""

from .difficulty import (
    DIFFICULTY_BOUNDS,
    QUESTION_TYPE_ORDER,
    candidate_tasks,
    difficulty_band,
    difficulty_review_reason,
    infer_difficulty_coefficients,
    select_paper_items,
)
from .compiler import (
    PaperBundle,
    PaperCompileError,
    PaperCompileFailure,
    build_paper_bundle,
    build_paper_tex,
    compile_paper_pdf,
)
from .document import (
    PaperDiagram,
    PaperDocument,
    PaperDocumentError,
    PaperDocumentItem,
    PaperDocumentSection,
    build_paper_document,
)

__all__ = [
    "DIFFICULTY_BOUNDS",
    "QUESTION_TYPE_ORDER",
    "PaperBundle",
    "PaperCompileError",
    "PaperCompileFailure",
    "PaperDiagram",
    "PaperDocument",
    "PaperDocumentError",
    "PaperDocumentItem",
    "PaperDocumentSection",
    "build_paper_bundle",
    "build_paper_document",
    "build_paper_tex",
    "candidate_tasks",
    "compile_paper_pdf",
    "difficulty_band",
    "difficulty_review_reason",
    "infer_difficulty_coefficients",
    "select_paper_items",
]
