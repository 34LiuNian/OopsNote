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
_RENDERER_PROFILE_VERSION = "tikz-xelatex-v6"
_TIKZ_BASE_FONT_SIZE_PT = 10.0
_TEX_POINTS_PER_INCH = 72.27
_PDF_POINTS_PER_INCH = 72.0
_TEMP_ROOT = "/tmp" if Path("/tmp").is_dir() else None
_CJK_FONT = os.getenv("OOPSNOTE_CJK_FONT", "Noto Serif CJK SC")
_CJK_FONT_FILE_VALUE = os.getenv("OOPSNOTE_CJK_FONT_FILE", "").strip()
_TIKZ_ENVIRONMENT_READY = False
if not re.fullmatch(r"[\w .-]{1,128}", _CJK_FONT):
    raise RuntimeError("OOPSNOTE_CJK_FONT contains unsupported characters")
_CJK_FONT_FILE: Path | None = None
if _CJK_FONT_FILE_VALUE:
    _CJK_FONT_FILE = Path(_CJK_FONT_FILE_VALUE).expanduser().resolve()
    if not _CJK_FONT_FILE.is_file() or _CJK_FONT_FILE.suffix.lower() not in {
        ".otf",
        ".ttf",
        ".ttc",
    }:
        raise RuntimeError("OOPSNOTE_CJK_FONT_FILE must reference an installed OpenType font")
    font_directory = f"{_CJK_FONT_FILE.parent.as_posix().rstrip('/')}/"
    if any(character in font_directory for character in "{}\r\n"):
        raise RuntimeError("OOPSNOTE_CJK_FONT_FILE contains unsupported characters")
    _CJK_FONT_DECLARATION = rf"\setCJKmainfont[Path={{{font_directory}}}]{{{_CJK_FONT_FILE.name}}}"
