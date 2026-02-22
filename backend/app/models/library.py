"""
Library and query models.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .common import OptionItem
from .problem import TaggingResult


class ProblemSummary(BaseModel):
    """Flattened view of a single problem across all tasks, for library/list APIs."""
    task_id: str
    problem_id: str
    question_no: Optional[str] = None
    question_type: Optional[str] = None
    problem_text: str
    options: List[OptionItem] = Field(default_factory=list)
    subject: str
    grade: Optional[str] = None
    source: Optional[str] = None
    knowledge_points: List[str] = Field(default_factory=list)
    knowledge_tags: List[str] = Field(default_factory=list)
    error_tags: List[str] = Field(default_factory=list)
    user_tags: List[str] = Field(default_factory=list)


class ProblemsResponse(BaseModel):
    """Response with problem list."""
    items: List[ProblemSummary]


class TaggingQuery(BaseModel):
    """Query parameters for tagging operations."""
    knowledge_points: List[str] = Field(default_factory=list)
    question_type: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    error_hypothesis: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
