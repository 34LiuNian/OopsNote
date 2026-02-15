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

router = APIRouter()


def _paper_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "storage" / "papers"


def _paper_assets_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "storage" / "paper_assets"


def _paper_template_path() -> Path:
    return Path(__file__).resolve().parents[1] / "templates" / "paper.tex"


def _load_paper_template() -> str:
    template_path = _paper_template_path()
    if not template_path.exists():
        raise HTTPException(
            status_code=500,
            detail={"message": "试卷模板文件不存在。", "log": ""},
        )
    return template_path.read_text(encoding="utf-8")


def _norm_question_type(raw: Optional[str], has_choices: bool) -> str:
    if raw:
        label = str(raw).strip()
    else:
        label = "选择题" if has_choices else "解答题"

    if "多选" in label:
        return "多选题"
    if "选择" in label:
        return "选择题"
    if "填空" in label:
        return "填空题"
    if "解答" in label or "证明" in label:
        return "解答题"
    return "其它"


def _normalize_text(raw: str) -> str:
    text = raw or ""
    text = _convert_chemfig_markdown(text)
    text = text.replace("\\n", "\n")
    text = text.replace("\\r", "\r")
    text = text.replace("\\t", "\t")
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
    body = _normalize_text(text).strip() if text else ""
    if options:
        rendered_options = []
        for opt in options:
            opt_text = getattr(opt, "text", "")
            rendered_options.append(f"\\item {_normalize_text(str(opt_text))}")
        choices_block = "\n".join(rendered_options)
        return (
            "\\begin{question}\n"
            + body
            + "\n\\begin{choices}\n"
            + choices_block
            + "\n\\end{choices}\n"
            + "\\end{question}\n"
        )
    return "\\begin{question}\n" + body + "\n\\end{question}\n"


def _build_problem_block(text: str) -> str:
    body = _normalize_text(text).strip() if text else ""
    return "\\begin{problem}\n" + body + "\n\\end{problem}\n"


def _render_section(title: str, blocks: list[str]) -> str:
    if not blocks:
        return ""
    header = f"\\section*{{{title}}}\\hangindent=2em\n"
    return header + "\n".join(blocks) + "\n"


def _paper_template(
    *,
    title: str,
    subtitle: Optional[str],
    show_answers: bool,
    sections: list[tuple[str, list[str]]],
) -> str:
    template = _load_paper_template()
    sections_text = "\n".join(
        _render_section(sec_title, blocks) for sec_title, blocks in sections if blocks
    )
    return (
        template.replace("{{TITLE}}", title)
        .replace("{{SUBTITLE}}", subtitle or "")
        .replace("{{SHOW_ANSWERS}}", "true" if show_answers else "false")
        .replace("{{SECTIONS}}", sections_text)
    )


@router.post("/papers/compile")
def compile_paper(request: Request, payload: PaperCompileRequest) -> Response:
    state = getattr(request.app.state, "oops", None)
    svc = getattr(state, "tasks", None)
    if svc is None:
        raise HTTPException(
            status_code=500, detail={"message": "任务服务不可用。", "log": ""}
        )

    if not payload.items:
        raise HTTPException(
            status_code=400, detail={"message": "请选择至少一道题目。", "log": ""}
        )

    tasks_by_id = {t.id: t for t in svc.repository.list_all().values()}
    sections_map: dict[str, list[str]] = {
        "选择题": [],
        "多选题": [],
        "填空题": [],
        "解答题": [],
        "其它": [],
    }

    for item in payload.items:
        task = tasks_by_id.get(item.task_id)
        if not task:
            continue
        problem = next(
            (p for p in task.problems if p.problem_id == item.problem_id), None
        )
        if not problem:
            continue
        tag_result = next(
            (t for t in task.tags if t.problem_id == item.problem_id), None
        )
        raw_type = getattr(problem, "question_type", None) or getattr(
            tag_result, "question_type", None
        )
        question_type = _norm_question_type(raw_type, bool(problem.options))
        if question_type in ("选择题", "多选题", "填空题"):
            block = _build_question_block(problem.problem_text or "", problem.options)
        elif question_type == "解答题":
            block = _build_problem_block(problem.problem_text or "")
        else:
            block = _build_problem_block(problem.problem_text or "")
        sections_map.setdefault(question_type, []).append(block)

    sections: list[tuple[str, list[str]]] = []
    order = ["选择题", "多选题", "填空题", "解答题", "其它"]
    for label in order:
        blocks = sections_map.get(label, [])
        if blocks:
            title = label
            sections.append((title, blocks))

    tex_content = _paper_template(
        title=payload.title or "试卷",
        subtitle=payload.subtitle or "",
        show_answers=payload.show_answers,
        sections=sections,
    )

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
        "subtitle": payload.subtitle,
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