else:
    _CJK_FONT_DECLARATION = rf"\setCJKmainfont{{{_CJK_FONT}}}"


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
{_CJK_FONT_DECLARATION}
\usepackage{{amsmath,amssymb,mhchem}}
\usepackage{{tikz}}
\usetikzlibrary{{calc}}
\begin{{document}}
\fontsize{{{_TIKZ_BASE_FONT_SIZE_PT:g}pt}}{{12pt}}\selectfont
"""


def _environment_error(message: str, evidence: str) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "renderer_environment_error",
            "message": message,
            "retryable": False,
            "evidence": evidence[-12_000:],
        },
    )


def _png_converter() -> tuple[str, str]:
    if shutil.which("rsvg-convert"):
        return "rsvg", "rsvg-convert"
    if shutil.which("pdftocairo"):
        return "poppler", "pdftocairo"
    raise HTTPException(status_code=503, detail="PNG converter is unavailable")


def _svg_converter() -> str:
    """Return the PDF-backed SVG converter used for browser-safe output."""

    converter = shutil.which("pdftocairo")
    if converter:
        return converter
    raise HTTPException(status_code=503, detail="PDF to SVG converter is unavailable")


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
    base_font_size_pt: float
    canvas_width_em: float
    canvas_height_em: float


def _run_xelatex(
    directory: Path,
    filename: str,
    timeout: int,
    *,
    no_pdf: bool,
    passes: int = 2,
) -> tuple[Path, str]:
    # Keep the host TeX runtime context (notably USERPROFILE, TEMP, and
    # LOCALAPPDATA for MiKTeX's logs/cache) while applying the restricted I/O
    # knobs required by the renderer boundary.
    environment = {
        **os.environ,
        "openin_any": "p",
        "openout_any": "p",
    }
    command = [
        "xelatex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-no-shell-escape",
    ]
    if no_pdf:
        command.append("-no-pdf")
    command.append(filename)
    logs: list[str] = []
    for _ in range(passes):
        try:
            result = subprocess.run(
                command,
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
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


def _convert_tikz_outputs(directory: Path, xdv: Path) -> tuple[Path, Path, Path]:
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
        svg_result = subprocess.run(
            [_svg_converter(), "-svg", pdf.name, svg.name],
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(status_code=504, detail="PDF to SVG conversion timed out") from error
    if svg_result.returncode or not svg.is_file():
        raise HTTPException(
            status_code=422,
            detail=(svg_result.stdout + svg_result.stderr)[-12_000:],
        )
    svg_text = svg.read_text(encoding="utf-8", errors="replace")
    drawable_body = svg_text.split("</defs>", 1)[-1]
    if "<svg" not in svg_text or "<path" not in drawable_body:
        raise HTTPException(
            status_code=422,
            detail="PDF to SVG conversion produced no drawable paths",
        )
    converter, converter_command = _png_converter()
    png_command = (
        [converter_command, "-f", "png", "-o", png.name, svg.name]
        if converter == "rsvg"
        else [converter_command, "-png", "-singlefile", "-r", "160", pdf.name, png.stem]
    )
    try:
        converted = subprocess.run(
            png_command,
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise HTTPException(status_code=504, detail="diagram to PNG timed out") from error
    if converted.returncode or not png.is_file():
        raise HTTPException(
            status_code=422,
            detail=(converted.stdout + converted.stderr)[-12_000:],
        )
    return svg, pdf, png


def _pdf_canvas_em(pdf: Path) -> tuple[float, float]:
    """Return the standalone PDF MediaBox normalized by the TikZ default em."""

    try:
        result = subprocess.run(
            ["pdfinfo", "-box", pdf.name],
            cwd=pdf.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise _environment_error(
            "TikZ renderer cannot inspect PDF dimensions",
            str(error),
        ) from error
    output = result.stdout + result.stderr
    match = re.search(
        r"^MediaBox:\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s+(-?[0-9.]+)\s*$",
        output,
        flags=re.MULTILINE,
    )
    if result.returncode or match is None:
        raise _environment_error(
            "TikZ renderer returned a PDF without a readable MediaBox",
            output,
        )
    x0, y0, x1, y1 = (float(value) for value in match.groups())
    width_pdf_pt = x1 - x0
    height_pdf_pt = y1 - y0
    base_font_pdf_pt = _TIKZ_BASE_FONT_SIZE_PT * _PDF_POINTS_PER_INCH / _TEX_POINTS_PER_INCH
    if width_pdf_pt <= 0 or height_pdf_pt <= 0:
        raise _environment_error(
            "TikZ renderer returned a non-positive PDF canvas",
            output,
        )
    return width_pdf_pt / base_font_pdf_pt, height_pdf_pt / base_font_pdf_pt


def _ensure_tikz_environment() -> None:
    """Validate the shared renderer preamble before compiling user TikZ."""

    global _TIKZ_ENVIRONMENT_READY
    if _TIKZ_ENVIRONMENT_READY:
        return
    required = [
        name for name in ("xelatex", "xdvipdfmx", "pdftocairo", "pdfinfo") if not shutil.which(name)
    ]
    try:
        _png_converter()
    except HTTPException:
        required.append("rsvg-convert or pdftocairo")
    if required:
        missing = ", ".join(required)
        raise _environment_error(
            "TikZ renderer environment is incomplete; manual intervention is required",
            f"Missing renderer executables: {missing}",
        )
    with tempfile.TemporaryDirectory(prefix="oopsnote-tikz-probe-", dir=_TEMP_ROOT) as temp_name:
        directory = Path(temp_name)
        (directory / "probe.tex").write_text(
            _TIKZ_PREAMBLE
            + "\\begin{tikzpicture}\\draw (0,0) -- (1,1);\\end{tikzpicture}\n"
            + "\\end{document}\n",
            encoding="utf-8",
        )
        try:
            xdv, _ = _run_xelatex(
                directory,
                "probe.tex",
                timeout=30,
                no_pdf=True,
                passes=1,
            )
            _convert_tikz_outputs(directory, xdv)
        except HTTPException as error:
            if error.status_code not in {422, 503}:
                raise
            detail = error.detail if isinstance(error.detail, str) else str(error.detail)
            raise _environment_error(
                "TikZ renderer shared preamble is invalid; manual intervention is required",
                detail,
            ) from error
    _TIKZ_ENVIRONMENT_READY = True


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
        "svg_converter": shutil.which("pdftocairo") or "missing",
        "xdvipdfmx": shutil.which("xdvipdfmx") or "missing",
        "pdfinfo": shutil.which("pdfinfo") or "missing",
        "rsvg_convert": shutil.which("rsvg-convert") or "missing",
        "png_converter": converter,
        "png_converter_path": converter_path,
        "cjk_font": _CJK_FONT_FILE.name if _CJK_FONT_FILE else _CJK_FONT,
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
                raise HTTPException(
                    status_code=422, detail="Invalid paper asset encoding"
                ) from error
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
def _render_tikz_bundle(payload: TikzRequest) -> tuple[bytes, bytes, bytes, float, float]:
    _ensure_tikz_environment()
    source = payload.source.strip()
    if _FORBIDDEN.search(source):
        raise HTTPException(status_code=422, detail="TikZ source contains a forbidden TeX command")
    if "\\begin{tikzpicture}" not in source:
        source = "\\begin{tikzpicture}\n" + source + "\n\\end{tikzpicture}"
    with tempfile.TemporaryDirectory(prefix="oopsnote-tikz-", dir=_TEMP_ROOT) as temp_name:
        directory = Path(temp_name)
        (directory / "diagram.tex").write_text(
            _TIKZ_PREAMBLE + source + "\n\\end{document}\n", encoding="utf-8"
        )
        xdv, _ = _run_xelatex(
            directory,
            "diagram.tex",
            timeout=60,
            no_pdf=True,
            passes=1,
        )
        svg, pdf, png = _convert_tikz_outputs(directory, xdv)
        canvas_width_em, canvas_height_em = _pdf_canvas_em(pdf)
        return (
            svg.read_bytes(),
            pdf.read_bytes(),
            png.read_bytes(),
            canvas_width_em,
            canvas_height_em,
        )


@app.post("/v1/tikz")
def render_tikz(payload: TikzRequest) -> Response:
    svg, _pdf, _png, _width_em, _height_em = _render_tikz_bundle(payload)
    return Response(content=svg, media_type="image/svg+xml")


@app.post("/v1/tikz/bundle", response_model=TikzBundleResponse)
def render_tikz_bundle(payload: TikzRequest) -> TikzBundleResponse:
    svg, pdf, png, canvas_width_em, canvas_height_em = _render_tikz_bundle(payload)
    return TikzBundleResponse(
        svg_base64=base64.b64encode(svg).decode("ascii"),
        pdf_base64=base64.b64encode(pdf).decode("ascii"),
        png_base64=base64.b64encode(png).decode("ascii"),
        renderer_profile_version=_renderer_profile_version(),
        base_font_size_pt=_TIKZ_BASE_FONT_SIZE_PT,
        canvas_width_em=canvas_width_em,
        canvas_height_em=canvas_height_em,
    )
