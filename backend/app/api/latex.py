from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from starlette.responses import Response

from ..models import ChemfigRenderRequest, LatexCompileRequest

router = APIRouter()


def _latex_template(content: str, title: Optional[str], author: Optional[str]) -> str:
    safe_title = title or "LaTeX 测试"
    safe_author = author or "OopsNote"
    return (
        "\\documentclass[12pt,a4paper]{ctexart}\n"
        "\\usepackage{amsmath,amssymb,geometry,graphicx,hyperref}\n"
        "\\geometry{margin=2.5cm}\n"
        "\\title{" + safe_title + "}\n"
        "\\author{" + safe_author + "}\n"
        "\\date{\\today}\n"
        "\\begin{document}\n"
        "\\maketitle\n"
        "\\thispagestyle{plain}\n"
        + content
        + "\n\\end{document}\n"
    )


def _read_log_tail(log_path: Path, max_lines: int = 80) -> str:
    if not log_path.exists():
        return ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return ""
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)


def _chemfig_template(content: str, inline: bool) -> str:
    body = content.strip()
    if "\\chemfig" not in body:
        body = f"\\chemfig{{{body}}}"
    if inline:
        body = f"\\({body}\\)"
    return (
        "\\documentclass[12pt]{standalone}\n"
        "\\usepackage{chemfig}\n"
        "\\usepackage{amsmath,amssymb}\n"
        "\\begin{document}\n"
        + body
        + "\n\\end{document}\n"
    )


def _find_xelatex() -> Optional[str]:
    xelatex_path = os.getenv("XELATEX_PATH") or shutil.which("xelatex")
    if not xelatex_path:
        xelatex_path = "C:\\texlive\\2025\\bin\\windows\\xelatex.exe"
    return xelatex_path


def _find_latex() -> Optional[str]:
    latex_path = os.getenv("LATEX_PATH") or shutil.which("latex")
    if not latex_path:
        latex_path = "C:\\texlive\\2025\\bin\\windows\\latex.exe"
    return latex_path


def _find_dvisvgm() -> Optional[str]:
    dvisvgm_path = os.getenv("DVISVGM_PATH") or shutil.which("dvisvgm")
    if not dvisvgm_path:
        dvisvgm_path = "C:\\texlive\\2025\\bin\\windows\\dvisvgm.exe"
    return dvisvgm_path


def _read_text_tail(text: str, max_lines: int = 80) -> str:
    lines = (text or "").splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)


@router.post("/latex/compile")
def compile_latex(payload: LatexCompileRequest) -> Response:
    if "\\documentclass" in payload.content:
        tex_content = payload.content
    else:
        tex_content = _latex_template(payload.content, payload.title, payload.author)

    latex_path = _find_latex()
    xelatex_path = _find_xelatex()
    compiler_path = latex_path or xelatex_path
    if not compiler_path:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "未找到 latex/xelatex，请先安装并加入 PATH 或设置 LATEX_PATH/XELATEX_PATH。",
                "log": "",
            },
        )

    try:
        with tempfile.TemporaryDirectory(prefix="oopsnote-latex-") as tmp_dir:
            workdir = Path(tmp_dir)
            tex_path = workdir / "main.tex"
            tex_path.write_text(tex_content, encoding="utf-8")

            try:
                result = subprocess.run(
                    [
                        xelatex_path,
                        "-interaction=nonstopmode",
                        "-halt-on-error",
                        "-no-shell-escape",
                        tex_path.name,
                    ],
                    cwd=workdir,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "未找到 xelatex，请先安装并加入 PATH 或设置 XELATEX_PATH。",
                        "log": "",
                    },
                ) from exc

            if result.returncode != 0:
                log_tail = _read_log_tail(workdir / "main.log")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "LaTeX 编译失败。",
                        "log": log_tail,
                        "exit_code": result.returncode,
                    },
                )

            pdf_path = workdir / "main.pdf"
            if not pdf_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "未生成 PDF 文件。",
                        "log": "",
                    },
                )

            pdf_bytes = pdf_path.read_bytes()
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": "inline; filename=latex.pdf"},
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"LaTeX 编译异常: {exc}",
                "log": "",
            },
        ) from exc


@router.post("/latex/chemfig")
def render_chemfig(payload: ChemfigRenderRequest) -> Response:
    latex_path = _find_latex()
    xelatex_path = _find_xelatex()
    if not latex_path and not xelatex_path:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "未找到 latex/xelatex，请先安装并加入 PATH 或设置 LATEX_PATH/XELATEX_PATH。",
                "log": "",
            },
        )

    dvisvgm_path = _find_dvisvgm()
    if not dvisvgm_path:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "未找到 dvisvgm，请先安装并加入 PATH 或设置 DVISVGM_PATH。",
                "log": "",
            },
        )

    tex_content = _chemfig_template(payload.content, payload.inline)

    try:
        with tempfile.TemporaryDirectory(prefix="oopsnote-chemfig-") as tmp_dir:
            workdir = Path(tmp_dir)
            tex_path = workdir / "main.tex"
            tex_path.write_text(tex_content, encoding="utf-8")

            if latex_path:
                compile_args = [
                    latex_path,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-no-shell-escape",
                    tex_path.name,
                ]
            else:
                compile_args = [
                    xelatex_path,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-no-shell-escape",
                    "-no-pdf",
                    tex_path.name,
                ]

            result = subprocess.run(
                compile_args,
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                log_tail = _read_log_tail(workdir / "main.log")
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": "Chemfig 编译失败。",
                        "log": log_tail,
                        "exit_code": result.returncode,
                    },
                )

            dvi_path = workdir / "main.dvi"
            xdv_path = workdir / "main.xdv"
            pdf_path = workdir / "main.pdf"
            if dvi_path.exists():
                input_path = dvi_path
            elif xdv_path.exists():
                input_path = xdv_path
            else:
                input_path = pdf_path

            if not input_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "未生成 DVI/XDV/PDF 文件。",
                        "log": "",
                    },
                )

            svg_path = workdir / "main.svg"
            extra_args = os.getenv("DVISVGM_ARGS", "").strip().split()
            dvisvgm_args = [
                dvisvgm_path,
                "--page=1",
                "--no-fonts",
                "-o",
                svg_path.name,
                input_path.name,
                *extra_args,
            ]
            if input_path.suffix.lower() == ".pdf":
                dvisvgm_args.insert(1, "--pdf")

            svg_result = subprocess.run(
                dvisvgm_args,
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
            )

            if svg_result.returncode != 0 or not svg_path.exists():
                log_tail = _read_log_tail(workdir / "main.log")
                svg_stdout = _read_text_tail(svg_result.stdout or "")
                svg_stderr = _read_text_tail(svg_result.stderr or "")
                combined_log = "\n".join(
                    part
                    for part in [log_tail, "[dvisvgm stdout]", svg_stdout, "[dvisvgm stderr]", svg_stderr]
                    if part
                )
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Chemfig SVG 生成失败。",
                        "log": combined_log,
                        "exit_code": svg_result.returncode,
                    },
                )

            svg_bytes = svg_path.read_bytes()
            return Response(content=svg_bytes, media_type="image/svg+xml")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Chemfig 渲染异常: {exc}",
                "log": "",
            },
        ) from exc
