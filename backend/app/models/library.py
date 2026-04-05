"""题库与查询相关模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from .common import OptionItem


class ProblemSummary(BaseModel):
    """跨任务聚合后的单题扁平视图，用于题库/列表 API。"""

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
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        description="任务创建时间戳（继承自所属任务）",
    )


class ProblemsResponse(BaseModel):
    """题目列表响应。"""

    items: List[ProblemSummary]


class TaggingQuery(BaseModel):
    """打标相关查询参数。"""

    knowledge_points: List[str] = Field(default_factory=list)
    question_type: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    error_hypothesis: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
