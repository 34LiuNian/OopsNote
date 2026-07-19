"""Obsidian .md 文件生成器。

每道 Problem → 一个 .md 文件（极简 frontmatter + wikilink）。
文件名：{date}-{short_id}.md，与 Problem.id 一一对应。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from oopsnote.core import Problem


# ── 学科与目录映射 ─────────────────────────────────

SUBJECT_DIR_MAP: dict[str, str] = {
    "数学": "maths",
    "物理": "physics",
    "化学": "chemical",
    "math": "maths",
    "physics": "physics",
    "chemistry": "chemical",
}


def subject_dir(subject: str) -> str:
    """学科中文/英文 → 目录名。"""
    return SUBJECT_DIR_MAP.get(subject, subject)


# ── 文件名生成 ──────────────────────────────────────

def problem_filename(problem: Problem, idx: Optional[int] = None) -> str:
    """生成日期-序号.md 文件名。"""
    date_str = problem.created_at.strftime("%Y-%m-%d")
    seq = problem.id[:6]
    return f"{date_str}-{seq}.md"


# ── .md 内容生成 ────────────────────────────────────

def _section(lines: list[str], heading: str, content_lines: list[str]) -> None:
    """追加一个带 heading 的区块，heading 与内容之间隔一个空行。"""
    if not content_lines:
        return
    lines.append(f"# {heading}")
    lines.append("")
    lines.extend(content_lines)
    lines.append("")


def render_problem(problem: Problem) -> str:
    """将单道 Problem 渲染为 Obsidian .md 内容。"""
    lines: list[str] = []

    # frontmatter
    lines.append("---")
    if problem.source:
        lines.append(f"source: \"{problem.source}\"")
    if problem.source_page is not None:
        lines.append(f"source_page: {problem.source_page}")
    date_str = problem.created_at.strftime("%Y-%m-%d")
    lines.append(f"date: {date_str}")
    lines.append("---")

    # 题目
    _section(lines, "题目", [problem.problem_text])

    # 选项
    if problem.options:
        opts: list[str] = [f"- {opt}" for opt in problem.options]
        _section(lines, "选项", opts)

    # 答案
    if problem.answer:
        _section(lines, "答案", [problem.answer])

    # 解析
    if problem.explanation:
        _section(lines, "解析", [problem.explanation])

    # wikilink 关联（知识点 + 错因）
    wiki_links: list[str] = []
    for kp in problem.knowledge_points:
        wiki_links.append(f"[[{kp}]]")
    for eh in problem.error_hypothesis:
        wiki_links.append(f"[[{eh}]]")
    if wiki_links:
        _section(lines, "关联", ["  ".join(wiki_links)])

    # 错因
    if problem.error_hypothesis:
        _section(lines, "错因", [f"- {eh}" for eh in problem.error_hypothesis])

    return "\n".join(lines)


# ── 写入文件 ────────────────────────────────────────

def write_problem(
    problem: Problem,
    vault_root: Path,
    subject: Optional[str] = None,
) -> Path:
    """将 Problem 写入 vault 目录，返回写入路径。"""
    subj = subject or problem.subject
    dir_name = subject_dir(subj)
    problems_dir = vault_root / dir_name / "problems"
    problems_dir.mkdir(parents=True, exist_ok=True)

    filename = problem_filename(problem)
    path = problems_dir / filename
    path.write_text(render_problem(problem), encoding="utf-8")
    return path


# ── Tag 索引文件 ────────────────────────────────────

def render_tag_index(
    tag_name: str,
    problem_refs: list[tuple[str, str]],
    aliases: Optional[list[str]] = None,
) -> str:
    """渲染标签索引页（如 二次函数.md）。"""
    lines: list[str] = []

    lines.append("---")
    lines.append("type: index")
    lines.append(f"ref_count: {len(problem_refs)}")
    if aliases:
        alias_str = ", ".join(f'"{a}"' for a in aliases)
        lines.append(f"aliases: [{alias_str}]")
    lines.append("---")
    lines.append("")

    lines.append(f"# {tag_name}")
    lines.append("")
    lines.append(f"> 共 {len(problem_refs)} 道相关题目")
    lines.append("")

    lines.append("## 相关题目")
    lines.append("")
    for ref, preview in problem_refs:
        lines.append(f"- [[{ref}]] — {preview}")
    lines.append("")

    return "\n".join(lines)


def write_tag_index(
    tag_name: str,
    problem_refs: list[tuple[str, str]],
    vault_root: Path,
    subject_dir_name: str,
    aliases: Optional[list[str]] = None,
) -> Path:
    """将标签索引写入 vault 目录。"""
    indexes_dir = vault_root / subject_dir_name / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)

    safe_name = tag_name.replace("/", "／").replace("\\", "／")
    path = indexes_dir / f"{safe_name}.md"
    path.write_text(
        render_tag_index(tag_name, problem_refs, aliases),
        encoding="utf-8",
    )
    return path
