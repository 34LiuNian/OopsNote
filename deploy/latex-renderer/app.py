"""Restricted XeLaTeX renderer for OopsNote's internal Docker network."""

from __future__ import annotations

import base64
import binascii
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

app = FastAPI(title="OopsNote LaTeX Renderer")
_SAFE_ASSET = re.compile(r"^assets/[a-f0-9]{20}\.(?:png|jpe?g|pdf)$")
_FORBIDDEN = re.compile(
    r"\\(?:documentclass|usepackage|input|include|write18|openout|read)\b|"
    r"\\(?:begin|end)\s*\{document\}"
)
_TIKZ_PREAMBLE = r"""\documentclass{standalone}
\usepackage{fontspec}
\usepackage{xeCJK}
\setCJKmainfont{Noto Serif CJK SC}
\usepackage{amsmath,amssymb,mhchem}
\usepackage{tikz}
\usetikzlibrary{calc}
\begin{document}
"""


class BundleFile(BaseModel):
    path: str
    content_base64: str


class PaperRequest(BaseModel):
    tex: str = Field(min_length=1, max_length=2_000_000)
    files: list[BundleFile] = Field(default_factory=list, max_length=128)


class TikzRequest(BaseModel):
    source: str = Field(min_length=1, max_length=80_000)


def _run_xelatex(directory: Path, filename: str, timeout: int, *, no_pdf: bool) -> tuple[Path, str]:
    environment = {"PATH": os.environ["PATH"], "openin_any": "p", "openout_any": "p"}
    command = [
        "xelatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
        "-no-shell-escape",
    ]
    if no_pdf:
        command.append("-no-pdf")
    command.append(filename)
    logs: list[str] = []
    for _ in range(2):
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
    xdv = directory / Path(filename).with_suffix(".xdv")
    if not xdv.is_file():
        raise HTTPException(status_code=422, detail="XeLaTeX did not produce XDV output")
    return xdv, "\n".join(logs)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "xelatex": shutil.which("xelatex") or "missing", "dvisvgm": shutil.which("dvisvgm") or "missing"}


@app.post("/v1/paper")
def render_paper(payload: PaperRequest) -> Response:
    total_size = 0
    with tempfile.TemporaryDirectory(prefix="oopsnote-paper-", dir="/tmp") as temp_name:
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


@app.post("/v1/tikz")
def render_tikz(payload: TikzRequest) -> Response:
    source = payload.source.strip()
    if _FORBIDDEN.search(source):
        raise HTTPException(status_code=422, detail="TikZ source contains a forbidden TeX command")
    if "\\begin{tikzpicture}" not in source:
        source = "\\begin{tikzpicture}\n" + source + "\n\\end{tikzpicture}"
    with tempfile.TemporaryDirectory(prefix="oopsnote-tikz-", dir="/tmp") as temp_name:
        directory = Path(temp_name)
        (directory / "diagram.tex").write_text(_TIKZ_PREAMBLE + source + "\n\\end{document}\n", encoding="utf-8")
        xdv, _ = _run_xelatex(directory, "diagram.tex", timeout=30, no_pdf=True)
        svg = directory / "diagram.svg"
        try:
            result = subprocess.run(
                ["dvisvgm", "--no-fonts", "--bbox=min", f"--output={svg.name}", xdv.name],
                cwd=directory, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise HTTPException(status_code=504, detail="dvisvgm conversion timed out") from error
        if result.returncode or not svg.is_file():
            raise HTTPException(status_code=422, detail=(result.stdout + result.stderr)[-12_000:])
        return Response(content=svg.read_bytes(), media_type="image/svg+xml")
