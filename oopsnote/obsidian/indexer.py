"""Obsidian 标签索引生成器。

聚合所有 Problem 的 knowledge_points/error_hypothesis，
按标签生成索引文件（如 二次函数.md），每条引用附带题目预览。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from oopsnote.core import Problem, TagStore

from .writer import (
    problem_filename,
    render_tag_index,
    subject_dir,
    tag_index_path,
    write_index_content,
)


def build_indexes(
    problems: list[Problem],
    vault_root: Path,
    tag_store: TagStore | None = None,
) -> list[Path]:
    """扫描所有 Problem，生成标签索引文件。

    返回所有写入的文件路径列表。
    """
    rendered = render_indexes(problems, vault_root, tag_store)
    for path, content in rendered:
        write_index_content(path, content)
    return [path for path, _content in rendered]


def render_indexes(
    problems: list[Problem],
    vault_root: Path,
    tag_store: TagStore | None = None,
) -> list[tuple[Path, str]]:
    """Build deterministic index content without mutating the vault.

    The synchronizer owns writes because it has the manifest hashes needed to
    distinguish an OopsNote update from a local Obsidian edit.
    """
    tag_to_problems: dict[str, list[tuple[str, Problem]]] = defaultdict(list)
    for problem in problems:
        for tag in [*problem.knowledge_points, *problem.error_hypothesis]:
            tag_to_problems[tag].append((problem.subject, problem))

    rendered: list[tuple[Path, str]] = []
    for tag_name, entries in tag_to_problems.items():
        by_subject: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for subject, problem in entries:
            by_subject[subject].append(
                (problem_filename(problem), _preview_text(problem.problem_text, max_len=40))
            )
        for subject, references in by_subject.items():
            aliases = None
            if tag_store:
                items = tag_store.search(query=tag_name, limit=1)
                if items and items[0].value == tag_name and items[0].aliases:
                    aliases = items[0].aliases
            rendered.append(
                (
                    tag_index_path(tag_name, vault_root, subject_dir(subject)),
                    render_tag_index(tag_name, references, aliases),
                )
            )
    return rendered


def _preview_text(text: str, max_len: int = 40) -> str:
    """截取题目文本预览（去除 LaTeX 标记，限制长度）。"""
    # 简单清理：去除 $$ 和 $ 标记
    clean = text.replace("$$", "").replace("$", "")
    # 去除多余的空白
    clean = " ".join(clean.split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."
