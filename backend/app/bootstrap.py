"""Backend module - auto-generated docstring."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .clients import load_agent_config_bundle
from .config import AppConfig, load_app_config
from .gateway import fetch_openai_models, guess_openai_gateway_config
from .repository import ArchiveStore
from .storage import LocalAssetStore
from .app_state import BackendState
from .api.health import router as health_router
from .api.auth import router as auth_router
from .api.tags import router as tags_router
from .api.agent_settings import router as agent_settings_router
from .api.tasks import router as tasks_router
from .api.problems import router as problems_router
from .api.models import router as models_router
from .api.latex import router as latex_router
from .api.papers import router as papers_router
from .api.account import router as account_router
from .api.users import router as users_router
from .services.models_service import ModelsService
from .services.tasks_service import TasksService
from .builders import (
    build_agent_settings_service,
    build_auth_settings_service,
    build_ai_client,
    build_pipeline,
    build_repository,
    build_tasks_service,
)

logger = logging.getLogger(__name__)
_MODELS_CACHE: list[dict[str, object]] | None = None
_AGENT_CONFIG_BUNDLE = None
_APP_CONFIG: AppConfig | None = None


def configure_logging():
    """Configure application logging based on environment variables."""
    log_level = os.getenv("APP_LOG_LEVEL", "WARNING").upper()
    try:
        level = getattr(logging, log_level)
    except AttributeError:
        level = logging.WARNING

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,  # This ensures the configuration is applied even if logging was already configured
    )

    # Also configure uvicorn loggers to use the same level
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    uvicorn_access_logger.setLevel(level)
    uvicorn_error_logger.setLevel(level)


class HealthCheckFilter(logging.Filter):
    """Filter out health check and polling logs to keep the terminal clean."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        # Filter health checks
        if "/health" in message:
            return False
        # Filter task polling requests (GET /tasks/{id} without body)
        if "GET /tasks/" in message and 'HTTP/1.1" 200' in message:
            return False
        return True


# Silence noisy health check and polling logs from uvicorn access log
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Configure logging before creating the app
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # pylint: disable=unused-argument
        # Recalculate tag reference counts on startup
        try:
            from app.tags import tag_store

            stats = tag_store.recalculate_all_counts()
            logger.info("Tag counts recalculated on startup: %s", stats)
        except Exception as exc:
            logger.warning(
                "Failed to recalculate tag counts on startup: %s", exc)

        # Prefetch models
        try:
            models_service.prefetch_cache()
        except Exception:
            pass
        yield

    app = FastAPI(title="OopsNote Backend", lifespan=lifespan)

    # Mount static files for asset access
    assets_dir = Path(__file__).resolve().parent.parent / "storage" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://[::1]:3000",
        ],
        allow_origin_regex=r"https?://.*\.local(:\d+)?|http://192\.168\.\d+\.\d+(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    state, models_service = _build_state()[:2]
    app.state.oops = state

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(tags_router)
    app.include_router(agent_settings_router)
    app.include_router(tasks_router)
    app.include_router(problems_router)
    app.include_router(models_router)
    app.include_router(latex_router)
    app.include_router(papers_router)
    app.include_router(account_router)
    app.include_router(users_router)

    return app


def _build_state() -> (
    tuple[BackendState, ModelsService,
          TasksService, dict[str, object], AppConfig]
):
    config = load_app_config()
    global _APP_CONFIG
    _APP_CONFIG = config

    repository = build_repository(config=config)
    archive_store = ArchiveStore()
    asset_store = LocalAssetStore()

    agent_settings_service = build_agent_settings_service()
    auth_settings_service = build_auth_settings_service()

    # Apply gateway settings overrides (UI settings > env vars)
    gateway_settings = agent_settings_service.load_gateway()
    debug_settings = agent_settings_service.load_debug()

    agent_config_bundle = load_agent_config_bundle(config.agent_config_path)
    global _AGENT_CONFIG_BUNDLE
    _AGENT_CONFIG_BUNDLE = agent_config_bundle

    ai_client = build_ai_client(
        config=config,
        gateway_settings=gateway_settings,
        debug_settings=debug_settings,
    )

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
        auth_settings=auth_settings_service,
        tasks=tasks_service,  # type: ignore[arg-type]
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
