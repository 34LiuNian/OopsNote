from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .openai_client import OpenAIClient
from .stub import StubAIClient

logger = logging.getLogger(__name__)


def _debug_llm_enabled() -> bool:
    return os.getenv("AI_DEBUG_LLM", "false").lower() == "true"


def _debug_payload_enabled() -> bool:
    return os.getenv("AI_DEBUG_LLM_PAYLOAD", "false").lower() == "true"


def _debug_payload_path() -> str | None:
    return os.getenv("AI_DEBUG_LLM_PAYLOAD_PATH")


@dataclass(frozen=True)
class AgentClientConfig:
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class AgentConfigBundle:
    """从 TOML 加载并解析后的运行时配置。"""

    default: AgentClientConfig | None = None
    agents: dict[str, AgentClientConfig] | None = None


def _float_env(value: str | None, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def load_agent_client_config(agent_name: str) -> AgentClientConfig | None:
    """从环境变量加载单个 Agent 配置。

        环境变量命名：
        `AGENT_<NAME>_PROVIDER`: `openai | stub`
            `AGENT_<NAME>_API_KEY`
            `AGENT_<NAME>_BASE_URL`（仅 openai）
            `AGENT_<NAME>_MODEL`
            `AGENT_<NAME>_TEMPERATURE`

    若 `PROVIDER` 缺失，则返回 `None`。
    """

    prefix = f"AGENT_{agent_name.upper()}_"
    provider = os.getenv(prefix + "PROVIDER")
    if not provider:
        return None

    return AgentClientConfig(
        provider=provider.lower().strip(),
        api_key=os.getenv(prefix + "API_KEY"),
        base_url=os.getenv(prefix + "BASE_URL"),
        model=os.getenv(prefix + "MODEL"),
        temperature=_float_env(os.getenv(prefix + "TEMPERATURE")),
    )


def load_agent_config_bundle(path: str | os.PathLike[str] | None) -> AgentConfigBundle:
    """从 TOML 文件加载 Agent 配置。

    TOML 结构示例：

        [default]
        provider = "openai"|"stub"
        api_key = "env:OPENAI_API_KEY"  # 或字面量
        base_url = "https://.../v1"     # 仅 openai
        model = "gpt-4o-mini"
        temperature = 0.2

        [agents.SOLVER]
        provider = "openai"
        ...

    字段支持 `env:VAR_NAME` 形式的环境变量引用。
    """

    if not path:
        return AgentConfigBundle(default=None, agents=None)

    file_path = Path(path)
    if not file_path.exists():
        return AgentConfigBundle(default=None, agents=None)

    import tomllib

    data = tomllib.loads(file_path.read_text(encoding="utf-8"))

    default_cfg = (
        _parse_cfg(data.get("default"))
        if isinstance(data.get("default"), dict)
        else None
    )

    agents_raw = data.get("agents")
    agents_cfg: dict[str, AgentClientConfig] = {}
    if isinstance(agents_raw, dict):
        for name, cfg in agents_raw.items():
            if isinstance(cfg, dict):
                parsed = _parse_cfg(cfg)
                if parsed is not None:
                    agents_cfg[str(name).upper()] = parsed

    return AgentConfigBundle(default=default_cfg, agents=agents_cfg or None)


def _parse_cfg(cfg: dict[str, Any] | None) -> AgentClientConfig | None:
    if not cfg:
        return None
    provider = str(cfg.get("provider", "")).strip().lower()
    if not provider:
        return None

    def _resolve(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        if text.startswith("env:"):
            return os.getenv(text[4:])
        return text

    temp = cfg.get("temperature")
    temperature = None
    if temp is not None:
        try:
            temperature = float(temp)
        except Exception:
            temperature = None

    return AgentClientConfig(
        provider=provider,
        api_key=_resolve(cfg.get("api_key")),
        base_url=_resolve(cfg.get("base_url")),
        model=_resolve(cfg.get("model")),
        temperature=temperature,
    )


def build_client_from_config(config: AgentClientConfig):
    provider = config.provider
    if provider == "stub":
        return StubAIClient()

    if provider == "openai":
        if not config.api_key:
            raise RuntimeError("openai provider requires API_KEY")
        return OpenAIClient(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model or "gpt-4o-mini",
            temperature=config.temperature if config.temperature is not None else 0.2,
            debug_payload=_debug_payload_enabled(),
            debug_payload_path=_debug_payload_path(),
        )

    raise RuntimeError(f"Unknown provider: {provider}")


def build_client_for_agent(
    agent_name: str, fallback_client, bundle: AgentConfigBundle | None = None
):
    """为指定 Agent 解析客户端实现。

        优先级：
            1) 环境变量 `AGENT_<NAME>_*`
            2) `bundle.agents[AGENT]`
            3) `bundle.default`
            4) `fallback_client`
    """

    name = agent_name.upper()

    env_cfg = load_agent_client_config(name)
    if env_cfg is not None:
        if _debug_llm_enabled():
            logger.info(
                "Agent client=%s source=env provider=%s model=%s base_url=%s",
                name,
                env_cfg.provider,
                env_cfg.model,
                env_cfg.base_url,
            )
        return build_client_from_config(env_cfg)

    if bundle and bundle.agents and name in bundle.agents:
        if _debug_llm_enabled():
            cfg = bundle.agents[name]
            logger.info(
                "Agent client=%s source=toml.agents provider=%s model=%s base_url=%s",
                name,
                cfg.provider,
                cfg.model,
                cfg.base_url,
            )
        return build_client_from_config(bundle.agents[name])

    if bundle and bundle.default is not None:
        if _debug_llm_enabled():
            cfg = bundle.default
            logger.info(
                "Agent client=%s source=toml.default provider=%s model=%s base_url=%s",
                name,
                cfg.provider,
                cfg.model,
                cfg.base_url,
            )
        return build_client_from_config(bundle.default)

    if _debug_llm_enabled():
        logger.info("Agent client=%s source=fallback", name)
    return fallback_client
