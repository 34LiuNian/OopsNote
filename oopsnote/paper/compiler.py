"""Compile selected OopsMark problems into a PDF through a controlled XeLaTeX job."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from oopsnote.content import ContentExportError, to_latex
from oopsnote.core import ContentFormat, Problem


class PaperCompileError(RuntimeError):
    def __init__(self, message: str, log: str = "") -> None:
        super().__init__(message)
        self.log = log


def _escape_latex_text(value: str) -> str:
    escapes = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(escapes.get(char, char) for char in value)


def build_paper_tex(
    problems: list[Problem],
    *,
    title: str,
    subtitle: str = "",
    show_answers: bool = False,
) -> str:
    """Convert canonical OopsMark content to a complete, shell-escape-free TeX file."""
    items: list[str] = []
    for problem in problems:
        if problem.content_format != ContentFormat.OOPSMARK_V1:
            raise PaperCompileError(
                f"Problem {problem.id} uses {problem.content_format.value}; "
                "migrate it to oopsmark-v1 before export"
            )
        body = [rf"\item {to_latex(problem.problem_text)}"]
        if problem.options:
            body.append(
                "\\begin{enumerate}\n"
                "\\renewcommand{\\labelenumii}{\\Alph{enumii}.}"
            )
            body.extend(rf"\item {to_latex(option)}" for option in problem.options)
            body.append(r"\end{enumerate}")
        if show_answers:
            body.append(r"\par\noindent\textbf{答案：}" + to_latex(problem.answer))
            if problem.explanation:
                body.append(r"\par\noindent\textbf{解析：}" + to_latex(problem.explanation))
        items.append("\n".join(body))

    heading = [
        r"\begin{center}\Large\textbf{" + _escape_latex_text(title) + r"}\end{center}"
    ]
    if subtitle:
        heading.append(
            r"\begin{center}\large " + _escape_latex_text(subtitle) + r"\end{center}"
        )
    return "\n".join(
        [
            r"\documentclass[a4paper,11pt]{article}",
            r"\usepackage{ctex}",
            r"\usepackage{amsmath,amssymb}",
            r"\usepackage[version=4]{mhchem}",
            r"\usepackage{graphicx}",
            r"\usepackage{tikz}",
            r"\usepackage{tabularray}",
            r"\usepackage[margin=25mm]{geometry}",
            r"\begin{document}",
            *heading,
            r"\begin{enumerate}",
            *items,
            r"\end{enumerate}",
            r"\end{document}",
        ]
    )


def compile_paper_pdf(
    problems: list[Problem],
    *,
    title: str,
    subtitle: str = "",
    show_answers: bool = False,
    xelatex: str | None = None,
) -> bytes:
    executable = xelatex or shutil.which("xelatex")
    if not executable:
        raise PaperCompileError("XeLaTeX is not installed or is not on PATH")
    try:
        tex = build_paper_tex(
            problems,
            title=title,
            subtitle=subtitle,
            show_answers=show_answers,
        )
    except ContentExportError as error:
        raise PaperCompileError(
            f"OopsMark export failed at line {error.line}: {error}"
        ) from error

    with tempfile.TemporaryDirectory(prefix="oopsnote-paper-") as temp_name:
        temp_dir = Path(temp_name)
        tex_path = temp_dir / "paper.tex"
        tex_path.write_text(tex, encoding="utf-8")
        try:
            result = subprocess.run(
                [
                    executable,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-no-shell-escape",
                    tex_path.name,
                ],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
        except FileNotFoundError as error:
            raise PaperCompileError(f"XeLaTeX executable not found: {executable}") from error
        except subprocess.TimeoutExpired as error:
            raise PaperCompileError("XeLaTeX compilation timed out after 120 seconds") from error

        pdf_path = temp_dir / "paper.pdf"
        if result.returncode != 0 or not pdf_path.is_file():
            log = (result.stdout + "\n" + result.stderr)[-12_000:]
            raise PaperCompileError("XeLaTeX compilation failed", log)
        return pdf_path.read_bytes()


__all__ = ["PaperCompileError", "build_paper_tex", "compile_paper_pdf"]
