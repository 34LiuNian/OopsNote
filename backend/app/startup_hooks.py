from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .clients import load_agent_config_bundle
from .config import AppConfig
from .gateway import collect_openai_gateway_urls, probe_openai_gateway

logger = logging.getLogger(__name__)


def check_ai_gateway(ai_gateway_status: dict[str, object], *, config: AppConfig) -> None:
    if config.running_under_pytest:
        ai_gateway_status.update({"checked": False, "skipped": "pytest"})
        return

    require_gateway = config.require_gateway
    agent_config_bundle = load_agent_config_bundle(config.agent_config_path)
    urls = collect_openai_gateway_urls(config, agent_config_bundle)
    if not urls:
        ai_gateway_status.update({"checked": True, "configured": False})
        return

    results: list[dict[str, object]] = []
    any_down = False
    for label, base_url in urls:
        ok, detail = probe_openai_gateway(base_url)
        results.append({"label": label, "base_url": base_url, "ok": ok, "detail": detail})
        if not ok:
            any_down = True

    ai_gateway_status.update(
        {
            "checked": True,
            "configured": True,
            "ok": not any_down,
            "targets": results,
            "require_gateway": require_gateway,
        }
    )

    if any_down:
        logger.warning(
            "OpenAI-compatible gateway not reachable at startup; tasks may fallback or fail. "
            "Set AI_REQUIRE_GATEWAY=true to fail fast. targets=%s",
            results,
        )
        if require_gateway:
            raise RuntimeError("AI_REQUIRE_GATEWAY=true but gateway probe failed")


def log_llm_payload_startup(config: AppConfig) -> None:
    if not config.debug_llm_payload:
        return
    try:
        payload_log_path = config.debug_llm_payload_path
        if not payload_log_path:
            payload_log_path = str(Path(__file__).resolve().parents[1] / "storage" / "llm_payloads.log")
        startup_record = {
            "type": "startup_check",
            "ts": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }
        with open(payload_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(startup_record, ensure_ascii=False) + "\n")
        logging.getLogger("uvicorn.error").info(
            "LLM payload log enabled; test record written path=%s",
            payload_log_path,
        )
    except Exception:
        pass
