"""Deterministic PaperDocument to PDF compilation through controlled XeLaTeX."""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

import httpx

from oopsnote.content import ContentExportError, to_latex

from .document import PaperDiagram, PaperDocument, PaperDocumentItem


class PaperCompileFailure(str, Enum):
    INVALID_CONTENT = "invalid-content"
    MISSING_ASSET = "missing-asset"
    UNSUPPORTED_ASSET = "unsupported-asset"
    MISSING_ENGINE = "missing-engine"
    ENGINE_TIMEOUT = "engine-timeout"
    ENGINE_FAILED = "engine-failed"


class PaperCompileError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: PaperCompileFailure,
        log: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.log = log


@dataclass(frozen=True)
class PaperBundleFile:
    path: str
    content: bytes


@dataclass(frozen=True)
class PaperBundle:
    """The complete, transportable input to any local or remote TeX compiler."""

    tex: str
    files: tuple[PaperBundleFile, ...] = ()


AssetPathResolver = Callable[[str], Path]
DerivedAssetResolver = Callable[[str, str], Path | None]

_TEMPLATE_PATH = Path(__file__).with_name("templates") / "paper.tex"
_SUPPORTED_GRAPHICS = {".jpeg", ".jpg", ".pdf", ".png"}
_ANSWER_SPACE = {
    "compact": "12mm",
    "standard": "35mm",
    "large": "65mm",
}


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


def _chinese_number(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value % 10] if value % 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    return str(value)


def _format_points(points: float | None) -> str:
    if points is None:
        return ""
    value = str(int(points)) if points.is_integer() else f"{points:g}"
    return rf"\hfill\textbf{{（{_escape_latex_text(value)}分）}}"


class _BundleBuilder:
    def __init__(
        self,
        *,
        asset_path_resolver: AssetPathResolver | None,
        derived_asset_resolver: DerivedAssetResolver | None,
    ) -> None:
        self.asset_path_resolver = asset_path_resolver
        self.derived_asset_resolver = derived_asset_resolver
        self._files: dict[str, bytes] = {}

    @property
    def files(self) -> tuple[PaperBundleFile, ...]:
        return tuple(
            PaperBundleFile(path, content)
            for path, content in sorted(self._files.items())
        )

    def _register_path(self, path: Path, *, label: str) -> str:
        suffix = path.suffix.lower()
        if suffix not in _SUPPORTED_GRAPHICS:
            raise PaperCompileError(
                f"{label} uses unsupported TeX graphic format {suffix or '(none)'}; use PNG, JPEG, or PDF",
                code=PaperCompileFailure.UNSUPPORTED_ASSET,
            )
        try:
            content = path.read_bytes()
        except (FileNotFoundError, OSError) as error:
            raise PaperCompileError(
                f"{label} could not be read: {error}",
                code=PaperCompileFailure.MISSING_ASSET,
            ) from error
        digest = hashlib.sha256(content).hexdigest()[:20]
        relative = f"assets/{digest}{suffix}"
        self._files.setdefault(relative, content)
        return relative

    def managed_asset(self, asset_path: str) -> str:
        if self.asset_path_resolver is None:
            raise PaperCompileError(
                f"No managed-asset resolver is configured for {asset_path}",
                code=PaperCompileFailure.MISSING_ASSET,
            )
        try:
            path = self.asset_path_resolver(asset_path)
        except (FileNotFoundError, OSError, ValueError) as error:
            raise PaperCompileError(
                f"Managed paper asset {asset_path} is unavailable: {error}",
                code=PaperCompileFailure.MISSING_ASSET,
            ) from error
        return self._register_path(path, label=f"Managed paper asset {asset_path}")

    def derived_asset(self, kind: str, source: str) -> str | None:
        if self.derived_asset_resolver is None:
            return None
        try:
            path = self.derived_asset_resolver(kind, source)
        except (FileNotFoundError, OSError, ValueError) as error:
            raise PaperCompileError(
                f"Derived {kind} asset is unavailable: {error}",
                code=PaperCompileFailure.MISSING_ASSET,
            ) from error
        if path is None:
            return None
        return self._register_path(path, label=f"Derived {kind} asset")


def _oopsmark_to_latex(value: str, *, item: PaperDocumentItem, bundle: _BundleBuilder) -> str:
    try:
        return to_latex(value, asset_resolver=bundle.derived_asset)
    except ContentExportError as error:
        code = (
            PaperCompileFailure.MISSING_ASSET
            if error.code == "missing-derived-asset"
            else PaperCompileFailure.INVALID_CONTENT
        )
        raise PaperCompileError(
            f"Problem {item.problem.id} export failed at line {error.line}: {error}",
            code=code,
        ) from error


