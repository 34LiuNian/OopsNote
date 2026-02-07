from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from starlette.responses import Response

from ..models import LatexCompileRequest

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


@router.post("/latex/compile")
def compile_latex(payload: LatexCompileRequest) -> Response:
    tex_content = _latex_template(payload.content, payload.title, payload.author)

    try:
        with tempfile.TemporaryDirectory(prefix="oopsnote-latex-") as tmp_dir:
            workdir = Path(tmp_dir)
            tex_path = workdir / "main.tex"
            tex_path.write_text(tex_content, encoding="utf-8")

            try:
                result = subprocess.run(
                    [
                        "xelatex",
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
                raise HTTPException(status_code=500, detail="未找到 xelatex，请先安装并加入 PATH。") from exc

            if result.returncode != 0:
                log_tail = _read_log_tail(workdir / "main.log")
                detail = "LaTeX 编译失败。"
                if log_tail:
                    detail = detail + "\n" + log_tail
                raise HTTPException(status_code=400, detail=detail)

            pdf_path = workdir / "main.pdf"
            if not pdf_path.exists():
                raise HTTPException(status_code=500, detail="未生成 PDF 文件。")

            pdf_bytes = pdf_path.read_bytes()
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": "inline; filename=latex.pdf"},
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LaTeX 编译异常: {exc}") from exc
