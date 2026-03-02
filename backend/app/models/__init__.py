"""
Models package - re-exports all model classes for backward compatibility.

This module organizes models into logical submodules while maintaining
a flat import structure for existing code.
"""

from __future__ import annotations

# Pydantic types (re-exported for convenience)
from pydantic import HttpUrl

# Common types
from .common import (
    TaskStatus,
    AssetSource,
    CropRegion,
    DetectionOutput,
    OptionItem,
)

# Problem and solution models
from .problem import (
    ProblemBlock,
    SolutionBlock,
    TaggingResult,
    ArchiveRecord,
)

# Task models
from .task import (
    AssetMetadata,
    TaskCreateRequest,
    TaskRecord,
    TaskResponse,
    TaskSummary,
    TasksResponse,
)

# Pipeline models
from .pipeline import (
    PipelineResult,
)

# Library models
from .library import (
    ProblemSummary,
    ProblemsResponse,
    TaggingQuery,
)

# API models
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

# Auth models
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
    # Common
    "TaskStatus",
    "AssetSource",
    "CropRegion",
    "DetectionOutput",
    "OptionItem",
    # Problem
    "ProblemBlock",
    "SolutionBlock",
    "TaggingResult",
    "ArchiveRecord",
    # Task
    "AssetMetadata",
    "TaskCreateRequest",
    "TaskRecord",
    "TaskResponse",
    "TaskSummary",
    "TasksResponse",
    # Pipeline
    "PipelineResult",
    # Library
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
    # Auth
    "UserRole",
    "UserRecord",
    "UserPublic",
    "LoginRequest",
    "AuthTokenResponse",
    "AuthMeResponse",
]
