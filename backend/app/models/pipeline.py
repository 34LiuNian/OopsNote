"""
Pipeline and processing models.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel

from .common import DetectionOutput
from .problem import ProblemBlock, SolutionBlock, TaggingResult, ArchiveRecord


class PipelineResult(BaseModel):
    """Result from AI pipeline execution."""
    detection: DetectionOutput
    problems: List[ProblemBlock]
    solutions: List[SolutionBlock]
    tags: List[TaggingResult]
    archive: ArchiveRecord
