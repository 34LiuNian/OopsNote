"""Backend module - auto-generated docstring."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from .config.app import AgentConfig, AppSettings, AuthConfig
from .config.security import SecurityConfig
from .env import float_env


@dataclass(frozen=True)
class AppConfig:  # pylint: disable=too-many-instance-attributes
    """Application configuration container (legacy, use modular config)."""

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
    
    # Modular config instances
    app_settings: AppSettings
    agent_config: AgentConfig
    auth_config: AuthConfig
    security_config: SecurityConfig


def load_app_config() -> AppConfig:
    """Load application configuration from environment variables."""
    # Load modular configurations
    app_settings = AppSettings.from_env()
    agent_config = AgentConfig.from_env()
    auth_config = AuthConfig.from_env()
    security_config = SecurityConfig.from_env()

    return AppConfig(
        persist_tasks=app_settings.persist_tasks,
        tasks_dir=app_settings.tasks_dir,
        running_under_pytest=app_settings.running_under_pytest,
        agent_config_path=agent_config.config_path,
        openai_api_key=agent_config.openai_api_key,
        openai_base_url=agent_config.openai_base_url,
        openai_model=agent_config.openai_model,
        openai_temperature=agent_config.openai_temperature,
        openai_authorization=agent_config.openai_authorization,
        openai_auth_header_name=agent_config.openai_auth_header_name,
        require_gateway=agent_config.require_gateway,
        debug_llm_payload=agent_config.debug_llm_payload,
        debug_llm_payload_path=agent_config.debug_llm_payload_path,
        agent_base_urls=agent_config.agent_base_urls,
        auth_enabled=auth_config.enabled,
        jwt_secret=security_config.jwt_secret,
        jwt_algorithm=security_config.jwt_algorithm,
        jwt_access_token_expire_minutes=security_config.jwt_access_token_expire_minutes,
        auth_admin_username=auth_config.admin_username,
        auth_admin_password=auth_config.admin_password,
        app_settings=app_settings,
        agent_config=agent_config,
        auth_config=auth_config,
        security_config=security_config,
    )