def _options_latex(item: PaperDocumentItem, bundle: _BundleBuilder) -> str:
    if not item.problem.options:
        return ""
    options = [
        rf"\item {_oopsmark_to_latex(option, item=item, bundle=bundle)}"
        for option in item.problem.options
    ]
    return "\n".join(
        [
            "{",
            r"\begin{enumerate}",
            r"\renewcommand{\labelenumi}{\Alph{enumi}.}",
            r"\setlength{\itemsep}{2pt}",
            *options,
            r"\end{enumerate}",
            "}",
        ]
    )


def _diagram_latex(diagram: PaperDiagram, bundle: _BundleBuilder) -> str:
    width = f"{diagram.scale_percent / 100:g}\\linewidth"
    if diagram.kind == "image":
        path = bundle.managed_asset(diagram.source)
        return rf"\includegraphics[width={width},keepaspectratio]{{{path}}}"
    source = diagram.source.strip()
    if "\\begin{tikzpicture}" not in source:
        source = "\\begin{tikzpicture}\n" + source + "\n\\end{tikzpicture}"
    return "\n".join(
        [
            rf"\resizebox{{{width}}}{{!}}{{%",
            source,
            "}",
        ]
    )


def _question_body_latex(item: PaperDocumentItem, bundle: _BundleBuilder) -> str:
    problem = _oopsmark_to_latex(item.problem.problem_text, item=item, bundle=bundle)
    parts = [
        rf"\noindent\textbf{{{item.number}.}}\quad {problem}{_format_points(item.points)}\par",
    ]
    options = _options_latex(item, bundle)
    if options:
        parts.append(options)
    return "\n".join(parts)


def _question_latex(item: PaperDocumentItem, bundle: _BundleBuilder, *, show_answers: bool) -> str:
    body = _question_body_latex(item, bundle)
    parts = [r"\par\medskip"]
    if item.diagram is None:
        parts.append(body)
    else:
        figure = "\n".join(
            [
                r"\begin{minipage}[t]{0.30\linewidth}",
                r"\centering",
                _diagram_latex(item.diagram, bundle),
                r"\end{minipage}",
            ]
        )
        text = "\n".join(
            [
                r"\begin{minipage}[t]{0.66\linewidth}",
                body,
                r"\end{minipage}",
            ]
        )
        parts.extend([figure, r"\hfill", text] if item.diagram.position == "left" else [text, r"\hfill", figure])

    if show_answers:
        parts.append(
            r"\par\smallskip\noindent\textbf{答案：}"
            + _oopsmark_to_latex(item.problem.answer, item=item, bundle=bundle)
        )
        if item.problem.explanation:
            parts.append(
                r"\par\noindent\textbf{解析：}"
                + _oopsmark_to_latex(item.problem.explanation, item=item, bundle=bundle)
            )
    else:
        parts.append(rf"\par\vspace*{{{_ANSWER_SPACE[item.answer_space]}}}")
    return "\n".join(parts)


def build_paper_bundle(
    document: PaperDocument,
    *,
    asset_path_resolver: AssetPathResolver | None = None,
    derived_asset_resolver: DerivedAssetResolver | None = None,
) -> PaperBundle:
    """Render one semantic document into a complete, transportable TeX bundle."""

    bundle = _BundleBuilder(
        asset_path_resolver=asset_path_resolver,
        derived_asset_resolver=derived_asset_resolver,
    )
    sections: list[str] = []
    for index, section in enumerate(document.sections, start=1):
        sections.append(
            rf"\par\bigskip\noindent{{\large\bfseries {_chinese_number(index)}、{_escape_latex_text(section.question_type)}}}\par\medskip"
        )
        sections.extend(
            _question_latex(item, bundle, show_answers=document.show_answers)
            for item in section.items
        )

    subtitle = ""
    if document.subtitle:
        subtitle = rf"{{\large {_escape_latex_text(document.subtitle)}\par}}"
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    tex = (
        template.replace("%%OOPSNOTE_TITLE%%", _escape_latex_text(document.title))
        .replace("%%OOPSNOTE_SUBTITLE%%", subtitle)
        .replace("%%OOPSNOTE_BODY%%", "\n".join(sections))
    )
    return PaperBundle(tex=tex, files=bundle.files)


def build_paper_tex(document: PaperDocument) -> str:
    """Build TeX for documents that do not require external graphic assets."""

    return build_paper_bundle(document).tex


