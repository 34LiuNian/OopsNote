"""各类端点的 API 请求/响应模型。"""

from __future__ import annotations

from typing import List, Optional, Dict

from pydantic import BaseModel, Field, HttpUrl, model_validator

from .common import OptionItem
from ..config.subjects import DEFAULT_SUBJECT


class UploadRequest(BaseModel):
    """上传图片处理请求。"""

    image_url: Optional[HttpUrl] = None
    image_base64: Optional[str] = Field(
        default=None,
        description="Base64 编码图片（可带可不带 data URI 前缀）",
    )
    filename: Optional[str] = None
    mime_type: Optional[str] = Field(default="image/png")
    subject: str = Field(default=DEFAULT_SUBJECT)
    grade: Optional[str] = None
    notes: Optional[str] = None
    question_no: Optional[str] = None
    question_type: Optional[str] = None
    mock_problem_count: Optional[int] = Field(default=None, ge=1, le=8)
    difficulty: Optional[str] = None
    source: Optional[str] = None
    options: List[OptionItem] = Field(default_factory=list)
    knowledge_tags: List[str] = Field(default_factory=list)
    error_tags: List[str] = Field(default_factory=list)
    user_tags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_source(self) -> "UploadRequest":
        if not self.image_url and not self.image_base64:
            raise ValueError("Upload requires either image_url or image_base64")
        return self


class LatexCompileRequest(BaseModel):
    """LaTeX 编译请求。"""

    content: str = Field(description="LaTeX 文档主体内容")
    title: Optional[str] = Field(default="LaTeX 测试", description="文档标题")
    author: Optional[str] = Field(default="OopsNote", description="文档作者")


class PaperItemRequest(BaseModel):
    """组卷请求中的单题条目。"""

    task_id: str
    problem_id: str


class PaperCompileRequest(BaseModel):
    """多题组卷编译请求。"""

    items: List[PaperItemRequest]
    title: Optional[str] = Field(default="试卷", description="试卷标题")
    show_answers: bool = Field(
        default=False, description="是否在试卷中展示答案"
    )


class ChemfigRenderRequest(BaseModel):
    """chemfig 结构渲染请求。"""

    content: str = Field(description="Chemfig 内容（可含或不含 \\chemfig{...}）")
    inline: bool = Field(default=False, description="是否按行内公式渲染")


class OverrideProblemRequest(BaseModel):
    """题目信息覆盖请求。"""

    question_no: Optional[str] = None
    problem_text: Optional[str] = None
    options: Optional[List[OptionItem]] = None
    source: Optional[str] = None
    knowledge_tags: Optional[List[str]] = None
    error_tags: Optional[List[str]] = None
    user_tags: Optional[List[str]] = None
    knowledge_points: Optional[List[str]] = None
    question_type: Optional[str] = None
    skills: Optional[List[str]] = None
    error_hypothesis: Optional[List[str]] = None
    recommended_actions: Optional[List[str]] = None
    locked_tags: Optional[bool] = None
    crop_bbox: Optional[List[float]] = Field(default=None, min_length=4, max_length=4)
    crop_image_url: Optional[str] = None
    diagram_detected: Optional[bool] = None
    diagram_kind: Optional[str] = None
    diagram_tikz_source: Optional[str] = None
    diagram_svg: Optional[str] = None
    diagram_render_status: Optional[str] = None
    diagram_error: Optional[str] = None
    diagram_needs_review: Optional[bool] = None
    retag: bool = Field(
        default=False, description="若为 true，覆盖后重新执行打标"
    )


class RetagRequest(BaseModel):
    """单题重打标请求。"""

    model: Optional[str] = Field(
        default=None, description="可选：用于打标的模型覆盖"
    )
    force: bool = Field(default=False, description="忽略 locked_tags 并强制重打标")


class ModelSummary(BaseModel):
    """可用模型摘要。"""

    id: str
    provider: Optional[str] = None
    provider_type: Optional[str] = None


class ModelsResponse(BaseModel):
    """可用模型列表响应。"""

    items: List[ModelSummary]


class AgentModelsResponse(BaseModel):
    """Agent 模型配置响应。"""

    models: Dict[str, str]


class AgentModelsUpdateRequest(BaseModel):
    """更新 Agent 模型配置请求。"""

    models: Dict[str, str]


class AgentEnabledResponse(BaseModel):
    """Agent 启用状态响应。"""

    enabled: Dict[str, bool]


class AgentEnabledUpdateRequest(BaseModel):
    """更新 Agent 启用状态请求。"""

    enabled: Dict[str, bool]


class AgentThinkingResponse(BaseModel):
    """Agent 思考模式状态响应。"""

    thinking: Dict[str, bool]


class AgentThinkingUpdateRequest(BaseModel):
    """更新 Agent 思考模式状态请求。"""

    thinking: Dict[str, bool]


# ---------------------------------------------------------------------------
# Agent 温度配置
# ---------------------------------------------------------------------------


class AgentTemperatureResponse(BaseModel):
    """Agent 温度覆盖配置响应。"""

    temperature: Dict[str, float]


class AgentTemperatureUpdateRequest(BaseModel):
    """更新 Agent 温度覆盖配置请求。"""

    temperature: Dict[str, float]


# ---------------------------------------------------------------------------
# 网关设置
# ---------------------------------------------------------------------------


class GatewaySettingsResponse(BaseModel):
    """网关连接设置响应（API Key 已脱敏）。"""

    base_url: Optional[str] = None
    api_key_masked: Optional[str] = None
    has_api_key: bool = False
    default_model: Optional[str] = None
    temperature: Optional[float] = None
    env_base_url: Optional[str] = None
    env_has_api_key: bool = False
    env_default_model: Optional[str] = None
    env_temperature: Optional[float] = None


class GatewaySettingsUpdateRequest(BaseModel):
    """更新网关连接设置请求。

    传 ``api_key = "__UNCHANGED__"`` 表示保持原值。
    传 ``api_key = ""`` 表示清空。
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    temperature: Optional[float] = None


class GatewayTestRequest(BaseModel):
    """网关连通性测试请求。"""

    base_url: str
    api_key: Optional[str] = None


class GatewayTestResponse(BaseModel):
    """网关连通性测试响应。"""

    success: bool
    message: str
    models_count: int = 0


# ---------------------------------------------------------------------------
# 调试设置
# ---------------------------------------------------------------------------


class DebugSettingsResponse(BaseModel):
    """调试开关响应。"""

    debug_llm_payload: bool = False
    persist_tasks: bool = True


class DebugSettingsUpdateRequest(BaseModel):
    """更新调试开关请求。"""

    debug_llm_payload: Optional[bool] = None
    persist_tasks: Optional[bool] = None


# ---------------------------------------------------------------------------
# 系统信息
# ---------------------------------------------------------------------------


class SystemInfoResponse(BaseModel):
    """只读系统信息。"""

    gateway_reachable: Optional[bool] = None
    gateway_url: Optional[str] = None
    storage_path: str = ""
    env_configured: bool = False
    models_count: int = 0
