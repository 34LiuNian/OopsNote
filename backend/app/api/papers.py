from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

from ..api.latex import _compile_pdf, _find_xelatex
from ..models import PaperCompileRequest
from .deps import get_tasks_service

router = APIRouter()


def _tasks_service(request: Request):
    """Resolve task service from shared API dependencies."""
    return get_tasks_service(request)


def _paper_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "storage" / "papers"


def _paper_assets_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "storage" / "paper_assets"


# Template file paths
_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
_PAPER_TEMPLATE_PATH = _TEMPLATE_DIR / "paper.tex"
_SECTION_HEADERS_TEMPLATE_PATH = _TEMPLATE_DIR / "section_headers.tex"
_QUESTION_FORMATS_TEMPLATE_PATH = _TEMPLATE_DIR / "question_formats.tex"


def _load_template(path: Path) -> str:
    if not path.exists():
        raise HTTPException(
            status_code=500,
            detail={"message": f"模板文件不存在：{path.name}", "log": ""},
        )
    return path.read_text(encoding="utf-8")


def _load_paper_template() -> str:
    """Load main paper template with section_headers and question_formats inlined."""
    template = _load_template(_PAPER_TEMPLATE_PATH)
    
    # Read and inline section_headers.tex
    section_headers_content = _load_template(_SECTION_HEADERS_TEMPLATE_PATH)
    
    # Read and inline question_formats.tex
    question_formats_content = _load_template(_QUESTION_FORMATS_TEMPLATE_PATH)
    
    # Replace \input commands with actual content
    template = template.replace(
        "\\input{section_headers.tex}",
        "% ========== section_headers.tex (inlined) ==========\n"
        + section_headers_content
        + "% ========== end section_headers.tex ==========\n"
    )
    template = template.replace(
        "\\input{question_formats.tex}",
        "% ========== question_formats.tex (inlined) ==========\n"
        + question_formats_content
        + "% ========== end question_formats.tex ==========\n"
    )
    
    return template


def _norm_question_type(raw: Optional[str], has_choices: bool) -> str:
    if raw:
        label = str(raw).strip()
    else:
        label = "单选题" if has_choices else "解答题"

    if "多选" in label:
        return "多选题"
    if "单选" in label or ("选择" in label and "多" not in label):
        return "单选题"
    if "填空" in label:
        return "填空题"
    if "解答" in label or "证明" in label or "计算" in label:
        return "解答题"
    return "其它"


def _normalize_text(raw: str) -> str:
    text = raw or ""
    text = _convert_chemfig_markdown(text)
    # 避免替换 LaTeX 命令中的 \r, \n, \t（如 \right, \sqrt 等）
    # 只替换独立的转义序列（后面不是字母的）
    text = re.sub(r"\\n(?![a-zA-Z])", "\n", text)
    text = re.sub(r"\\r(?![a-zA-Z])", "\r", text)
    text = re.sub(r"\\t(?![a-zA-Z])", "\t", text)
    # Fix common OCR misses for tabular blocks.
    text = text.replace("\nbegin{tabular}", "\n\\begin{tabular}")
    text = text.replace("\nend{tabular}", "\n\\end{tabular}")

    out: list[str] = []
    in_math = False
    in_chemfig = False
    chemfig_brace_depth = 0
    chemfig_started = False
    i = 0
    while i < len(text):
        if not in_chemfig and text.startswith("\\chemfig", i):
            in_chemfig = True
            chemfig_brace_depth = 0
            chemfig_started = False
            out.append("\\chemfig")
            i += len("\\chemfig")
            continue

        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if ch == "\\" and nxt in "([":
            in_math = True
            out.append(ch)
            out.append(nxt)
            i += 2
            continue
        if ch == "\\" and nxt in ")]":
            in_math = False
            out.append(ch)
            out.append(nxt)
            i += 2
            continue
        if ch == "$":
            if nxt == "$":
                in_math = not in_math
                out.append("$$")
                i += 2
                continue
            in_math = not in_math
            out.append(ch)
            i += 1
            continue

        if in_chemfig:
            if ch == "{":
                chemfig_started = True
                chemfig_brace_depth += 1
            elif ch == "}" and chemfig_started:
                chemfig_brace_depth -= 1
                if chemfig_brace_depth <= 0:
                    in_chemfig = False
            out.append(ch)
            i += 1
            continue

        if not in_math and ch == "_":
            out.append("\\_")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _convert_chemfig_markdown(text: str) -> str:
    def normalize_content(raw: str) -> str:
        code = (raw or "").strip()
        if not code:
            return ""
        if code.lstrip().startswith("\\chemfig"):
            return code
        if code.lstrip().startswith("chemfig"):
            code = code.lstrip()[len("chemfig") :].lstrip()
        return f"\\chemfig{{{code}}}"

    text = re.sub(
        r"```chemfig\s*([\s\S]*?)```",
        lambda m: normalize_content(m.group(1)),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"`\s*chemfig\s+([^`]+)`",
        lambda m: normalize_content(m.group(1)),
        text,
        flags=re.IGNORECASE,
    )
    return text


