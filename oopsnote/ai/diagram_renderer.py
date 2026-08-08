"""Client for the authoritative same-source TikZ render bundle."""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

import httpx

from oopsnote.content import validate_oopsmark
from oopsnote.core import AssetStore


@dataclass(frozen=True)
class TikzRenderBundle:
    svg_path: str
    pdf_path: str
    png_path: str
    renderer_profile_version: str


class TikzRenderError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class TikzRenderClient:
    def __init__(self, asset_store: AssetStore, renderer_url: str | None = None) -> None:
        self.asset_store = asset_store
        self.renderer_url = (
            renderer_url if renderer_url is not None
            else os.getenv("OOPSNOTE_LATEX_RENDERER_URL", "")
        ).rstrip("/")

    def render(self, source: str) -> TikzRenderBundle:
        source = source.strip()
        issues = validate_oopsmark(f"```tikz\n{source}\n```")
        if issues:
            first = issues[0]
            raise TikzRenderError(
                "invalid_tikz_source",
                f"{first.code} at line {first.line}: {first.message}",
            )
        if not self.renderer_url:
            raise TikzRenderError(
                "renderer_unavailable",
                "LaTeX renderer is not configured",
                # Missing configuration is deterministic. Retrying the same
                # run cannot create a renderer endpoint or change its URL.
                retryable=False,
            )
        try:
            response = httpx.post(
                f"{self.renderer_url}/v1/tikz/bundle",
                json={"source": source},
                timeout=95,
            )
        except httpx.TimeoutException as error:
            raise TikzRenderError("renderer_timeout", "TikZ rendering timed out", retryable=True) from error
        except httpx.TransportError as error:
            raise TikzRenderError("renderer_unavailable", str(error), retryable=True) from error
        if response.status_code != 200:
            code = "renderer_failed" if response.status_code < 500 else "renderer_unavailable"
            raise TikzRenderError(code, response.text[-12_000:], retryable=response.status_code >= 500)
        try:
            payload = response.json()
            profile = str(payload["renderer_profile_version"])
            assets = {
                extension: base64.b64decode(payload[f"{extension}_base64"], validate=True)
                for extension in ("svg", "pdf", "png")
            }
        except (KeyError, TypeError, ValueError) as error:
            raise TikzRenderError("renderer_contract_error", "Renderer returned an invalid bundle") from error
        identity = hashlib.sha256(f"{profile}\0{source}".encode("utf-8")).hexdigest()[:32]
        return TikzRenderBundle(
            svg_path=self.asset_store.save_bytes(assets["svg"], "diagram.svg", f"tikz-{identity}"),
            pdf_path=self.asset_store.save_bytes(assets["pdf"], "diagram.pdf", f"tikz-{identity}"),
            png_path=self.asset_store.save_bytes(assets["png"], "diagram.png", f"tikz-{identity}"),
            renderer_profile_version=profile,
        )


__all__ = ["TikzRenderBundle", "TikzRenderClient", "TikzRenderError"]
