"""Obsidian 同步器 — JSON → Obsidian vault 单向同步。

流程：
1. 读取所有 Task 的 Problem
2. 写入 .md 文件到 vaults/{subject}/problems/
3. 重新生成标签索引文件到 vaults/{subject}/indexes/
4. 清理 vault 中已不存在于 JSON 中的旧文件
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from oopsnote.core import Problem, TagStore, TaskStore
from .writer import problem_filename, render_problem, subject_dir
from .indexer import build_indexes


class ObsidianSyncer:
    """JSON → Obsidian vault 单向同步器。"""

    def __init__(
        self,
        task_store: TaskStore,
        vault_root: Optional[Path] = None,
        tag_store: Optional[TagStore] = None,
    ) -> None:
        self.task_store = task_store
        self.tag_store = tag_store
        self.vault_root = vault_root or (
            Path(__file__).resolve().parents[2] / "vaults"
        )

    # ── 公共接口 ────────────────────────────────────

    def sync(self) -> SyncReport:
        """执行完整同步，返回报告。"""
        problems = self._collect_problems()
        report = SyncReport()

        # 1. 写入 .md 文件
        for p in problems:
            self._write_md(p, report)

        # 2. 生成标签索引
        index_paths = build_indexes(problems, self.vault_root, self.tag_store)
        report.indexes_written = len(index_paths)

        # 3. 清理幽灵文件
        stale = self._clean_stale_files(problems)
        report.files_removed = stale

        return report

    def sync_for_subject(self, subject: str) -> SyncReport:
        """仅同步指定学科。"""
        problems = [p for p in self._collect_problems() if p.subject == subject]
        report = SyncReport()

        for p in problems:
            self._write_md(p, report)

        dir_name = subject_dir(subject)
        index_paths = build_indexes(problems, self.vault_root, self.tag_store)
        report.indexes_written = len(index_paths)

        # 清理该学科目录
        problems_dir = self.vault_root / dir_name / "problems"
        if problems_dir.exists():
            current = {problem_filename(p) for p in problems}
            for f in problems_dir.glob("*.md"):
                if f.name not in current:
                    f.unlink()
                    report.files_removed += 1

        return report

    # ── 内部方法 ────────────────────────────────────

    def _collect_problems(self) -> list[Problem]:
        """从所有 Task 中收集 Problem。"""
        all_problems: list[Problem] = []
        for task in self.task_store.list_all():
            if task.problem:
                all_problems.append(task.problem)
        # 按创建时间去重排序
        seen: set[str] = set()
        unique: list[Problem] = []
        for p in sorted(all_problems, key=lambda p: p.created_at):
            if p.id not in seen:
                seen.add(p.id)
                unique.append(p)
        return unique

    def _write_md(self, problem: Problem, report: SyncReport) -> None:
        """写一个 Problem 的 .md 文件。"""
        dir_name = subject_dir(problem.subject)
        problems_dir = self.vault_root / dir_name / "problems"
        problems_dir.mkdir(parents=True, exist_ok=True)

        filename = problem_filename(problem)
        path = problems_dir / filename
        path.write_text(render_problem(problem), encoding="utf-8")
        report.files_written += 1

    def _clean_stale_files(self, current_problems: list[Problem]) -> int:
        """删除 vault 中不存在的 .md 文件。"""
        current_names = {problem_filename(p) for p in current_problems}
        removed = 0

        for subject_dir_path in self.vault_root.iterdir():
            problems_dir = subject_dir_path / "problems"
            if not problems_dir.exists():
                continue
            for f in problems_dir.glob("*.md"):
                if f.name not in current_names:
                    f.unlink()
                    removed += 1

        return removed


class SyncReport:
    """同步结果报告。"""

    def __init__(self) -> None:
        self.files_written: int = 0
        self.files_removed: int = 0
        self.indexes_written: int = 0

    def __str__(self) -> str:
        return (
            f"写入 {self.files_written} 个 .md 文件, "
            f"清理 {self.files_removed} 个过期文件, "
            f"生成 {self.indexes_written} 个标签索引"
        )
