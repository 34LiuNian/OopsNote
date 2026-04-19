"""Agent 设置管理：按 Agent 维度管理模型、开关、思考模式、温度、网关与调试配置。

本模块提供 Agent 级别配置的持久化存储，主要包括：
- 各 Agent 的模型选择
- 各 Agent 的启用/禁用开关
- 各 Agent 的思考模式开关
- 各 Agent 的温度覆盖
- 网关连接参数（base_url、api_key、默认模型、temperature）
- 调试开关（LLM 载荷日志、任务持久化）
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


_AGENT_SETTINGS_FILENAME = "agent_settings.json"
_AGENT_SETTINGS_SHARED_LOCK = threading.Lock()
_AGENT_SETTINGS_SECTIONS = ("models", "enabled", "thinking", "temperature")
_LEGACY_AGENT_SETTINGS_FILES = {
    "models": "agent_models.json",
    "enabled": "agent_enabled.json",
    "thinking": "agent_thinking.json",
    "temperature": "agent_temperature.json",
}


def _normalize_models(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(k).upper(): str(v)
        for k, v in raw.items()
        if (k is not None) and (v is not None)
    }


def _normalize_bool_map(raw: Any) -> Dict[str, bool]:
    normalized: Dict[str, bool] = {}
    if not isinstance(raw, dict):
        return normalized
    for k, v in raw.items():
        if k is None:
            continue
        normalized[str(k).upper()] = bool(v)
    return normalized


def _normalize_float_map(raw: Any) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    if not isinstance(raw, dict):
        return normalized
    for k, v in raw.items():
        if k is None:
            continue
        try:
            normalized[str(k).upper()] = float(v)
        except (ValueError, TypeError):
            continue
    return normalized


def _read_json_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_agent_bundle(raw: Any) -> Dict[str, Dict[str, Any]]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "models": _normalize_models(data.get("models")),
        "enabled": _normalize_bool_map(data.get("enabled")),
        "thinking": _normalize_bool_map(data.get("thinking")),
        "temperature": _normalize_float_map(data.get("temperature")),
    }


def _read_legacy_agent_bundle(base_dir: Path) -> Dict[str, Dict[str, Any]]:
    legacy = _normalize_agent_bundle({})
    for section in _AGENT_SETTINGS_SECTIONS:
        filename = _LEGACY_AGENT_SETTINGS_FILES[section]
        data = _read_json_dict(base_dir / filename)
        if section == "models":
            legacy[section] = _normalize_models(data.get(section))
        elif section in {"enabled", "thinking"}:
            legacy[section] = _normalize_bool_map(data.get(section))
        else:
            legacy[section] = _normalize_float_map(data.get(section))
    return legacy


def _load_agent_bundle(path: Path) -> Dict[str, Dict[str, Any]]:
    exists = path.exists()
    bundle = _normalize_agent_bundle(_read_json_dict(path))
    if exists:
        return bundle

    legacy = _read_legacy_agent_bundle(path.parent)
    for section in _AGENT_SETTINGS_SECTIONS:
        if legacy.get(section):
            bundle[section] = legacy[section]
    return bundle


def _save_agent_bundle(path: Path, bundle: Dict[str, Dict[str, Any]]) -> None:
    payload = _normalize_agent_bundle(bundle)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class AgentModelSettings:
    """Agent 模型设置的不可变容器。

    Attributes:
        models: Agent 名称（大写）到模型标识的映射
    """

    models: Dict[str, str]


class AgentModelSettingsStore:
    """将各 Agent 的模型选择（非敏感）持久化到磁盘。

    该存储用于支持 UI 侧切换模型，而无需改动 API Key。
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / _AGENT_SETTINGS_FILENAME)
        self._lock = _AGENT_SETTINGS_SHARED_LOCK

    def load(self) -> AgentModelSettings:
        """从磁盘加载 Agent 模型设置。

        Returns:
            当前模型映射对应的 AgentModelSettings
        """
        with self._lock:
            bundle = _load_agent_bundle(self.path)
            return AgentModelSettings(models=bundle["models"])

    def save(self, settings: AgentModelSettings) -> AgentModelSettings:
        """将 Agent 模型设置保存到磁盘。

        Args:
            settings: 待持久化的设置

        Returns:
            已保存的设置
        """
        with self._lock:
            bundle = _load_agent_bundle(self.path)
            bundle["models"] = _normalize_models(settings.models)
            _save_agent_bundle(self.path, bundle)
            return AgentModelSettings(models=bundle["models"])

    def set_model(self, agent_name: str, model: str) -> AgentModelSettings:
        """为指定 Agent 设置模型。

        Args:
            agent_name: Agent 标识（不区分大小写）
            model: 使用的模型名

        Returns:
            保存后的最新设置
        """
        current = self.load()
        next_models = dict(current.models)
        next_models[agent_name.upper()] = model
        return self.save(AgentModelSettings(models=next_models))


@dataclass(frozen=True)
class AgentEnableSettings:
    """Agent 启用/禁用设置的不可变容器。

    Attributes:
        enabled: Agent 名称（大写）到启用状态的映射
    """

    enabled: Dict[str, bool]