def _build_question_block(text: str, options: Iterable[object] | None) -> str:
    """Build question LaTeX block using template format."""
    body = _normalize_text(text).strip() if text else ""
    if options:
        rendered_options = []
        for opt in options:
            opt_text = getattr(opt, "text", "")
            rendered_options.append(f"\t\\item {_normalize_text(str(opt_text))}")
        choices_block = "\n".join(rendered_options)
        return (
            "\\begin{question}\n"
            + "\t" + body
            + "\n\t\\begin{choices}\n"
            + choices_block
            + "\n\t\\end{choices}\n"
            + "\\end{question}\n"
        )
    # Fill-in question: add \fillinBlank placeholder
    return "\\begin{question}\n\t" + body + "\\fillinBlank{答案}.\n\\end{question}\n"


def _build_problem_block(text: str, points: int = 15, is_last: bool = False) -> str:
    """Build problem (long answer) LaTeX block with points and spacing."""
    body = _normalize_text(text).strip() if text else ""
    env = "problemWithLargeSpace" if is_last else "problemWithPoints"
    return f"\\begin{{{env}}}{{{points}}}\n{body}\n\\end{{{env}}}\n"


def _get_section_header(question_type: str, count: int, total_points: int = 0) -> str:
    """Get section header command with dynamic parameters.
    
    Args:
        question_type: Type of questions in this section
        count: Number of questions
        total_points: Total points for this section (used for 解答题)
    """
    if question_type == "单选题":
        return f"\\sectionSingleChoice[{count}]"
    elif question_type == "多选题":
        return f"\\sectionMultipleChoice[{count}]"
    elif question_type == "填空题":
        return f"\\sectionFillIn[{count}]"
    elif question_type == "解答题":
        return f"\\sectionProblem[{count}]{{{total_points}}}"
    else:
        return f"\\sectionOther[{count}]"


def _render_section(question_type: str, blocks: list[str], count: int, total_points: int = 0) -> str:
    """Render a section with header and question blocks.
    
    Args:
        question_type: Type of questions in this section
        blocks: List of LaTeX question blocks
        count: Number of questions
        total_points: Total points for this section (used for 解答题)
    """
    if not blocks:
        return ""
    header_cmd = _get_section_header(question_type, count, total_points)
    return f"{header_cmd}\n" + "\n".join(blocks) + "\n"


def _paper_template(
    *,
    title: str,
    show_answers: bool,
    sections: list[tuple[str, list[str]]],
) -> str:
    """Build final LaTeX document using template system."""
    template = _load_paper_template()
    
    # Build sections content (with headers included)
    sections_content = []
    
    for sec_title, blocks in sections:
        if blocks:
            # Get count of questions in this section
            count = len(blocks)
            # Calculate total points for 解答题 (default: 15 points per problem)
            total_points = 0
            if sec_title == "解答题":
                # Default 15 points per problem, can be customized
                total_points = count * 15
            
            # Add section content (header is included in _render_section)
            sections_content.append(_render_section(sec_title, blocks, count, total_points))
    
    # Join sections with proper spacing
    sections_text = "\n\n".join(sections_content)
    
    return (
        template.replace("{{TITLE}}", title)
        .replace("{{SHOW_ANSWERS}}", "true" if show_answers else "false")
        .replace("{{SECTIONS}}", sections_text)
    )


