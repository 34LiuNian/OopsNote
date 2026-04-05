"""流水线处理相关模型。"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel

from .common import DetectionOutput
from .problem import ProblemBlock, SolutionBlock, TaggingResult, ArchiveRecord


class PipelineResult(BaseModel):
    """AI 流水线执行结果。"""

    detection: DetectionOutput
    problems: List[ProblemBlock]
    solutions: List[SolutionBlock]
    tags: List[TaggingResult]
    archive: ArchiveRecord