class AgentEnableSettingsStore:
    """将各 Agent 的启用开关（非敏感）持久化到磁盘。

    用于控制某个 Agent 是否执行、是否允许调用模型。
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / _AGENT_SETTINGS_FILENAME)
        self._lock = _AGENT_SETTINGS_SHARED_LOCK

    def load(self) -> AgentEnableSettings:
        """从磁盘加载 Agent 启用设置。

        Returns:
            当前启用状态对应的 AgentEnableSettings
        """
        with self._lock:
            bundle = _load_agent_bundle(self.path)
            return AgentEnableSettings(enabled=bundle["enabled"])

    def save(self, settings: AgentEnableSettings) -> AgentEnableSettings:
        """将 Agent 启用设置保存到磁盘。

        Args:
            settings: 待持久化的设置

        Returns:
            已保存的设置
        """
        with self._lock:
            bundle = _load_agent_bundle(self.path)
            bundle["enabled"] = _normalize_bool_map(settings.enabled)
            _save_agent_bundle(self.path, bundle)
            return AgentEnableSettings(enabled=bundle["enabled"])


@dataclass(frozen=True)
class AgentThinkingSettings:
    """Agent 思考模式设置的不可变容器。

    Attributes:
        thinking: Agent 名称（大写）到思考模式状态的映射
    """

    thinking: Dict[str, bool]


class AgentThinkingSettingsStore:
    """将各 Agent 的思考模式开关（非敏感）持久化到磁盘。

    其语义刻意保持轻量：主要影响提示词风格。
    若供应商不支持，可忽略该设置。
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / _AGENT_SETTINGS_FILENAME)
        self._lock = _AGENT_SETTINGS_SHARED_LOCK

    def load(self) -> AgentThinkingSettings:
        """从磁盘加载 Agent 思考模式设置。

        Returns:
            当前思考模式状态对应的 AgentThinkingSettings
        """
        with self._lock:
            bundle = _load_agent_bundle(self.path)
            return AgentThinkingSettings(thinking=bundle["thinking"])

    def save(self, settings: AgentThinkingSettings) -> AgentThinkingSettings:
        """将 Agent 思考模式设置保存到磁盘。

        Args:
            settings: 待持久化的设置

        Returns:
            已保存的设置
        """
        with self._lock:
            bundle = _load_agent_bundle(self.path)
            bundle["thinking"] = _normalize_bool_map(settings.thinking)
            _save_agent_bundle(self.path, bundle)
            return AgentThinkingSettings(thinking=bundle["thinking"])


# ---------------------------------------------------------------------------
# Agent 温度设置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentTemperatureSettings:
    """各 Agent 温度覆盖设置的不可变容器。

    Attributes:
        temperature: Agent 名称（大写）到温度值的映射
    """

    temperature: Dict[str, float]


class AgentTemperatureSettingsStore:
    """将各 Agent 的温度覆盖配置持久化到磁盘。"""

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / _AGENT_SETTINGS_FILENAME)
        self._lock = _AGENT_SETTINGS_SHARED_LOCK

    def load(self) -> AgentTemperatureSettings:
        with self._lock:
            bundle = _load_agent_bundle(self.path)
            return AgentTemperatureSettings(temperature=bundle["temperature"])

    def save(self, settings: AgentTemperatureSettings) -> AgentTemperatureSettings:
        with self._lock:
            bundle = _load_agent_bundle(self.path)
            bundle["temperature"] = _normalize_float_map(settings.temperature)
            _save_agent_bundle(self.path, bundle)
            return AgentTemperatureSettings(temperature=bundle["temperature"])


# ---------------------------------------------------------------------------
# 网关设置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GatewaySettings:
    """网关连接参数的不可变容器。

    当这些值存在时，会覆盖对应的环境变量。

    Attributes:
        base_url: 兼容 OpenAI 的网关地址
        api_key: API Key（本地文件明文存储）
        default_model: 默认兜底模型名
        temperature: 默认温度
    """

    base_url: Optional[str] = None
    api_key: Optional[str] = None
    default_model: Optional[str] = None
    temperature: Optional[float] = None


class GatewaySettingsStore:
    """将网关连接参数持久化到磁盘。

    此处配置优先级高于环境变量。
    """

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "gateway.json")
        self._lock = threading.Lock()

    def load(self) -> GatewaySettings:
        with self._lock:
            if not self.path.exists():
                return GatewaySettings()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return GatewaySettings()
            temp = data.get("temperature")
            if temp is not None:
                try:
                    temp = float(temp)
                except (ValueError, TypeError):
                    temp = None
            return GatewaySettings(
                base_url=data.get("base_url") or None,
                api_key=data.get("api_key") or None,
                default_model=data.get("default_model") or None,
                temperature=temp,
            )

    def save(self, settings: GatewaySettings) -> GatewaySettings:
        with self._lock:
            payload: dict = {}
            if settings.base_url is not None:
                payload["base_url"] = settings.base_url
            if settings.api_key is not None:
                payload["api_key"] = settings.api_key
            if settings.default_model is not None:
                payload["default_model"] = settings.default_model
            if settings.temperature is not None:
                payload["temperature"] = settings.temperature
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings


# ---------------------------------------------------------------------------
# 调试设置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DebugSettings:
    """调试开关的不可变容器。

    Attributes:
        debug_llm_payload: 是否记录 LLM 请求/响应载荷
        persist_tasks: 是否将任务持久化到磁盘
    """

    debug_llm_payload: bool = False
    persist_tasks: bool = True


class DebugSettingsStore:
    """将调试开关持久化到磁盘。"""

    def __init__(self, path: Path | None = None) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.path = path or (base / "debug.json")
        self._lock = threading.Lock()

    def load(self) -> DebugSettings:
        with self._lock:
            if not self.path.exists():
                return DebugSettings()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return DebugSettings()
            return DebugSettings(
                debug_llm_payload=bool(data.get("debug_llm_payload", False)),
                persist_tasks=bool(data.get("persist_tasks", True)),
            )

    def save(self, settings: DebugSettings) -> DebugSettings:
        with self._lock:
            payload = {
                "debug_llm_payload": settings.debug_llm_payload,
                "persist_tasks": settings.persist_tasks,
            }
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return settings