@router.post("/papers/compile")
def compile_paper(request: Request, payload: PaperCompileRequest) -> Response:
    svc = _tasks_service(request)

    if not payload.items:
        raise HTTPException(
            status_code=400, detail={"message": "请选择至少一道题目。", "log": ""}
        )

    # 调试日志：打印请求信息
    print(f"[PAPER] 收到组卷请求：{len(payload.items)} 道题目")
    for idx, item in enumerate(payload.items):
        print(f"  [{idx+1}] task_id={item.task_id}, problem_id={item.problem_id}")

    tasks_by_id = {t.id: t for t in svc.iter_tasks()}
    print(f"[PAPER] 当前任务数：{len(tasks_by_id)}")
    
    # First pass: collect all problems by type with their metadata
    problems_by_type: dict[str, list[dict]] = {
        "单选题": [],
        "多选题": [],
        "填空题": [],
        "解答题": [],
        "其它": [],
    }

    processed_count = 0
    for item in payload.items:
        task = tasks_by_id.get(item.task_id)
        if not task:
            print(f"[PAPER] 警告：未找到任务 {item.task_id}")
            continue
        problem = next(
            (p for p in task.problems if p.problem_id == item.problem_id), None
        )
        if not problem:
            print(f"[PAPER] 警告：任务 {item.task_id} 中未找到题目 {item.problem_id}")
            continue
        processed_count += 1
        tag_result = next(
            (t for t in task.tags if t.problem_id == item.problem_id), None
        )
        raw_type = getattr(problem, "question_type", None) or getattr(
            tag_result, "question_type", None
        )
        question_type = _norm_question_type(raw_type, bool(problem.options))
        print(f"[PAPER] 处理题目 {item.problem_id}: 类型={question_type}")
        
        # Store problem data for second pass
        problems_by_type.setdefault(question_type, []).append({
            "problem_text": problem.problem_text or "",
            "options": problem.options,
            "problem_id": item.problem_id,
        })
    
    # Second pass: build LaTeX blocks with proper spacing
    sections_map: dict[str, list[str]] = {}
    for qtype, problems in problems_by_type.items():
        if not problems:
            continue
        blocks = []
        total_problems = len(problems)
        for idx, prob in enumerate(problems):
            is_last = (idx == total_problems - 1)
            if qtype in ("单选题", "多选题", "填空题"):
                block = _build_question_block(prob["problem_text"], prob["options"])
            elif qtype == "解答题":
                # Default 15 points, last problem gets larger spacing
                block = _build_problem_block(prob["problem_text"], points=15, is_last=is_last)
            else:
                block = _build_problem_block(prob["problem_text"], points=15, is_last=is_last)
            blocks.append(block)
        sections_map[qtype] = blocks

    sections: list[tuple[str, list[str]]] = []
    order = ["单选题", "多选题", "填空题", "解答题", "其它"]
    for label in order:
        blocks = sections_map.get(label, [])
        if blocks:
            title = label
            print(f"[PAPER] 章节 {title}: {len(blocks)} 道题")
            sections.append((title, blocks))

    print(f"[PAPER] 总共处理 {processed_count} 道题，生成 {len(sections)} 个章节")

    tex_content = _paper_template(
        title=payload.title or "试卷",
        show_answers=payload.show_answers,
        sections=sections,
    )
    
    # 调试：将生成的 LaTeX 内容写入临时文件
    # debug_path = Path(__file__).resolve().parents[2] / ".." / "_tmp" / "debug_paper.tex"
    # debug_path.parent.mkdir(parents=True, exist_ok=True)
    # debug_path.write_text(tex_content, encoding="utf-8")
    # print(f"[PAPER] 已写入调试文件：{debug_path}")

    xelatex_path = _find_xelatex()
    if not xelatex_path:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "未找到 xelatex，请先安装并加入 PATH 或设置 XELATEX_PATH。",
                "log": "",
            },
        )

    pdf_bytes = _compile_pdf(tex_content, xelatex_path=xelatex_path)

    paper_id = uuid.uuid4().hex
    meta = {
        "paper_id": paper_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": payload.title,
        "items": [i.model_dump() for i in payload.items],
    }
    paper_dir = _paper_dir()
    assets_dir = _paper_assets_dir()
    paper_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / f"{paper_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (assets_dir / f"{paper_id}.pdf").write_bytes(pdf_bytes)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline; filename=paper.pdf",
            "X-Paper-Id": paper_id,
        },
    )
