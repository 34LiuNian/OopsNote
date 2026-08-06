"""Restricted XeLaTeX renderer for OopsNote's internal Docker network."""

from __future__ import annotations

import base64
import binascii
import os
import re
import shutil
import subprocess
import tempfile
import threading
from functools import wraps
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

app = FastAPI(title="OopsNote LaTeX Renderer")
_RENDER_LOCK = threading.BoundedSemaphore(1)
_RENDERER_PROFILE_VERSION = "tikz-xelatex-v2"
_TEMP_ROOT = "/tmp" if Path("/tmp").is_dir() else None
_CJK_FONT = os.getenv("OOPSNOTE_CJK_FONT", "Noto Serif CJK SC")
if not re.fullmatch(r"[\w .-]{1,128}", _CJK_FONT):
    raise RuntimeError("OOPSNOTE_CJK_FONT contains unsupported characters")


def _serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _RENDER_LOCK:
            return function(*args, **kwargs)
    return wrapped
_SAFE_ASSET = re.compile(r"^assets/[a-f0-9]{20}\.(?:png|jpe?g|pdf)$")
_FORBIDDEN = re.compile(
    r"\\(?:documentclass|usepackage|input|include|write18|openout|read)\b|"
    r"\\(?:begin|end)\s*\{document\}"
)
_TIKZ_PREAMBLE = rf"""\documentclass{{standalone}}
\usepackage{{fontspec}}
\usepackage{{xeCJK}}
\setCJKmainfont{{{_CJK_FONT}}}
\usepackage{{amsmath,amssymb,mhchem}}
\usepackage{{tikz}}
\usetikzlibrary{{calc}}
\begin{{document}}
"""


def _png_converter() -> tuple[str, str]:
    if shutil.which("rsvg-convert"):
        return "rsvg", "rsvg-convert"
    if shutil.which("pdftocairo"):
        return "poppler", "pdftocairo"
    raise HTTPException(status_code=503, detail="PNG converter is unavailable")


def _renderer_profile_version() -> str:
    converter, _command = _png_converter()
    return f"{_RENDERER_PROFILE_VERSION}-{converter}"


class BundleFile(BaseModel):
    path: str
    content_base64: str


class PaperRequest(BaseModel):
    tex: str = Field(min_length=1, max_length=2_000_000)
    files: list[BundleFile] = Field(default_factory=list, max_length=128)


class TikzRequest(BaseModel):
    source: str = Field(min_length=1, max_length=80_000)


class TikzBundleResponse(BaseModel):
    svg_base64: str
    pdf_base64: str
    png_base64: str
    renderer_profile_version: str


def _run_xelatex(
    directory: Path,
    filename: str,
    timeout: int,
    *,
    no_pdf: bool,
    passes: int = 2,
) -> tuple[Path, str]:
    environment = {"PATH": os.environ["PATH"], "openin_any": "p", "openout_any": "p"}
    command = [
        "xelatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
        "-no-shell-escape",
    ]
    if no_pdf:
        command.append("-no-pdf")
    command.append(filename)
    logs: list[str] = []
    for _ in range(passes):
        try:
            result = subprocess.run(
                command, cwd=directory, env=environment, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise HTTPException(status_code=504, detail="XeLaTeX compilation timed out") from error
        logs.append(result.stdout + result.stderr)
        if result.returncode:
            raise HTTPException(status_code=422, detail="\n".join(logs)[-12_000:])
    output = directory / Path(filename).with_suffix(".xdv" if no_pdf else ".pdf")
    if not output.is_file():
        raise HTTPException(
            status_code=422,
            detail=f"XeLaTeX did not produce {output.suffix.upper()} output",
        )
    return output, "\n".join(logs)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        converter, converter_path = _png_converter()
    except HTTPException:
        converter, converter_path = "missing", "missing"
    return {
        "status": "ok",
        "xelatex": shutil.which("xelatex") or "missing",
        "dvisvgm": shutil.which("dvisvgm") or "missing",
        "xdvipdfmx": shutil.which("xdvipdfmx") or "missing",
        "rsvg_convert": shutil.which("rsvg-convert") or "missing",
        "png_converter": converter,
        "png_converter_path": converter_path,
        "profile": (
            _renderer_profile_version()
            if converter != "missing"
            else f"{_RENDERER_PROFILE_VERSION}-unavailable"
        ),
    }


@app.post("/v1/paper")
@_serialized
def render_paper(payload: PaperRequest) -> Response:
    total_size = 0
    with tempfile.TemporaryDirectory(prefix="oopsnote-paper-", dir=_TEMP_ROOT) as temp_name:
        directory = Path(temp_name)
        (directory / "paper.tex").write_text(payload.tex, encoding="utf-8")
        for item in payload.files:
            if not _SAFE_ASSET.fullmatch(item.path):
                raise HTTPException(status_code=422, detail="Invalid paper asset path")
            try:
                content = base64.b64decode(item.content_base64, validate=True)
            except (binascii.Error, ValueError) as error:
                raise HTTPException(status_code=422, detail="Invalid paper asset encoding") from error
            total_size += len(content)
            if total_size > 64 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="Paper assets exceed 64 MiB")
            output = directory / item.path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        _run_xelatex(directory, "paper.tex", timeout=120, no_pdf=False)
        pdf = directory / "paper.pdf"
        if not pdf.is_file():
            raise HTTPException(status_code=422, detail="XeLaTeX did not produce PDF output")
        return Response(content=pdf.read_bytes(), media_type="application/pdf")


