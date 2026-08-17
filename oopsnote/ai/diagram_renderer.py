"""Client for the authoritative same-source TikZ render bundle."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from oopsnote.content import validate_oopsmark
from oopsnote.core import AssetStore

_LEGACY_TIKZ_BASE_FONT_SIZE_PT = 10.0
_TEX_POINTS_PER_INCH = 72.27
_PDF_POINTS_PER_INCH = 72.0
_SVG_LENGTH = re.compile(r"^\s*([0-9]+(?:\.[0-9]*)?)\s*(pt|px|in|cm|mm|pc)?\s*$")


@dataclass(frozen=True)
class TikzRenderBundle:
    svg_path: str
    pdf_path: str
    png_path: str
    renderer_profile_version: str
    base_font_size_pt: float
    canvas_width_em: float
    canvas_height_em: float


class TikzRenderError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        evidence: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.evidence = evidence


def legacy_svg_canvas_em(svg: str) -> tuple[float, float] | None:
    """Read physical SVG dimensions to migrate one old TikZ display once."""

    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return None
    if root.tag.rsplit("}", 1)[-1].lower() != "svg":
        return None

    def length_in_pdf_pt(raw: str | None) -> float | None:
        if not raw:
            return None
        match = _SVG_LENGTH.fullmatch(raw)
        if match is None:
            return None
        value = float(match.group(1))
        unit = match.group(2) or "px"
        if unit == "pt":
            return value
        if unit == "px":
            return value * _PDF_POINTS_PER_INCH / 96
        if unit == "in":
            return value * _PDF_POINTS_PER_INCH
        if unit == "cm":
            return value * _PDF_POINTS_PER_INCH / 2.54
        if unit == "mm":
            return value * _PDF_POINTS_PER_INCH / 25.4
        return value * _PDF_POINTS_PER_INCH / 6

    width_pt = length_in_pdf_pt(root.attrib.get("width"))
    height_pt = length_in_pdf_pt(root.attrib.get("height"))
    base_font_pdf_pt = _LEGACY_TIKZ_BASE_FONT_SIZE_PT * _PDF_POINTS_PER_INCH / _TEX_POINTS_PER_INCH
    if width_pt is None or height_pt is None or min(width_pt, height_pt) <= 0:
        return None
    return width_pt / base_font_pdf_pt, height_pt / base_font_pdf_pt


def _renderer_error_detail(response: httpx.Response) -> tuple[str | None, str, bool, str]:
    raw = response.text[-12_000:]
    try:
        payload = response.json()
    except ValueError:
        payload = None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        code = str(detail.get("code") or "").strip() or None
        message = str(detail.get("message") or raw).strip()
        retryable = bool(detail.get("retryable", response.status_code >= 500))
        evidence = str(detail.get("evidence") or raw)
        return code, message, retryable, evidence
    message = str(detail).strip() if isinstance(detail, str) else raw
    return None, message, response.status_code >= 500, raw


def _is_legacy_environment_error(message: str) -> bool:
    normalized = message.lower()
    return (
        "package fontspec error" in normalized
        and "noto serif cjk sc" in normalized
        and "cannot be found" in normalized
    )


class TikzRenderClient:
    def __init__(self, asset_store: AssetStore, renderer_url: str | None = None) -> None:
        self.asset_store = asset_store
        self.renderer_url = (
            renderer_url
            if renderer_url is not None
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
            raise TikzRenderError(
                "renderer_timeout", "TikZ rendering timed out", retryable=True
            ) from error
        except httpx.TransportError as error:
            raise TikzRenderError("renderer_unavailable", str(error), retryable=True) from error
        if response.status_code != 200:
            explicit_code, message, retryable, evidence = _renderer_error_detail(response)
            if explicit_code:
                code = explicit_code
            elif _is_legacy_environment_error(message):
                code = "renderer_environment_error"
                message = (
                    "TikZ renderer shared preamble is invalid; manual intervention is required"
                )
                retryable = False
            else:
                code = "renderer_failed" if response.status_code < 500 else "renderer_unavailable"
            raise TikzRenderError(
                code,
                message,
                retryable=retryable,
                evidence=evidence,
            )
        try:
            payload = response.json()
            profile = str(payload["renderer_profile_version"])
            base_font_size_pt = float(payload["base_font_size_pt"])
            canvas_width_em = float(payload["canvas_width_em"])
            canvas_height_em = float(payload["canvas_height_em"])
            if min(base_font_size_pt, canvas_width_em, canvas_height_em) <= 0:
                raise ValueError("TikZ dimensions must be positive")
            assets = {
                extension: base64.b64decode(payload[f"{extension}_base64"], validate=True)
                for extension in ("svg", "pdf", "png")
            }
        except (KeyError, TypeError, ValueError) as error:
            raise TikzRenderError(
                "renderer_contract_error", "Renderer returned an invalid bundle"
            ) from error
        identity = hashlib.sha256(f"{profile}\0{source}".encode()).hexdigest()[:32]
        return TikzRenderBundle(
            svg_path=self.asset_store.save_bytes(assets["svg"], "diagram.svg", f"tikz-{identity}"),
            pdf_path=self.asset_store.save_bytes(assets["pdf"], "diagram.pdf", f"tikz-{identity}"),
            png_path=self.asset_store.save_bytes(assets["png"], "diagram.png", f"tikz-{identity}"),
            renderer_profile_version=profile,
            base_font_size_pt=base_font_size_pt,
            canvas_width_em=canvas_width_em,
            canvas_height_em=canvas_height_em,
        )


__all__ = ["TikzRenderBundle", "TikzRenderClient", "TikzRenderError"]
