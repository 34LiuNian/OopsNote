from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class ModelsService:
    """List models with caching.

    NOTE: This service is designed to be test-friendly.
    Cache access and gateway functions are injected by the app bootstrap layer.
    """

    guess_config: Callable[[], tuple[str | None, str | None, str | None, str]]
    fetch_models: Callable[
        [str, str | None, str | None, str, float], list[dict[str, object]]
    ]
    cache_getter: Callable[[], list[dict[str, object]] | None]
    cache_setter: Callable[[list[dict[str, object]] | None], None]

    def prefetch_cache(self) -> None:
        try:
            base_url, api_key, authorization, auth_header_name = self.guess_config()
            if base_url and (api_key or authorization):
                self.cache_setter(
                    self.fetch_models(
                        base_url, api_key, authorization, auth_header_name, 5.0
                    )
                )
        except Exception:
            pass

    def list_models(self, refresh: bool = False) -> list[dict[str, object]]:
        cached = self.cache_getter()
        if cached is not None and not refresh:
            return list(cached)

        base_url, api_key, authorization, auth_header_name = self.guess_config()
        if not base_url:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=400,
                detail="Missing OPENAI_BASE_URL or default.base_url in agent config",
            )
        if not api_key and not authorization:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=400,
                detail="Missing OPENAI_API_KEY (or OPENAI_AUTHORIZATION) or default.api_key in agent config",
            )

        items = self.fetch_models(
            base_url, api_key, authorization, auth_header_name, 5.0
        )
        self.cache_setter(items)
        return list(items)