@_serialized
def _render_tikz_bundle(payload: TikzRequest) -> tuple[bytes, bytes, bytes]:
    source = payload.source.strip()
    if _FORBIDDEN.search(source):
        raise HTTPException(status_code=422, detail="TikZ source contains a forbidden TeX command")
    if "\\begin{tikzpicture}" not in source:
        source = "\\begin{tikzpicture}\n" + source + "\n\\end{tikzpicture}"
    with tempfile.TemporaryDirectory(prefix="oopsnote-tikz-", dir=_TEMP_ROOT) as temp_name:
        directory = Path(temp_name)
        (directory / "diagram.tex").write_text(_TIKZ_PREAMBLE + source + "\n\\end{document}\n", encoding="utf-8")
        xdv, _ = _run_xelatex(
            directory,
            "diagram.tex",
            timeout=60,
            no_pdf=True,
            passes=1,
        )
        svg = directory / "diagram.svg"
        pdf = directory / "diagram.pdf"
        png = directory / "diagram.png"
        try:
            pdf_result = subprocess.run(
                ["xdvipdfmx", "-q", "-o", pdf.name, xdv.name],
                cwd=directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise HTTPException(status_code=504, detail="XDV to PDF timed out") from error
        if pdf_result.returncode or not pdf.is_file():
            raise HTTPException(
                status_code=422,
                detail=(pdf_result.stdout + pdf_result.stderr)[-12_000:],
            )
        try:
            result = subprocess.run(
                [
                    "dvisvgm",
                    "--pdf",
                    "--no-fonts",
                    "--bbox=min",
                    f"--output={svg.name}",
                    pdf.name,
                ],
                cwd=directory, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise HTTPException(status_code=504, detail="dvisvgm conversion timed out") from error
        if result.returncode or not svg.is_file():
            raise HTTPException(status_code=422, detail=(result.stdout + result.stderr)[-12_000:])
        converter, converter_command = _png_converter()
        png_command = (
            [converter_command, "-f", "png", "-o", png.name, svg.name]
            if converter == "rsvg"
            else [converter_command, "-png", "-singlefile", "-r", "160", pdf.name, png.stem]
        )
        conversions = ((png_command, png, "diagram to PNG"),)
        for command, output, label in conversions:
            try:
                converted = subprocess.run(
                    command,
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise HTTPException(status_code=504, detail=f"{label} timed out") from error
            if converted.returncode or not output.is_file():
                raise HTTPException(
                    status_code=422,
                    detail=(converted.stdout + converted.stderr)[-12_000:],
                )
        return svg.read_bytes(), pdf.read_bytes(), png.read_bytes()


@app.post("/v1/tikz")
def render_tikz(payload: TikzRequest) -> Response:
    svg, _pdf, _png = _render_tikz_bundle(payload)
    return Response(content=svg, media_type="image/svg+xml")


@app.post("/v1/tikz/bundle", response_model=TikzBundleResponse)
def render_tikz_bundle(payload: TikzRequest) -> TikzBundleResponse:
    svg, pdf, png = _render_tikz_bundle(payload)
    return TikzBundleResponse(
        svg_base64=base64.b64encode(svg).decode("ascii"),
        pdf_base64=base64.b64encode(pdf).decode("ascii"),
        png_base64=base64.b64encode(png).decode("ascii"),
        renderer_profile_version=_renderer_profile_version(),
    )
