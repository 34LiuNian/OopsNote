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
    """生成日期-序号.md 文件名。

    Problem.id → 取前 6 位作为序号。
    如果提供了 idx（同一天内的顺序），覆盖 uuid 前缀。
    """
    date_str = problem.created_at.strftime("%Y-%m-%d")
    seq = problem.id[:6]
    return f"{date_str}-{seq}.md"


# ── .md 内容生成 ────────────────────────────────────

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
    lines.append("")

    # 题目
    lines.append("# 题目")
    lines.append(problem.problem_text)
    lines.append("")

    # 选项
    if problem.options:
        for opt in problem.options:
            lines.append(f"- {opt}")
        lines.append("")

    # 答案
    if problem.answer:
        lines.append("# 答案")
        lines.append(problem.answer)
        lines.append("")

    # 解析
    if problem.explanation:
        lines.append("# 解析")
        lines.append(problem.explanation)
        lines.append("")

    # wikilink 关联（知识点 + 错因）
    wiki_links: list[str] = []
    for kp in problem.knowledge_points:
        wiki_links.append(f"[[{kp}]]")
    for eh in problem.error_hypothesis:
        wiki_links.append(f"[[{eh}]]")
    if wiki_links:
        lines.append("# 关联")
        lines.append("  ".join(wiki_links))
        lines.append("")

    # 错因
    if problem.error_hypothesis:
        lines.append("# 错因")
        for eh in problem.error_hypothesis:
            lines.append(f"- {eh}")
        lines.append("")

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
    problem_refs: list[tuple[str, str]],  # [(display_name_or_filename, problem_text_preview)]
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

    # 标签名中的特殊字符处理
    safe_name = tag_name.replace("/", "／").replace("\\", "／")
    path = indexes_dir / f"{safe_name}.md"
    path.write_text(
        render_tag_index(tag_name, problem_refs, aliases),
        encoding="utf-8",
    )
    return path
