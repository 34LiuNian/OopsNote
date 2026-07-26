"""Serialized, incremental JSON-to-Obsidian synchronization."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional
from uuid import uuid4

from oopsnote.core import Problem, TagStore, TaskStore

from .indexer import build_indexes
from .writer import problem_filename, render_problem, subject_dir


MANIFEST_NAME = ".oopsnote-managed.json"
MANAGED_MARKER = "oopsnote_managed: true"


class SyncReport:
    def __init__(self) -> None:
        self.files_written = 0
        self.files_removed = 0
        self.indexes_written = 0

    def __str__(self) -> str:
        return (
            f"写入 {self.files_written} 个题目文件，清理 {self.files_removed} 个受管文件，"
            f"生成 {self.indexes_written} 个索引"
        )


class ObsidianSyncer:
    """Write only OopsNote-owned files and serialize all vault mutations."""

    _sync_lock = threading.RLock()

    def __init__(
        self,
        task_store: TaskStore,
        vault_root: Optional[Path] = None,
        tag_store: Optional[TagStore] = None,
    ) -> None:
        self.task_store = task_store
        self.tag_store = tag_store
        self.vault_root = vault_root or Path(__file__).resolve().parents[2] / "vaults"

    def sync(self) -> SyncReport:
        """Explicit full sync, still constrained by per-subject managed manifests."""
        with self._sync_lock:
            report = SyncReport()
            subjects_by_directory = {
                subject_dir(problem.subject): problem.subject
                for problem in self._collect_problems()
            }
            if self.vault_root.exists():
                for manifest in self.vault_root.glob(f"*/{MANIFEST_NAME}"):
                    try:
                        payload = json.loads(manifest.read_text(encoding="utf-8"))
                        if payload.get("subject"):
                            subject = str(payload["subject"])
                            subjects_by_directory.setdefault(subject_dir(subject), subject)
                    except (OSError, ValueError):
                        # An unreadable ownership manifest must never authorize deletion.
                        continue
            for subject in sorted(subjects_by_directory.values()):
                current = self._sync_subject(subject, write_all=True)
                report.files_written += current.files_written
                report.files_removed += current.files_removed
                report.indexes_written += current.indexes_written
            return report

    def sync_for_subject(self, subject: str) -> SyncReport:
        with self._sync_lock:
            return self._sync_subject(subject, write_all=True)

    def sync_problem(self, problem: Problem) -> SyncReport:
        """Incrementally write one completed problem and rebuild only its subject indexes."""
        return self.sync_problems([problem])

    def sync_problems(self, problems: list[Problem]) -> SyncReport:
        """Write a coalesced set of problems and rebuild each affected subject once."""

        with self._sync_lock:
            report = SyncReport()
            grouped: dict[str, tuple[str, dict[str, Problem]]] = {}
            for problem in problems:
                directory = subject_dir(problem.subject)
                subject, items = grouped.setdefault(directory, (problem.subject, {}))
                items[problem.id] = problem
            for subject, items in grouped.values():
                current = self._sync_subject(
                    subject,
                    write_all=False,
                    changed=list(items.values()),
                )
                report.files_written += current.files_written
                report.files_removed += current.files_removed
                report.indexes_written += current.indexes_written
            return report

    def _sync_subject(
        self,
        subject: str,
        *,
        write_all: bool,
        changed: list[Problem] | None = None,
    ) -> SyncReport:
        directory_name = subject_dir(subject)
        problems = [
            problem
            for problem in self._collect_problems()
            if subject_dir(problem.subject) == directory_name
        ]
        report = SyncReport()
        subject_root = self.vault_root / directory_name
        manifest = self._read_manifest(subject_root)
        previous_problems = set(manifest.get("problem_files", []))
        previous_indexes = set(manifest.get("index_files", []))

        written_problem_names: set[str] = set()
        if write_all:
            for problem in problems:
                self._write_problem(problem)
                written_problem_names.add(problem_filename(problem))
                report.files_written += 1
        elif changed:
            for problem in changed:
                self._write_problem(problem)
                written_problem_names.add(problem_filename(problem))
            report.files_written = len(written_problem_names)

        current_problem_names = {problem_filename(problem) for problem in problems}
        if write_all:
            managed_problems = current_problem_names
        else:
            managed_problems = (previous_problems & current_problem_names) | written_problem_names

        index_paths = build_indexes(problems, self.vault_root, self.tag_store)
        current_indexes = {
            path.name
            for path in index_paths
            if path.parent == subject_root / "indexes"
        }
        report.indexes_written = len(current_indexes)
        report.files_removed += self._remove_managed(
            subject_root / "problems", previous_problems - current_problem_names
        )
        report.files_removed += self._remove_managed(
            subject_root / "indexes", previous_indexes - current_indexes
        )
        self._write_manifest(
            subject_root,
            {
                "version": 1,
                "subject": subject,
                "problem_files": sorted(managed_problems),
                "index_files": sorted(current_indexes),
            },
        )
        return report

    def _collect_problems(self) -> list[Problem]:
        seen: set[str] = set()
        problems: list[Problem] = []
        candidates = [task.problem for task in self.task_store.list_all() if task.problem]
        for problem in sorted(candidates, key=lambda item: item.created_at):
            if problem.id not in seen:
                seen.add(problem.id)
                problems.append(problem)
        return problems

    def _write_problem(self, problem: Problem) -> None:
        path = self.vault_root / subject_dir(problem.subject) / "problems" / problem_filename(problem)
        self._atomic_write(path, render_problem(problem))

    def _read_manifest(self, subject_root: Path) -> dict:
        path = subject_root / MANIFEST_NAME
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Invalid Obsidian ownership manifest: {path}") from error
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise RuntimeError(f"Unsupported Obsidian ownership manifest: {path}")
        return payload

    def _write_manifest(self, subject_root: Path, payload: dict) -> None:
        self._atomic_write(
            subject_root / MANIFEST_NAME,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _remove_managed(self, directory: Path, names: set[str]) -> int:
        removed = 0
        for name in names:
            path = directory / name
            try:
                if path.is_file() and MANAGED_MARKER in path.read_text(encoding="utf-8")[:2048]:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()


class ObsidianSyncQueue:
    """One daemon worker that coalesces repeated subject sync requests losslessly."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._pending: dict[
            tuple[str, str],
            tuple[ObsidianSyncer, dict[str, tuple[Problem, str | None]]],
        ] = {}
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        self.last_errors: dict[tuple[str, str], str] = {}

    def enqueue(
        self,
        syncer: ObsidianSyncer,
        problem: Problem,
        *,
        task_id: str | None = None,
    ) -> None:
        key = (str(syncer.vault_root.resolve()), subject_dir(problem.subject))
        with self._condition:
            _, pending = self._pending.setdefault(key, (syncer, {}))
            pending[problem.id] = (problem, task_id)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run,
                    name="oopsnote-obsidian-sync",
                    daemon=True,
                )
                self._thread.start()
            self._condition.notify()

    def _run(self) -> None:
        while True:
            with self._condition:
                if not self._pending:
                    self._condition.wait(timeout=1.0)
                    if not self._pending:
                        return
                key, (syncer, pending) = self._pending.popitem()
            items = list(pending.values())
            problems = [problem for problem, _ in items]
            task_ids = [task_id for _, task_id in items if task_id]
            try:
                syncer.sync_problems(problems)
                self.last_error = None
                self.last_errors.pop(key, None)
                self._update_tasks(syncer, task_ids, "AI 结果已写入；Obsidian 同步完成")
            except Exception as error:  # background failure remains observable
                self.last_error = str(error)
                self.last_errors[key] = str(error)
                self._update_tasks(
                    syncer,
                    task_ids,
                    f"AI 结果已写入；Obsidian 同步失败：{error}",
                )

    @staticmethod
    def _update_tasks(
        syncer: ObsidianSyncer,
        task_ids: list[str],
        message: str,
    ) -> None:
        for task_id in task_ids:
            try:
                syncer.task_store.update(task_id, stage_message=message)
            except (KeyError, OSError):
                continue


OBSIDIAN_SYNC_QUEUE = ObsidianSyncQueue()


__all__ = [
    "MANAGED_MARKER",
    "MANIFEST_NAME",
    "OBSIDIAN_SYNC_QUEUE",
    "ObsidianSyncQueue",
    "ObsidianSyncer",
    "SyncReport",
]
