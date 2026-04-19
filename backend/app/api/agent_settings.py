from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from ..auth.deps import require_admin
from ..agent_settings import DebugSettings, GatewaySettings
from ..config import load_app_config
from ..gateway import fetch_openai_models, probe_openai_gateway
from ..models import (
    AgentEnabledResponse,
    AgentEnabledUpdateRequest,
    AgentModelsResponse,
    AgentModelsUpdateRequest,
    AgentTemperatureResponse,
    AgentTemperatureUpdateRequest,
    AgentThinkingResponse,
    AgentThinkingUpdateRequest,
    DebugSettingsResponse,
    DebugSettingsUpdateRequest,
    GatewaySettingsResponse,
    GatewaySettingsUpdateRequest,
    GatewayTestRequest,
    GatewayTestResponse,
    SystemInfoResponse,
)
from .deps import get_agent_settings_service, get_backend_state, get_tasks_service

router = APIRouter(dependencies=[Depends(require_admin)])
logger = logging.getLogger(__name__)

_SENTINEL_UNCHANGED = "__UNCHANGED__"


def _service(request: Request):
    """从通用 API 依赖中解析 Agent 设置服务。"""
    return get_agent_settings_service(request)


def _mask_api_key(key: str | None) -> str | None:
    """返回脱敏后的 API Key，用于安全展示。"""
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return key[:3] + "****" + key[-4:]


# ── Agent 模型配置 ─────────────────────────────────────────────────────────


@router.get("/settings/agent-models", response_model=AgentModelsResponse)
def get_agent_models(request: Request) -> AgentModelsResponse:
    svc = _service(request)
    return AgentModelsResponse(models=svc.load_models())


@router.put("/settings/agent-models", response_model=AgentModelsResponse)
def update_agent_models(
    request: Request, payload: AgentModelsUpdateRequest
) -> AgentModelsResponse:
    """更新 Agent 模型配置。

    Args:
        request: HTTP 请求
        payload: 模型更新载荷

    Returns:
        更新后的模型配置
    """
    svc = _service(request)
    saved = svc.save_models(payload.models)
    return AgentModelsResponse(models=saved)


# ── Agent 启用开关 ──────────────────────────────────────────────────────────


@router.get("/settings/agent-enabled", response_model=AgentEnabledResponse)
def get_agent_enabled(request: Request) -> AgentEnabledResponse:
    svc = _service(request)
    return AgentEnabledResponse(enabled=svc.enabled_snapshot())


@router.put("/settings/agent-enabled", response_model=AgentEnabledResponse)
def update_agent_enabled(
    request: Request, payload: AgentEnabledUpdateRequest
) -> AgentEnabledResponse:
    svc = _service(request)
    saved = svc.save_enabled(payload.enabled)
    return AgentEnabledResponse(enabled=saved)


# ── Agent 思考模式 ──────────────────────────────────────────────────────────


@router.get("/settings/agent-thinking", response_model=AgentThinkingResponse)
def get_agent_thinking(request: Request) -> AgentThinkingResponse:
    svc = _service(request)
    return AgentThinkingResponse(thinking=svc.thinking_snapshot())


@router.put("/settings/agent-thinking", response_model=AgentThinkingResponse)
def update_agent_thinking(
    request: Request, payload: AgentThinkingUpdateRequest
) -> AgentThinkingResponse:
    svc = _service(request)
    saved = svc.save_thinking(payload.thinking)
    return AgentThinkingResponse(thinking=saved)


# ── Agent 温度参数 ──────────────────────────────────────────────────────────


@router.get("/settings/agent-temperature", response_model=AgentTemperatureResponse)
def get_agent_temperature(request: Request) -> AgentTemperatureResponse:
    svc = _service(request)
    return AgentTemperatureResponse(temperature=svc.temperature_snapshot())


@router.put("/settings/agent-temperature", response_model=AgentTemperatureResponse)
def update_agent_temperature(
    request: Request, payload: AgentTemperatureUpdateRequest
) -> AgentTemperatureResponse:
    svc = _service(request)
    saved = svc.save_temperature(payload.temperature)
    return AgentTemperatureResponse(temperature=saved)


# ── 网关设置 ────────────────────────────────────────────────────────────────


@router.get("/settings/gateway", response_model=GatewaySettingsResponse)
def get_gateway_settings(request: Request) -> GatewaySettingsResponse:
    svc = _service(request)
    gw = svc.load_gateway()
    env_config = load_app_config()
    return GatewaySettingsResponse(
        base_url=gw.base_url,
        api_key_masked=_mask_api_key(gw.api_key),
        has_api_key=bool(gw.api_key),
        default_model=gw.default_model,
        temperature=gw.temperature,
        env_base_url=env_config.openai_base_url,
        env_has_api_key=bool(env_config.openai_api_key),
        env_default_model=env_config.openai_model,
        env_temperature=env_config.openai_temperature,
    )


