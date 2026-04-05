"""题目与解答相关模型。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import OptionItem
from ..config.subjects import DEFAULT_SUBJECT, VALID_SUBJECT_KEYS


class ProblemBlock(BaseModel):
    """OCR 提取后的题目块。"""

    problem_id: str
    region_id: str
    subject: str = Field(
        default=DEFAULT_SUBJECT,
        description=f"自动识别学科：{', '.join(VALID_SUBJECT_KEYS)}",
    )
    question_no: Optional[str] = Field(
        default=None,
        description="用户提供的题号（可含字母数字）；仅用于展示",
    )
    question_type: Optional[str] = Field(
        default=None, description="可选的手动题型标签"
    )
    problem_text: str
    crop_image_url: Optional[str] = Field(
        default=None, description="裁剪区域的 URL 或路径"
    )
    locked_tags: bool = Field(
        default=False, description="为 true 时跳过自动重打标（除非强制）"
    )
    media_notes: Optional[str] = None
    options: List[OptionItem] = Field(
        default_factory=list, description="可选的选择题选项"
    )
    source: Optional[str] = Field(
        default=None, description="试卷/考试来源，如 2024-XX-模拟考"
    )
    knowledge_tags: List[str] = Field(
        default_factory=list,
        description="该题手动知识体系标签",
    )
    error_tags: List[str] = Field(
        default_factory=list,
        description="该题手动错因归因标签",
    )
    user_tags: List[str] = Field(
        default_factory=list, description="该题手动自定义标签"
    )
    crop_bbox: Optional[List[float]] = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="从 CropRegion 复制的 [x, y, width, height] 归一化坐标",
    )
    ocr_has_diagram: bool = Field(
        default=False,
        description="OCR 是否判定该题需要图形重建",
    )
    diagram_detected: bool = Field(
        default=False,
        description="是否从 OCR 文本检测到可绘制图形",
    )
    diagram_kind: Optional[str] = Field(
        default=None,
        description="图形类型，如 tikz",
    )
    diagram_tikz_source: Optional[str] = Field(
        default=None,
        description="用于图形重建的 TikZ 源码",
    )
    diagram_svg: Optional[str] = Field(
        default=None,
        description="渲染后的 SVG 内容，可供前端直接预览",
    )
    diagram_render_status: Optional[str] = Field(
        default=None,
        description="渲染状态：ready/failed/skipped",
    )
    diagram_error: Optional[str] = Field(
        default=None,
        description="渲染失败原因，供人工介入",
    )
    diagram_needs_review: bool = Field(
        default=False,
        description="图形输出是否需要人工复核",
    )
    diagram_confidence: Optional[float] = Field(
        default=None,
        description="图形重建模型置信度（0-1）",
    )


class SolutionBlock(BaseModel):
    """单题解答块。"""

    problem_id: str
    answer: str
    explanation: str
    short_answer: Optional[str] = Field(
        default=None, description="摘要视图可用的简答答案（可选）"
    )


class TaggingResult(BaseModel):
    """AI Agent 生成的打标结果。"""

    # 兼容旧版持久化任务中可能存在的额外字段。
    model_config = ConfigDict(extra="ignore")

    problem_id: str
    knowledge_points: List[str]
    question_type: str
    skills: List[str]
    error_hypothesis: List[str]
    recommended_actions: List[str]


class ArchiveRecord(BaseModel):
    """题目持久化归档记录。"""

    task_id: str
    stored_problem_ids: List[str]
    timestamp: datetime
