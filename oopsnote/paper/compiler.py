"""Deterministic PaperDocument to PDF compilation through controlled XeLaTeX."""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import httpx

from oopsnote.content import ContentExportError, to_latex

from .document import PaperDiagram, PaperDocument, PaperDocumentItem


class PaperCompileFailure(StrEnum):
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
    "compact": None,
    "standard": "35mm",
    "large": "65mm",
}
_PAPER_SIDE_MAX_WIDTH_EM = 14.0
_PAPER_BLOCK_MAX_WIDTH_EM = 39.0
_PAPER_SIDE_MAX_WIDTH_FRACTION = 0.4
_PAPER_IMAGE_BASE_WIDTH_FRACTION = 0.3


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
            PaperBundleFile(path, content) for path, content in sorted(self._files.items())
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
        _oopsmark_to_latex(option, item=item, bundle=bundle) for option in item.problem.options
    ]
    if len(options) == 4:
        boxes = [
            rf"\setbox{index}=\hbox{{{label}.\enspace {option}}}"
            for index, (label, option) in enumerate(zip("ABCD", options, strict=True))
        ]
        measure = [rf"\ifdim\wd{index}>\dimen0\dimen0=\wd{index}\fi" for index in range(4)]
        one_row = "".join(rf"\makebox[0.25\linewidth][l]{{\copy{index}}}" for index in range(4))
        two_rows = [
            "".join(rf"\makebox[0.5\linewidth][l]{{\copy{index}}}" for index in indices)
            for indices in ((0, 1), (2, 3))
        ]
        return "\n".join(
            [
                "{",
                *boxes,
                r"\dimen0=0pt",
                *measure,
                r"\ifdim\dimen0<0.24\linewidth",
                rf"\noindent{{{one_row}}}\par",
                r"\else\ifdim\dimen0<0.49\linewidth",
                rf"\noindent{{{two_rows[0]}}}\par",
                rf"\noindent{{{two_rows[1]}}}\par",
                r"\else",
                *[rf"\noindent\copy{index}\par" for index in range(4)],
                r"\fi\fi",
                "}",
            ]
        )
    enumerated = [rf"\item {option}" for option in options]
    return "\n".join(
        [
            "{",
            r"\begin{enumerate}",
            r"\renewcommand{\labelenumi}{\Alph{enumi}.}",
            r"\setlength{\itemsep}{2pt}",
            *enumerated,
            r"\end{enumerate}",
            "}",
        ]
    )


def _diagram_scale(diagram: PaperDiagram, diagram_scale_percent: int) -> float:
    return diagram.scale_adjustment_percent * diagram_scale_percent / 10_000


def _tikz_width_em(diagram: PaperDiagram, diagram_scale_percent: int) -> float:
    assert diagram.canvas_width_em is not None
    return diagram.canvas_width_em * _diagram_scale(diagram, diagram_scale_percent)


def _image_width_fraction(diagram: PaperDiagram, diagram_scale_percent: int) -> float:
    return _PAPER_IMAGE_BASE_WIDTH_FRACTION * _diagram_scale(diagram, diagram_scale_percent)


def _diagram_latex(
    diagram: PaperDiagram,
    bundle: _BundleBuilder,
    *,
    diagram_scale_percent: int,
    image_width: str | None = None,
) -> str:
    if diagram.kind == "tikz":
        width_em = _tikz_width_em(diagram, diagram_scale_percent)
        if width_em > _PAPER_BLOCK_MAX_WIDTH_EM:
            raise PaperCompileError(
                f"TikZ diagram width {width_em:g}em exceeds the printable question width",
                code=PaperCompileFailure.INVALID_CONTENT,
            )
        width = f"{width_em:g}em"
    else:
        width_fraction = _image_width_fraction(diagram, diagram_scale_percent)
        if width_fraction > 1:
            raise PaperCompileError(
                f"Image diagram width {width_fraction:g} of the line exceeds the printable question width",
                code=PaperCompileFailure.INVALID_CONTENT,
            )
        width = image_width or f"{width_fraction:g}\\linewidth"
    path = bundle.managed_asset(diagram.source)
    return rf"\includegraphics[width={width},keepaspectratio]{{{path}}}"


def _question_stem_latex(item: PaperDocumentItem, bundle: _BundleBuilder) -> str:
    problem = _oopsmark_to_latex(item.problem.problem_text, item=item, bundle=bundle)
    return rf"\noindent\textbf{{{item.number}.}}\quad {problem}{_format_points(item.points)}\par"


