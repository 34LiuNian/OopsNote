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


@dataclass(frozen=True)
class AgentClientConfig:
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class AgentConfigBundle:
    """Resolved runtime config loaded from a TOML file."""

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
    """Load per-agent config from env.

    Env naming:
    AGENT_<NAME>_PROVIDER: openai | stub
      AGENT_<NAME>_API_KEY
      AGENT_<NAME>_BASE_URL   (openai only)
      AGENT_<NAME>_MODEL
      AGENT_<NAME>_TEMPERATURE

    If PROVIDER is missing, returns None.
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
    """Load agent config from TOML.

    TOML structure:

      [default]
    provider = "openai"|"stub"
      api_key = "env:OPENAI_API_KEY"  # or literal
      base_url = "https://.../v1"     # openai only
      model = "gpt-4o-mini"
      temperature = 0.2

    [agents.SOLVER]
      provider = "openai"
      ...

    Values can use env indirection: "env:VAR_NAME".
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
        )

    if provider == "gemini":
        raise RuntimeError(
            "gemini provider has been removed. Use provider=openai with an OpenAI-compatible gateway (BASE_URL)."
        )

    raise RuntimeError(f"Unknown provider: {provider}")


def build_client_for_agent(
    agent_name: str, fallback_client, bundle: AgentConfigBundle | None = None
):
    """Resolve client for agent.

    Priority:
            1) env AGENT_<NAME>_*
            2) bundle.agents[AGENT]
            3) bundle.default
      4) fallback_client
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
