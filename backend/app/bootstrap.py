from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .clients import load_agent_config_bundle
from .config import AppConfig, load_app_config
from .gateway import fetch_openai_models, guess_openai_gateway_config
from .http_logging import configure_app_logging, request_logging_middleware
from .startup_hooks import check_ai_gateway, log_llm_payload_startup
from .repository import ArchiveStore
from .storage import LocalAssetStore
from .app_state import BackendState
from .api.health import router as health_router
from .api.tags import router as tags_router
from .api.agent_settings import router as agent_settings_router
from .api.tasks import router as tasks_router
from .api.problems import router as problems_router
from .api.models import router as models_router
from .api.latex import router as latex_router
from .api.papers import router as papers_router
from .services.models_service import ModelsService
from .services.tasks_service import TasksService
from .builders import (
    build_agent_settings_service,
    build_ai_client,
    build_pipeline,
    build_repository,
    build_tasks_service,
)

logger = logging.getLogger(__name__)
_MODELS_CACHE: list[dict[str, object]] | None = None
_AGENT_CONFIG_BUNDLE = None
_APP_CONFIG: AppConfig | None = None


def create_app() -> FastAPI:
    configure_app_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks_service.ensure_workers_started()
        log_llm_payload_startup(config)
        try:
            models_service.prefetch_cache()
        except Exception:
            pass
        check_ai_gateway(ai_gateway_status, config=config)
        yield

    app = FastAPI(title="AI Mistake Organizer Backend", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.middleware("http")(request_logging_middleware)

    state, models_service, tasks_service, ai_gateway_status, config = _build_state()
    app.state.oops = state

    app.include_router(health_router)
    app.include_router(tags_router)
    app.include_router(agent_settings_router)
    app.include_router(tasks_router)
    app.include_router(problems_router)
    app.include_router(models_router)
    app.include_router(latex_router)
    app.include_router(papers_router)

    return app


def _build_state() -> tuple[
    BackendState, ModelsService, TasksService, dict[str, object], AppConfig
]:
    config = load_app_config()
    global _APP_CONFIG
    _APP_CONFIG = config

    repository = build_repository(config=config)
    archive_store = ArchiveStore()
    asset_store = LocalAssetStore()

    agent_settings_service = build_agent_settings_service()

    agent_config_bundle = load_agent_config_bundle(config.agent_config_path)
    global _AGENT_CONFIG_BUNDLE
    _AGENT_CONFIG_BUNDLE = agent_config_bundle

    ai_client = build_ai_client(config=config)

    models_service = ModelsService(
        # Use dynamic lookups so tests can monkeypatch module-level helpers.
        guess_config=lambda: _guess_openai_gateway_config(),
        fetch_models=lambda base_url, api_key, authorization, auth_header_name, timeout_seconds: (
            _fetch_openai_models(
                base_url,
                api_key,
                authorization,
                auth_header_name,
                timeout_seconds,
            )
        ),
        cache_getter=_models_cache_getter,
        cache_setter=_models_cache_setter,
    )

    pipeline = build_pipeline(
        ai_client=ai_client,
        agent_config_bundle=agent_config_bundle,
        agent_settings_service=agent_settings_service,
        archive_store=archive_store,
    )

    tasks_service = build_tasks_service(
        repository=repository,
        pipeline=pipeline,
        asset_store=asset_store,
    )

    ai_gateway_status: dict[str, object] = {"checked": False}

    state = BackendState(
        repository=repository,
        ai_gateway_status=ai_gateway_status,
        agent_settings=agent_settings_service,
        tasks=tasks_service,
        models=models_service,
    )

    return state, models_service, tasks_service, ai_gateway_status, config


def _models_cache_getter() -> list[dict[str, object]] | None:
    return _MODELS_CACHE


def _models_cache_setter(value: list[dict[str, object]] | None) -> None:
    global _MODELS_CACHE
    _MODELS_CACHE = value


def _guess_openai_gateway_config() -> tuple[str | None, str | None, str | None, str]:
    if _APP_CONFIG is None:
        return guess_openai_gateway_config(load_app_config(), _AGENT_CONFIG_BUNDLE)
    return guess_openai_gateway_config(_APP_CONFIG, _AGENT_CONFIG_BUNDLE)


def _fetch_openai_models(
    base_url: str,
    api_key: str | None,
    authorization: str | None,
    auth_header_name: str,
    timeout_seconds: float,
) -> list[dict[str, object]]:
    return fetch_openai_models(
        base_url, api_key, authorization, auth_header_name, timeout_seconds
    )
