from __future__ import annotations

import json
from .config import AppConfig
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import HTTPException


def probe_openai_gateway(base_url: str, timeout_seconds: float = 1.2) -> tuple[bool, str]:
    """Best-effort reachability probe.

    Treat any HTTP response (including 401/403/404) as "reachable".
    Only connection/timeout errors count as unreachable.
    """

    url = base_url.rstrip("/") + "/models"
    request = urllib.request.Request(url, headers={"Content-Type": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return True, f"http_{response.status}"
    except urllib.error.HTTPError as exc:
        return True, f"http_{exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def collect_openai_gateway_urls(config: AppConfig, agent_config_bundle: Any) -> list[tuple[str, str]]:
    """Collect configured OpenAI-compatible base URLs from env + agent config.

    Returns a list of (label, base_url).
    """

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(label: str, value: str | None) -> None:
        if not value:
            return
        url = str(value).strip()
        if not url:
            return
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return
        norm = url.rstrip("/")
        if norm in seen:
            return
        seen.add(norm)
        candidates.append((label, norm))

    _add("env:OPENAI_BASE_URL", config.openai_base_url)
    for name, value in config.agent_base_urls.items():
        _add(f"env:AGENT_{name}_BASE_URL", value)

    try:
        default_cfg = agent_config_bundle.default if agent_config_bundle else None
        if default_cfg and default_cfg.provider == "openai":
            _add("toml:default.base_url", default_cfg.base_url)
    except Exception:
        pass

    try:
        agents_cfg = agent_config_bundle.agents if agent_config_bundle else None
        if agents_cfg:
            for name, cfg in agents_cfg.items():
                if cfg and cfg.provider == "openai":
                    _add(f"toml:agents.{name}.base_url", cfg.base_url)
    except Exception:
        pass

    return candidates


def guess_openai_gateway_config(
    config: AppConfig,
    agent_config_bundle: Any,
) -> tuple[str | None, str | None, str | None, str]:
    """Pick a base_url+api_key for OpenAI-compatible gateway model listing.

    Priority:
      1) agent TOML default if provider=openai
      2) env OPENAI_BASE_URL + OPENAI_API_KEY
    """

    base_url: str | None = None
    api_key: str | None = None
    authorization: str | None = None
    auth_header_name: str = "Authorization"

    try:
        default_cfg = agent_config_bundle.default if agent_config_bundle else None
        if default_cfg and default_cfg.provider == "openai":
            base_url = default_cfg.base_url
            api_key = default_cfg.api_key
    except Exception:
        pass

    base_url = base_url or config.openai_base_url
    api_key = api_key or config.openai_api_key
    authorization = config.openai_authorization
    auth_header_name = config.openai_auth_header_name

    if authorization and not api_key:
        prefix = "Bearer "
        api_key = authorization[len(prefix) :].strip() if authorization.startswith(prefix) else authorization.strip()

    return base_url, api_key, authorization, auth_header_name


def fetch_openai_models(
    base_url: str,
    api_key: str | None,
    authorization: str | None,
    auth_header_name: str = "Authorization",
    timeout_seconds: float = 5.0,
) -> list[dict[str, object]]:
    url = base_url.rstrip("/") + "/models"

    headers = {
        "Content-Type": "application/json",
    }
    if authorization:
        headers[auth_header_name] = authorization
    elif api_key:
        headers[auth_header_name] = f"Bearer {api_key}"

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        raise HTTPException(status_code=exc.code, detail=body or str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach gateway: {exc}") from exc

    payload = json.loads(body)
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(data, list):
        return []
    items: list[dict[str, object]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "id": item.get("id"),
                "provider": item.get("provider"),
                "provider_type": item.get("provider_type"),
            }
        )
    return items
