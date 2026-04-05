"""模型包统一导出入口（兼容旧导入路径）。

本模块将模型按逻辑拆分到子模块，同时保持扁平导入体验，
便于现有代码平滑迁移。
"""

from __future__ import annotations

# Pydantic 类型（便捷重导出）
from pydantic import HttpUrl

# 通用类型
from .common import (
    TaskStatus,
    AssetSource,
    CropRegion,
    DetectionOutput,
    OptionItem,
)

# 题目与解答模型
from .problem import (
    ProblemBlock,
    SolutionBlock,
    TaggingResult,
    ArchiveRecord,
)

# 任务模型
from .task import (
    AssetMetadata,
    TaskCreateRequest,
    TaskRecord,
    TaskResponse,
    TaskSummary,
    TasksResponse,
)

# 流水线模型
from .pipeline import (
    PipelineResult,
)

# 题库模型
from .library import (
    ProblemSummary,
    ProblemsResponse,
    TaggingQuery,
)

# API 模型
from .api import (
    UploadRequest,
    LatexCompileRequest,
    PaperItemRequest,
    PaperCompileRequest,
    ChemfigRenderRequest,
    OverrideProblemRequest,
    RetagRequest,
    ModelSummary,
    ModelsResponse,
    AgentModelsResponse,
    AgentModelsUpdateRequest,
    AgentEnabledResponse,
    AgentEnabledUpdateRequest,
    AgentThinkingResponse,
    AgentThinkingUpdateRequest,
    AgentTemperatureResponse,
    AgentTemperatureUpdateRequest,
    GatewaySettingsResponse,
    GatewaySettingsUpdateRequest,
    GatewayTestRequest,
    GatewayTestResponse,
    DebugSettingsResponse,
    DebugSettingsUpdateRequest,
    SystemInfoResponse,
)

# 认证模型
from .auth import (
    UserRole,
    UserRecord,
    UserPublic,
    LoginRequest,
    AuthTokenResponse,
    AuthMeResponse,
)

__all__ = [
    # Pydantic
    "HttpUrl",
    # 通用
    "TaskStatus",
    "AssetSource",
    "CropRegion",
    "DetectionOutput",
    "OptionItem",
    # 题目
    "ProblemBlock",
    "SolutionBlock",
    "TaggingResult",
    "ArchiveRecord",
    # 任务
    "AssetMetadata",
    "TaskCreateRequest",
    "TaskRecord",
    "TaskResponse",
    "TaskSummary",
    "TasksResponse",
    # 流水线
    "PipelineResult",
    # 题库
    "ProblemSummary",
    "ProblemsResponse",
    "TaggingQuery",
    # API
    "UploadRequest",
    "LatexCompileRequest",
    "PaperItemRequest",
    "PaperCompileRequest",
    "ChemfigRenderRequest",
    "OverrideProblemRequest",
    "RetagRequest",
    "ModelSummary",
    "ModelsResponse",
    "AgentModelsResponse",
    "AgentModelsUpdateRequest",
    "AgentEnabledResponse",
    "AgentEnabledUpdateRequest",
    "AgentThinkingResponse",
    "AgentThinkingUpdateRequest",
    "AgentTemperatureResponse",
    "AgentTemperatureUpdateRequest",
    "GatewaySettingsResponse",
    "GatewaySettingsUpdateRequest",
    "GatewayTestRequest",
    "GatewayTestResponse",
    "DebugSettingsResponse",
    "DebugSettingsUpdateRequest",
    "SystemInfoResponse",
    # 认证
    "UserRole",
    "UserRecord",
    "UserPublic",
    "LoginRequest",
    "AuthTokenResponse",
    "AuthMeResponse",
]
