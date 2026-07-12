"""OopsNote Core — 数据层。

独立于任何 UI 框架，CLI / REST / MCP 均可复用。
"""

from .assets import AssetStore
from .models import (
    Problem,
    SearchQuery,
    TagCreateRequest,
    TagDimension,
    TagItem,
    TagsResponse,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
)
from .search import Searcher
from .store import TaskStore
from .tags import TagStore

__all__ = [
    "AssetStore",
    "Problem",
    "Searcher",
    "SearchQuery",
    "TagCreateRequest",
    "TagDimension",
    "TagItem",
    "TagsResponse",
    "TagStore",
    "TaskCreateRequest",
    "TaskRecord",
    "TaskStatus",
    "TaskStore",
]
