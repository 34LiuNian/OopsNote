"""OopsNote Core — 数据层。

独立于任何 UI 框架，CLI / REST / MCP 均可复用。
"""

from .assets import AssetStore
from .models import (
    BatchCropRect,
    BatchSegment,
    BatchSegmentPart,
    BatchSessionRecord,
    BatchSessionUpdateRequest,
    ContentFormat,
    Problem,
    QuestionType,
    RunStatus,
    SearchQuery,
    StageRun,
    StageStatus,
    TagCreateRequest,
    TagDimension,
    TagItem,
    TagsResponse,
    TaskCreateRequest,
    TaskRecord,
    TaskRun,
    TaskStage,
    TaskStatus,
)
from .search import Searcher
from .store import BatchSessionStore, RunStore, TaskStore
from .tags import TagStore

__all__ = [
    "AssetStore",
    "BatchCropRect",
    "BatchSegment",
    "BatchSegmentPart",
    "BatchSessionRecord",
    "BatchSessionStore",
    "BatchSessionUpdateRequest",
    "ContentFormat",
    "Problem",
    "QuestionType",
    "RunStatus",
    "RunStore",
    "Searcher",
    "SearchQuery",
    "StageRun",
    "StageStatus",
    "TagCreateRequest",
    "TagDimension",
    "TagItem",
    "TagsResponse",
    "TagStore",
    "TaskCreateRequest",
    "TaskRecord",
    "TaskRun",
    "TaskStage",
    "TaskStatus",
    "TaskStore",
]
