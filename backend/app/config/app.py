"""应用配置定义。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from .env import float_env


@dataclass(frozen=True)
class AppSettings:
    """应用核心设置。"""

    persist_tasks: bool
    tasks_dir: str | None
    running_under_pytest: bool

    @classmethod
    def from_env(cls) -> "AppSettings":
        """从环境变量加载应用设置。"""
        running_under_pytest = ("pytest" in sys.modules) or (
            "PYTEST_CURRENT_TEST" in os.environ
        )
        persist_tasks = os.getenv("PERSIST_TASKS", "true").lower() == "true"
        tasks_dir = os.getenv("TASKS_DIR")

        return cls(
            persist_tasks=persist_tasks,
            tasks_dir=tasks_dir,
            running_under_pytest=running_under_pytest,
        )


@dataclass(frozen=True)
class AgentConfig:
    """LLM Agent 配置。"""

    config_path: str | None
    openai_api_key: str | None
    openai_base_url: str | None
    openai_model: str
    openai_temperature: float
    openai_authorization: str | None
    openai_auth_header_name: str
    require_gateway: bool
    debug_llm_payload: bool
    debug_llm_payload_path: str | None
    agent_base_urls: dict[str, str]

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """从环境变量加载 Agent 配置。"""
        running_under_pytest = ("pytest" in sys.modules) or (
            "PYTEST_CURRENT_TEST" in os.environ
        )

        config_path = os.getenv("AGENT_CONFIG_PATH") or os.getenv("AI_AGENT_CONFIG")
        openai_api_key = None if running_under_pytest else os.getenv("OPENAI_API_KEY")
        openai_base_url = os.getenv("OPENAI_BASE_URL")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        openai_temperature = float_env("OPENAI_TEMPERATURE", 0.2)
        openai_authorization = os.getenv("OPENAI_AUTHORIZATION") or os.getenv(
            "OPENAI_AUTH_HEADER_VALUE"
        )
        openai_auth_header_name = os.getenv("OPENAI_AUTH_HEADER_NAME") or "Authorization"
        require_gateway = os.getenv("AI_REQUIRE_GATEWAY", "false").lower() == "true"
        debug_llm_payload = os.getenv("AI_DEBUG_LLM_PAYLOAD", "false").lower() == "true"
        debug_llm_payload_path = os.getenv("AI_DEBUG_LLM_PAYLOAD_PATH")

        agent_base_urls: dict[str, str] = {}
        for name in ["SOLVER", "TAGGER", "OCR"]:
            value = os.getenv(f"AGENT_{name}_BASE_URL")
            if value:
                agent_base_urls[name] = value

        return cls(
            config_path=config_path,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            openai_model=openai_model,
            openai_temperature=openai_temperature,
            openai_authorization=openai_authorization,
            openai_auth_header_name=openai_auth_header_name,
            require_gateway=require_gateway,
            debug_llm_payload=debug_llm_payload,
            debug_llm_payload_path=debug_llm_payload_path,
            agent_base_urls=agent_base_urls,
        )


@dataclass(frozen=True)
class AuthConfig:
    """认证配置。"""

    enabled: bool
    admin_username: str
    admin_password: str

    @classmethod
    def from_env(cls) -> "AuthConfig":
        """从环境变量加载认证配置。"""
        return cls(
            enabled=os.getenv("AUTH_ENABLED", "true").lower() == "true",
            admin_username=os.getenv("AUTH_ADMIN_USERNAME", "admin"),
            admin_password=os.getenv("AUTH_ADMIN_PASSWORD", "admin123456"),
        )
