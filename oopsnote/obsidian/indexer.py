"""Obsidian 标签索引生成器。

聚合所有 Problem 的 knowledge_points/error_hypothesis，
按标签生成索引文件（如 二次函数.md），每条引用附带题目预览。
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

from oopsnote.core import Problem, TagItem, TagStore
from .writer import problem_filename, write_tag_index, subject_dir


def build_indexes(
    problems: list[Problem],
    vault_root: Path,
    tag_store: Optional[TagStore] = None,
) -> list[Path]:
    """扫描所有 Problem，生成标签索引文件。

    返回所有写入的文件路径列表。
    """
    # 聚合：tag → [(subject, problem)]
    tag_to_problems: dict[str, list[tuple[str, Problem]]] = defaultdict(list)

    for p in problems:
        for kp in p.knowledge_points:
            tag_to_problems[kp].append((p.subject, p))
        for eh in p.error_hypothesis:
            tag_to_problems[eh].append((p.subject, p))

    # 按学科分组写索引
    written: list[Path] = []

    for tag_name, entries in tag_to_problems.items():
        # 按学科分组
        by_subject: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for subject, p in entries:
            ref = problem_filename(p)
            preview = _preview_text(p.problem_text, max_len=40)
            by_subject[subject].append((ref, preview))

        # 写入每个学科
        for subject, refs in by_subject.items():
            dir_name = subject_dir(subject)

            # 查别名
            aliases = None
            if tag_store:
                items = tag_store.search(query=tag_name, limit=1)
                if items:
                    item = items[0]
                    if item.value == tag_name and item.aliases:
                        aliases = item.aliases

            path = write_tag_index(tag_name, refs, vault_root, dir_name, aliases)
            written.append(path)

    return written


def _preview_text(text: str, max_len: int = 40) -> str:
    """截取题目文本预览（去除 LaTeX 标记，限制长度）。"""
    # 简单清理：去除 $$ 和 $ 标记
    clean = text.replace("$$", "").replace("$", "")
    # 去除多余的空白
    clean = " ".join(clean.split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3] + "..."
