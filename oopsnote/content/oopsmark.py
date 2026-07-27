"""Parser, validator, and LaTeX exporter for the OopsMark v1 contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class OopsMarkBlockKind(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    DISPLAY_MATH = "display_math"
    FENCE = "fence"
    TABLE = "table"
    LIST = "list"


@dataclass(frozen=True)
class OopsMarkBlock:
    kind: OopsMarkBlockKind
    content: str
    line: int
    language: Optional[str] = None
    rows: tuple[tuple[str, ...], ...] = ()
    ordered: bool = False


@dataclass(frozen=True)
class ContentIssue:
    code: str
    message: str
    line: int
    severity: str = "error"


class ContentExportError(ValueError):
    def __init__(self, code: str, message: str, line: int) -> None:
        super().__init__(message)
        self.code = code
        self.line = line


AssetResolver = Callable[[str, str], Optional[str]]

_ALLOWED_FENCES = {"molecule", "smiles", "tikz", "mermaid", "text"}
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_LIST_ITEM = re.compile(r"^(?P<indent>\s*)(?:(?P<number>\d+)[.)]|(?P<bullet>[-+*]))\s+(?P<text>.+)$")
_RAW_ENVIRONMENT = re.compile(r"\\(?:begin|end)\{(?P<name>tabular|array|tblr|enumerate|itemize|tikzpicture|document)\}")
_DOCUMENT_COMMAND = re.compile(r"\\(?:documentclass|usepackage|input|include|write18|openout|read)\b")
_OPTION_MARKER = re.compile(
    r"^\s*(?:"
    r"[（(]\s*(?:[A-Za-z]|\d{1,2})\s*[）)]"
    r"|(?:[A-Za-z]|\d{1,2})\s*[.．、:：)）\]】]"
    r")\s*"
)
_BARE_OPTION_MATH_COMMAND = re.compile(r"\\[A-Za-z]+")
_BARE_OPTION_MATH_BODY = re.compile(r"[A-Za-z0-9\\{}()[\]^_+\-*/=<>.,:;|!'\s]+")
_ORDERED_ITEM = re.compile(
    r"^(?P<indent>\s*)(?P<number>\d{1,2})[.．、)）]\s+(?P<text>.+)$"
)


def _split_table_row(line: str) -> tuple[str, ...]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    return tuple(cell.strip() for cell in value.split("|"))


def parse_oopsmark(source: str) -> list[OopsMarkBlock]:
    """Parse the block structure needed by both render targets.

    Inline Markdown remains in paragraph/table cells and is handled by the
    target adapter. This keeps the block parser deterministic and lossless.
    """

    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[OopsMarkBlock] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            start = index
            language = stripped[3:].strip().lower()
            body: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            blocks.append(
                OopsMarkBlock(
                    kind=OopsMarkBlockKind.FENCE,
                    content="\n".join(body),
                    line=start + 1,
                    language=language,
                )
            )
            continue

        if stripped.startswith("$$"):
            start = index
            after_open = stripped[2:]
            if after_open.endswith("$$") and len(after_open) >= 2:
                content = after_open[:-2].strip()
                index += 1
            else:
                body = [after_open] if after_open else []
                index += 1
                while index < len(lines):
                    candidate = lines[index]
                    if candidate.strip().endswith("$$"):
                        body.append(candidate[: candidate.rfind("$$")])
                        index += 1
                        break
                    body.append(candidate)
                    index += 1
                content = "\n".join(body).strip()
            blocks.append(OopsMarkBlock(OopsMarkBlockKind.DISPLAY_MATH, content, start + 1))
            continue

        if re.match(r"^#{1,6}\s+", stripped):
            marker, content = stripped.split(maxsplit=1)
            blocks.append(
                OopsMarkBlock(
                    kind=OopsMarkBlockKind.HEADING,
                    content=content,
                    line=index + 1,
                    language=str(len(marker)),
                )
            )
            index += 1
            continue

        if index + 1 < len(lines) and "|" in line and _TABLE_SEPARATOR.match(lines[index + 1]):
            start = index
            rows = [_split_table_row(line)]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_split_table_row(lines[index]))
                index += 1
            blocks.append(
                OopsMarkBlock(
                    kind=OopsMarkBlockKind.TABLE,
                    content="\n".join(lines[start:index]),
                    line=start + 1,
                    rows=tuple(rows),
                )
            )
            continue

        list_match = _LIST_ITEM.match(line)
        if list_match:
            start = index
            ordered = list_match.group("number") is not None
            items: list[str] = []
            while index < len(lines):
                item_match = _LIST_ITEM.match(lines[index])
                if not item_match or (item_match.group("number") is not None) != ordered:
                    break
                items.append(item_match.group("text"))
                index += 1
            blocks.append(
                OopsMarkBlock(
                    kind=OopsMarkBlockKind.LIST,
                    content="\n".join(items),
                    line=start + 1,
                    ordered=ordered,
                )
            )
            continue

        start = index
        paragraph = [line]
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip():
                break
            if candidate.strip().startswith(("```", "$$")):
                break
            if _LIST_ITEM.match(candidate):
                break
            if index + 1 < len(lines) and "|" in candidate and _TABLE_SEPARATOR.match(lines[index + 1]):
                break
            paragraph.append(candidate)
            index += 1
        blocks.append(OopsMarkBlock(OopsMarkBlockKind.PARAGRAPH, "\n".join(paragraph), start + 1))

    return blocks


def _unclosed_constructs(source: str) -> list[ContentIssue]:
    issues: list[ContentIssue] = []
    fence_line: Optional[int] = None
    display_line: Optional[int] = None
    for number, line in enumerate(source.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            fence_line = number if fence_line is None else None
            continue
        if fence_line is not None:
            continue
        if stripped.startswith("$$") or stripped.endswith("$$"):
            if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
                continue
            display_line = number if display_line is None else None
    if fence_line is not None:
        issues.append(ContentIssue("unclosed-fence", "代码块缺少结束围栏", fence_line))
    if display_line is not None:
        issues.append(ContentIssue("unclosed-display-math", "独立公式缺少结束 $$", display_line))
    return issues


def validate_oopsmark(source: str) -> list[ContentIssue]:
    issues = _unclosed_constructs(source)
    for block in parse_oopsmark(source):
        if block.kind == OopsMarkBlockKind.FENCE:
            language = block.language or ""
            if language not in _ALLOWED_FENCES:
                issues.append(ContentIssue("unsupported-fence", f"不支持的代码块类型：{language or '未标注'}", block.line))
            if language in {"molecule", "smiles", "tikz"} and not block.content.strip():
                issues.append(ContentIssue("empty-special-block", f"{language} 块不能为空", block.line))
            if _DOCUMENT_COMMAND.search(block.content):
                issues.append(ContentIssue("document-command", "内容块包含文档级或危险 TeX 命令", block.line))
            continue

        raw_environment = _RAW_ENVIRONMENT.search(block.content)
        if raw_environment:
            issues.append(
                ContentIssue(
                    "raw-latex-environment",
                    f"正文不能包含 {raw_environment.group('name')} 环境，请使用 OopsMark 对应块语法",
                    block.line,
                )
            )
        if _DOCUMENT_COMMAND.search(block.content):
            issues.append(ContentIssue("document-command", "正文包含文档级或危险 TeX 命令", block.line))
        if "\\chemfig" in block.content:
            issues.append(ContentIssue("chemfig-not-portable", "分子结构请使用 molecule 块，不要使用 chemfig", block.line))
        if block.kind != OopsMarkBlockKind.DISPLAY_MATH and "\\ce{" in block.content:
            for line_offset, line in enumerate(block.content.splitlines()):
                if "\\ce{" in line and "$" not in line:
                    issues.append(ContentIssue("chemistry-outside-math", "\\ce 必须放在数学分隔符内", block.line + line_offset))
        if block.kind in {OopsMarkBlockKind.PARAGRAPH, OopsMarkBlockKind.LIST, OopsMarkBlockKind.HEADING}:
            for line_offset, line in enumerate(block.content.splitlines()):
                unescaped_dollars = sum(
                    1 for index, char in enumerate(line)
                    if char == "$" and (index == 0 or line[index - 1] != "\\")
                )
                if unescaped_dollars % 2:
                    issues.append(ContentIssue("unclosed-inline-math", "行内公式缺少结束 $", block.line + line_offset))
    return issues


def normalize_oopsmark(source: str) -> str:
    """Normalize newlines in OopsMark v1 content.

    - Replaces CRLF/CR with LF.
    - Converts consecutive Markdown 1./2. items to canonical （1）/（2） subquestion paragraphs.
    - Collapses 3+ consecutive newlines to exactly \n\n (one blank line) outside fenced code blocks.
    - Strips leading/trailing whitespace.

    This keeps standard Markdown paragraph separation (\n\n) intact
    while eliminating unintended extra blank lines from AI output.
    Fenced code blocks (```…```) are preserved verbatim to avoid corrupting
    tikz, molecule, or mermaid content with intentional blank lines.
    """
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    _normalize_ordered_subquestions(lines)
    result: list[str] = []
    in_fence = False
    need_blank = False  # emit one blank line before next non-blank non-fence line

    for line in lines:
        if line.strip().startswith("```"):
            if need_blank:
                result.append("")
                need_blank = False
            result.append(line)
            in_fence = not in_fence
        elif in_fence:
            result.append(line)
        elif not line.strip():
            need_blank = True
        else:
            if need_blank:
                result.append("")
                need_blank = False
            result.append(line)

    # strip leading and trailing blank lines
    while result and result[0] == "":
        result.pop(0)
    while result and result[-1] == "":
        result.pop()

    return "\n".join(result)


def _normalize_ordered_subquestions(lines: list[str]) -> None:
    """Canonicalize consecutive 1./2. subquestions without touching a lone question number."""

    in_fence = False
    candidates: list[tuple[int, re.Match[str]]] = []

    def flush() -> None:
        nonlocal candidates
        numbers = [int(match.group("number")) for _, match in candidates]
        if len(numbers) >= 2 and numbers == list(range(1, len(numbers) + 1)):
            for line_index, match in candidates:
                lines[line_index] = (
                    f'{match.group("indent")}（{match.group("number")}）'
                    f'{match.group("text")}'
                )
        candidates = []

    for index, line in enumerate(lines):
        if line.strip().startswith("```"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue
        match = _ORDERED_ITEM.match(line)
        if match:
            expected = len(candidates) + 1
            if int(match.group("number")) == expected:
                candidates.append((index, match))
                continue
        flush()
        if match and match.group("number") == "1":
            candidates.append((index, match))
    flush()


def normalize_option_text(source: str) -> str:
    """Return canonical marker-free OopsMark for one ordered choice body."""

    normalized = _OPTION_MARKER.sub("", normalize_oopsmark(source), count=1).strip()
    if (
        "$" not in normalized
        and "\n" not in normalized
        and _BARE_OPTION_MATH_COMMAND.search(normalized)
        and _BARE_OPTION_MATH_BODY.fullmatch(normalized)
    ):
        return f"${normalized}$"
    return normalized


def option_label(index: int) -> str:
    """Map a zero-based choice position to its canonical A, B, ..., AA label."""

    if index < 0:
        raise ValueError("option index must be non-negative")
    value = index + 1
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


_LATEX_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}


def _escape_text(value: str) -> str:
    return "".join(_LATEX_ESCAPES.get(char, char) for char in value)


def _inline_to_latex(value: str) -> str:
    output: list[str] = []
    plain: list[str] = []
    index = 0

    def flush_plain() -> None:
        if plain:
            output.append(_escape_text("".join(plain)))
            plain.clear()

    while index < len(value):
        if value.startswith("**", index):
            end = value.find("**", index + 2)
            if end != -1:
                flush_plain()
                output.append(r"\textbf{" + _inline_to_latex(value[index + 2 : end]) + "}")
                index = end + 2
                continue
        if value[index] == "`":
            end = value.find("`", index + 1)
            if end != -1:
                flush_plain()
                output.append(r"\texttt{" + _escape_text(value[index + 1 : end]) + "}")
                index = end + 1
                continue
        if value[index] == "$" and (index == 0 or value[index - 1] != "\\"):
            end = index + 1
            while end < len(value):
                if value[end] == "$" and value[end - 1] != "\\":
                    break
                end += 1
            if end < len(value):
                flush_plain()
                output.append("$" + value[index + 1 : end] + "$")
                index = end + 1
                continue
        plain.append(value[index])
        index += 1
    flush_plain()
    return "".join(output)


def _asset_latex(language: str, source: str, line: int, resolver: Optional[AssetResolver]) -> str:
    asset_path = resolver(language, source) if resolver else None
    if not asset_path:
        raise ContentExportError(
            "missing-derived-asset",
            f"{language} 块需要派生图形资产才能导出试卷",
            line,
        )
    normalized_path = asset_path.replace("\\", "/")
    return "\n".join(
        [
            r"\begin{center}",
            r"\includegraphics[width=0.9\linewidth]{" + _escape_text(normalized_path) + "}",
            r"\end{center}",
        ]
    )


def to_latex(source: str, asset_resolver: Optional[AssetResolver] = None) -> str:
    """Convert valid OopsMark v1 source to a LaTeX document fragment."""

    issues = [issue for issue in validate_oopsmark(source) if issue.severity == "error"]
    if issues:
        first = issues[0]
        raise ContentExportError(first.code, first.message, first.line)

    output: list[str] = []
    for block in parse_oopsmark(source):
        if block.kind == OopsMarkBlockKind.HEADING:
            output.append(r"\par\medskip\noindent\textbf{" + _inline_to_latex(block.content) + r"}\par")
        elif block.kind == OopsMarkBlockKind.PARAGRAPH:
            lines = block.content.splitlines()
            output.append((r" \\" + "\n").join(_inline_to_latex(line) for line in lines))
        elif block.kind == OopsMarkBlockKind.DISPLAY_MATH:
            output.append("\\[\n" + block.content + "\n\\]")
        elif block.kind == OopsMarkBlockKind.LIST:
            environment = "enumerate" if block.ordered else "itemize"
            items = [f"\\item {_inline_to_latex(item)}" for item in block.content.splitlines()]
            output.append(f"\\begin{{{environment}}}\n" + "\n".join(items) + f"\n\\end{{{environment}}}")
        elif block.kind == OopsMarkBlockKind.TABLE:
            column_count = max((len(row) for row in block.rows), default=1)
            rows = [" & ".join(_inline_to_latex(cell) for cell in row) + r" \\" for row in block.rows]
            output.append(
                "\\begin{tblr}{colspec={" + "X" * column_count + "},hlines,vlines}\n"
                + "\n".join(rows)
                + "\n\\end{tblr}"
            )
        elif block.kind == OopsMarkBlockKind.FENCE:
            language = block.language or ""
            if language == "tikz":
                content = block.content.strip()
                if "\\begin{tikzpicture}" not in content:
                    content = "\\begin{tikzpicture}\n" + content + "\n\\end{tikzpicture}"
                output.append(content)
            elif language in {"molecule", "smiles", "mermaid"}:
                output.append(_asset_latex(language, block.content.strip(), block.line, asset_resolver))
            else:
                output.append("\\begin{verbatim}\n" + block.content + "\n\\end{verbatim}")
    return "\n\n".join(output)
