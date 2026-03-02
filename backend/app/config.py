"""Backend module - auto-generated docstring."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from .env import float_env


@dataclass(frozen=True)
class AppConfig:  # pylint: disable=too-many-instance-attributes
    """Application configuration container."""

    persist_tasks: bool
    tasks_dir: str | None
    running_under_pytest: bool
    agent_config_path: str | None
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
    auth_enabled: bool
    jwt_secret: str
    jwt_algorithm: str
    jwt_access_token_expire_minutes: int
    auth_admin_username: str
    auth_admin_password: str


def load_app_config() -> AppConfig:
    """Load application configuration from environment variables."""
    running_under_pytest = ("pytest" in sys.modules) or (
        "PYTEST_CURRENT_TEST" in os.environ
    )
    persist_tasks = os.getenv("PERSIST_TASKS", "true").lower() == "true"
    tasks_dir = os.getenv("TASKS_DIR")
    agent_config_path = os.getenv("AGENT_CONFIG_PATH") or os.getenv("AI_AGENT_CONFIG")

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

    auth_enabled = os.getenv("AUTH_ENABLED", "true").lower() == "true"
    jwt_secret = os.getenv("JWT_SECRET", "oopsnote-dev-secret-change-me")
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_access_token_expire_minutes = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "120")
    )
    auth_admin_username = os.getenv("AUTH_ADMIN_USERNAME", "admin")
    auth_admin_password = os.getenv("AUTH_ADMIN_PASSWORD", "admin123456")

    return AppConfig(
        persist_tasks=persist_tasks,
        tasks_dir=tasks_dir,
        running_under_pytest=running_under_pytest,
        agent_config_path=agent_config_path,
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
        auth_enabled=auth_enabled,
        jwt_secret=jwt_secret,
        jwt_algorithm=jwt_algorithm,
        jwt_access_token_expire_minutes=jwt_access_token_expire_minutes,
        auth_admin_username=auth_admin_username,
        auth_admin_password=auth_admin_password,
    )