@router.put("/settings/gateway", response_model=GatewaySettingsResponse)
def update_gateway_settings(
    request: Request, payload: GatewaySettingsUpdateRequest
) -> GatewaySettingsResponse:
    svc = _service(request)
    current = svc.load_gateway()

    # 处理 API Key 的哨兵值
    new_api_key = current.api_key
    if payload.api_key is not None:
        if payload.api_key == _SENTINEL_UNCHANGED:
            new_api_key = current.api_key
        elif payload.api_key == "":
            new_api_key = None
        else:
            new_api_key = payload.api_key

    new_settings = GatewaySettings(
        base_url=payload.base_url if payload.base_url is not None else current.base_url,
        api_key=new_api_key,
        default_model=payload.default_model
        if payload.default_model is not None
        else current.default_model,
        temperature=payload.temperature
        if payload.temperature is not None
        else current.temperature,
    )
    saved = svc.save_gateway(new_settings)
    env_config = load_app_config()

    # 通过任务服务公开端口应用运行时配置，避免跨层访问 pipeline 内部对象。
    tasks_svc = get_tasks_service(request)
    effective_base_url = saved.base_url or env_config.openai_base_url
    effective_api_key = saved.api_key or env_config.openai_api_key
    effective_model = saved.default_model or env_config.openai_model
    effective_temp = (
        saved.temperature
        if saved.temperature is not None
        else env_config.openai_temperature
    )
    apply_stats = tasks_svc.apply_runtime_settings(
        base_url=effective_base_url,
        api_key=effective_api_key,
        model=effective_model,
        temperature=effective_temp,
    )
    logger.info(
        "Gateway runtime settings applied: updated=%s total=%s",
        apply_stats.get("clients_updated", 0),
        apply_stats.get("clients_total", 0),
    )

    return GatewaySettingsResponse(
        base_url=saved.base_url,
        api_key_masked=_mask_api_key(saved.api_key),
        has_api_key=bool(saved.api_key),
        default_model=saved.default_model,
        temperature=saved.temperature,
        env_base_url=env_config.openai_base_url,
        env_has_api_key=bool(env_config.openai_api_key),
        env_default_model=env_config.openai_model,
        env_temperature=env_config.openai_temperature,
    )


@router.post("/settings/gateway/test", response_model=GatewayTestResponse)
def test_gateway_connection(payload: GatewayTestRequest) -> GatewayTestResponse:
    """测试网关连通性并尝试拉取模型列表。"""
    try:
        reachable, status = probe_openai_gateway(payload.base_url, timeout_seconds=5.0)
        if not reachable:
            return GatewayTestResponse(
                success=False, message=f"无法连接: {status}", models_count=0
            )
        # 尝试获取模型列表
        models = fetch_openai_models(
            payload.base_url,
            payload.api_key,
            authorization=None,
            auth_header_name="Authorization",
            timeout_seconds=5.0,
        )
        return GatewayTestResponse(
            success=True,
            message=f"连接成功，共 {len(models)} 个模型可用",
            models_count=len(models),
        )
    except Exception as exc:
        return GatewayTestResponse(
            success=False, message=f"连接失败: {exc}", models_count=0
        )


# ── 调试设置 ────────────────────────────────────────────────────────────────


@router.get("/settings/debug", response_model=DebugSettingsResponse)
def get_debug_settings(request: Request) -> DebugSettingsResponse:
    svc = _service(request)
    dbg = svc.load_debug()
    return DebugSettingsResponse(
        debug_llm_payload=dbg.debug_llm_payload,
        persist_tasks=dbg.persist_tasks,
    )


@router.put("/settings/debug", response_model=DebugSettingsResponse)
def update_debug_settings(
    request: Request, payload: DebugSettingsUpdateRequest
) -> DebugSettingsResponse:
    svc = _service(request)
    current = svc.load_debug()
    new_settings = DebugSettings(
        debug_llm_payload=payload.debug_llm_payload
        if payload.debug_llm_payload is not None
        else current.debug_llm_payload,
        persist_tasks=payload.persist_tasks
        if payload.persist_tasks is not None
        else current.persist_tasks,
    )
    saved = svc.save_debug(new_settings)

    # 通过任务服务公开端口应用 debug 配置，避免跨层访问 pipeline 内部对象。
    tasks_svc = get_tasks_service(request)
    apply_stats = tasks_svc.apply_runtime_settings(
        debug_payload=saved.debug_llm_payload
    )
    logger.info(
        "Debug runtime settings applied: updated=%s total=%s",
        apply_stats.get("clients_updated", 0),
        apply_stats.get("clients_total", 0),
    )

    return DebugSettingsResponse(
        debug_llm_payload=saved.debug_llm_payload,
        persist_tasks=saved.persist_tasks,
    )


# ── 系统信息 ────────────────────────────────────────────────────────────────


@router.get("/settings/system-info", response_model=SystemInfoResponse)
def get_system_info(request: Request) -> SystemInfoResponse:
    svc = _service(request)
    env_config = load_app_config()
    gw = svc.load_gateway()

    effective_base_url = gw.base_url or env_config.openai_base_url
    effective_api_key = gw.api_key or env_config.openai_api_key

    gateway_reachable = None
    if effective_base_url:
        try:
            reachable, _status = probe_openai_gateway(
                effective_base_url, timeout_seconds=2.0
            )
            gateway_reachable = reachable
        except Exception:
            gateway_reachable = False

    storage_path = str(
        Path(__file__).resolve().parent.parent / "storage"
    )

    # 统计缓存中的模型数量
    state = get_backend_state(request)
    models_count = 0
    try:
        models_svc = getattr(state, "models", None)
        if models_svc:
            cache = getattr(models_svc, "_cache", None)
            if cache and callable(cache):
                cached = cache()
                models_count = len(cached) if cached else 0
    except Exception:
        pass

    return SystemInfoResponse(
        gateway_reachable=gateway_reachable,
        gateway_url=effective_base_url,
        storage_path=storage_path,
        env_configured=bool(effective_api_key),
        models_count=models_count,
    )