def _block_figure_latex(
    diagram: PaperDiagram,
    bundle: _BundleBuilder,
    *,
    align: str,
    diagram_scale_percent: int,
) -> str:
    alignment = {"left": "l", "center": "c", "right": "r"}[align]
    figure = _diagram_latex(
        diagram,
        bundle,
        diagram_scale_percent=diagram_scale_percent,
    )
    return rf"\noindent\makebox[\linewidth][{alignment}]{{{figure}}}\par"


def _side_question_latex(
    item: PaperDocumentItem,
    bundle: _BundleBuilder,
    diagram: PaperDiagram,
    *,
    diagram_scale_percent: int,
) -> str | None:
    placement = diagram.placement
    if placement.kind != "side":
        return None
    if diagram.kind == "tikz":
        width_em = _tikz_width_em(diagram, diagram_scale_percent)
        if width_em > _PAPER_SIDE_MAX_WIDTH_EM:
            return None
        figure_width = f"{width_em:g}em"
        figure_content = _diagram_latex(
            diagram,
            bundle,
            diagram_scale_percent=diagram_scale_percent,
        )
    else:
        width_fraction = _image_width_fraction(diagram, diagram_scale_percent)
        if width_fraction > _PAPER_SIDE_MAX_WIDTH_FRACTION:
            return None
        figure_width = f"{width_fraction:g}\\linewidth"
        figure_content = _diagram_latex(
            diagram,
            bundle,
            diagram_scale_percent=diagram_scale_percent,
            image_width=r"\linewidth",
        )
    figure = "\n".join(
        [
            rf"\begin{{minipage}}[t]{{{figure_width}}}",
            r"\vspace{0pt}",
            r"\centering",
            figure_content,
            r"\end{minipage}",
        ]
    )
    text_width = rf"\dimexpr\linewidth-{figure_width}-1em\relax"
    text = "\n".join(
        [
            rf"\begin{{minipage}}[t]{{{text_width}}}",
            r"\vspace{0pt}",
            _question_stem_latex(item, bundle),
            r"\end{minipage}",
        ]
    )
    lead = (
        "\n".join([figure, r"\hfill", text])
        if placement.side == "left"
        else "\n".join([text, r"\hfill", figure])
    )
    options = _options_latex(item, bundle)
    return "\n".join([lead, options] if options else [lead])


def _question_latex(
    item: PaperDocumentItem,
    bundle: _BundleBuilder,
    *,
    show_answers: bool,
    diagram_scale_percent: int,
) -> str:
    parts = [r"\par"]
    if item.diagram is None:
        parts.append(_question_stem_latex(item, bundle))
        options = _options_latex(item, bundle)
        if options:
            parts.append(options)
    else:
        side = _side_question_latex(
            item,
            bundle,
            item.diagram,
            diagram_scale_percent=diagram_scale_percent,
        )
        if side is not None:
            parts.append(side)
        else:
            placement = item.diagram.placement
            parts.append(_question_stem_latex(item, bundle))
            if placement.kind == "block" and placement.anchor == "after_stem":
                parts.append(
                    _block_figure_latex(
                        item.diagram,
                        bundle,
                        align=placement.align,
                        diagram_scale_percent=diagram_scale_percent,
                    )
                )
            options = _options_latex(item, bundle)
            if options:
                parts.append(options)
            if placement.kind == "side" or placement.anchor == "after_options":
                parts.append(
                    _block_figure_latex(
                        item.diagram,
                        bundle,
                        align=placement.side if placement.kind == "side" else placement.align,
                        diagram_scale_percent=diagram_scale_percent,
                    )
                )

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
        answer_space = _ANSWER_SPACE[item.answer_space]
        if item.question_type == "解答题" and answer_space:
            parts.append(rf"\par\vspace*{{{answer_space}}}")
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
            _question_latex(
                item,
                bundle,
                show_answers=document.show_answers,
                diagram_scale_percent=document.diagram_scale_percent,
            )
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
                stdout = (
                    error.stdout.decode("utf-8", "replace")
                    if isinstance(error.stdout, bytes)
                    else error.stdout or ""
                )
                stderr = (
                    error.stderr.decode("utf-8", "replace")
                    if isinstance(error.stderr, bytes)
                    else error.stderr or ""
                )
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