def compile_paper_pdf(
    document: PaperDocument,
    *,
    asset_path_resolver: AssetPathResolver | None = None,
    derived_asset_resolver: DerivedAssetResolver | None = None,
    xelatex: str | None = None,
) -> bytes:
    bundle = build_paper_bundle(
        document,
        asset_path_resolver=asset_path_resolver,
        derived_asset_resolver=derived_asset_resolver,
    )
    renderer_url = os.getenv("OOPSNOTE_LATEX_RENDERER_URL", "").rstrip("/")
    if renderer_url:
        return _compile_remote_bundle(bundle, renderer_url)
    executable = xelatex or shutil.which("xelatex")
    if not executable:
        raise PaperCompileError(
            "XeLaTeX is not installed or is not on PATH",
            code=PaperCompileFailure.MISSING_ENGINE,
        )

    with tempfile.TemporaryDirectory(prefix="oopsnote-paper-") as temp_name:
        temp_dir = Path(temp_name)
        tex_path = temp_dir / "paper.tex"
        tex_path.write_text(bundle.tex, encoding="utf-8")
        for file in bundle.files:
            output = temp_dir / file.path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(file.content)

        job_environment = os.environ.copy()
        job_environment["openin_any"] = "p"
        job_environment["openout_any"] = "p"
        pdf_path = temp_dir / "paper.pdf"
        command = [
            executable,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-no-shell-escape",
            tex_path.name,
        ]
        deadline = time.monotonic() + 120
        logs: list[str] = []
        # Two passes are one compile protocol, not a retry: the second resolves
        # page totals and other references produced by the first pass.
        for pass_number in (1, 2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PaperCompileError(
                    "XeLaTeX compilation timed out after 120 seconds",
                    code=PaperCompileFailure.ENGINE_TIMEOUT,
                    log="\n".join(logs)[-12_000:],
                )
            try:
                result = subprocess.run(
                    command,
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=remaining,
                    check=False,
                    env=job_environment,
                )
            except FileNotFoundError as error:
                raise PaperCompileError(
                    f"XeLaTeX executable not found: {executable}",
                    code=PaperCompileFailure.MISSING_ENGINE,
                ) from error
            except subprocess.TimeoutExpired as error:
                stdout = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else error.stdout or ""
                stderr = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else error.stderr or ""
                logs.append(f"--- pass {pass_number} ---\n{stdout}\n{stderr}")
                raise PaperCompileError(
                    "XeLaTeX compilation timed out after 120 seconds",
                    code=PaperCompileFailure.ENGINE_TIMEOUT,
                    log="\n".join(logs)[-12_000:],
                ) from error
            logs.append(f"--- pass {pass_number} ---\n{result.stdout}\n{result.stderr}")
            if result.returncode != 0 or not pdf_path.is_file():
                raise PaperCompileError(
                    f"XeLaTeX compilation failed on pass {pass_number}",
                    code=PaperCompileFailure.ENGINE_FAILED,
                    log="\n".join(logs)[-12_000:],
                )
        return pdf_path.read_bytes()


def _compile_remote_bundle(bundle: PaperBundle, renderer_url: str) -> bytes:
    """Compile the immutable paper bundle in the configured renderer service.

    A configured service is authoritative. Failures are reported to callers;
    this must not silently switch engines and produce divergent paper output.
    """

    payload = {
        "tex": bundle.tex,
        "files": [
            {
                "path": file.path,
                "content_base64": base64.b64encode(file.content).decode("ascii"),
            }
            for file in bundle.files
        ],
    }
    try:
        response = httpx.post(
            f"{renderer_url}/v1/paper",
            json=payload,
            timeout=130,
        )
    except httpx.TimeoutException as error:
        raise PaperCompileError(
            "LaTeX renderer timed out after 120 seconds",
            code=PaperCompileFailure.ENGINE_TIMEOUT,
        ) from error
    except httpx.HTTPError as error:
        raise PaperCompileError(
            f"LaTeX renderer is unavailable: {error}",
            code=PaperCompileFailure.MISSING_ENGINE,
        ) from error
    if response.status_code == 504:
        raise PaperCompileError(
            "LaTeX renderer timed out after 120 seconds",
            code=PaperCompileFailure.ENGINE_TIMEOUT,
            log=response.text[-12_000:],
        )
    if response.status_code != 200:
        raise PaperCompileError(
            "LaTeX renderer failed to compile the paper",
            code=PaperCompileFailure.ENGINE_FAILED,
            log=response.text[-12_000:],
        )
    return response.content


__all__ = [
    "PaperBundle",
    "PaperBundleFile",
    "PaperCompileError",
    "PaperCompileFailure",
    "build_paper_bundle",
    "build_paper_tex",
    "compile_paper_pdf",
]
