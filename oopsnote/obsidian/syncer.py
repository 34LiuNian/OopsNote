"""Serialized, incremental JSON-to-Obsidian synchronization."""

from __future__ import annotations

import json
import hashlib
import threading
from pathlib import Path
from typing import Optional
from uuid import uuid4

from oopsnote.core import AssetStore, DiagramStatus, Problem, StateConflict, TagStore, TaskStatus, TaskStore

from .indexer import render_indexes
from .writer import problem_filename, render_problem, subject_dir


MANIFEST_NAME = ".oopsnote-managed.json"
MANAGED_MARKER = "oopsnote_managed: true"


class SyncReport:
    def __init__(self) -> None:
        self.files_written = 0
        self.files_removed = 0
        self.indexes_written = 0
        self.conflicts: list[str] = []

    def __str__(self) -> str:
        return (
            f"写入 {self.files_written} 个题目文件，清理 {self.files_removed} 个受管文件，"
            f"生成 {self.indexes_written} 个索引，检测到 {len(self.conflicts)} 个本地冲突"
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
        self.asset_store = AssetStore(task_store.base_dir / "assets")
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
                report.conflicts.extend(current.conflicts)
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
                report.conflicts.extend(current.conflicts)
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
        previous_problem_hashes = dict(manifest.get("problem_hashes", {}))
        previous_index_hashes = dict(manifest.get("index_hashes", {}))
        previous_assets = set(manifest.get("asset_files", []))
        previous_asset_hashes = dict(manifest.get("asset_hashes", {}))
        problem_ids = {problem.id for problem in problems}
        tasks_by_problem = {
            task.problem.id: task
            for task in self.task_store.list_all()
            if task.problem and task.problem.id in problem_ids
        }
        asset_plan: dict[str, bytes] = {}
        diagram_paths: dict[str, tuple[str, ...]] = {}
        for problem in problems:
            task = tasks_by_problem.get(problem.id)
            if task is None:
                continue
            embeds: list[str] = []
            for item in sorted(task.diagram_items, key=lambda value: value.ordinal):
                asset_path = None
                if item.status == DiagramStatus.READY_TIKZ and item.selected_candidate_id:
                    selected = next(
                        (candidate for candidate in item.candidates if candidate.id == item.selected_candidate_id),
                        None,
                    )
                    asset_path = selected.svg_path if selected else None
                elif item.status == DiagramStatus.READY_IMAGE:
                    asset_path = item.fallback_image_path
                if not asset_path:
                    continue
                try:
                    source = self.asset_store.resolve(asset_path)
                    content = source.read_bytes()
                except (FileNotFoundError, OSError, ValueError):
                    continue
                digest = hashlib.sha256(content).hexdigest()[:20]
                name = f"{digest}{source.suffix.lower()}"
                asset_plan[name] = content
                embeds.append(f"../assets/{name}")
            if embeds:
                diagram_paths[problem.id] = tuple(embeds)

        written_problem_names: set[str] = set()
        current_problem_hashes = {
            name: digest
            for name, digest in previous_problem_hashes.items()
            if name in previous_problems
        }
        if write_all:
            for problem in problems:
                filename = problem_filename(problem)
                content = render_problem(problem, diagram_paths.get(problem.id, ()))
                result = self._write_managed(
                    subject_root / "problems" / filename,
                    content,
                    previous_problem_hashes.get(filename),
                )
                if result == "conflict":
                    report.conflicts.append(f"problems/{filename}")
                else:
                    written_problem_names.add(filename)
                    current_problem_hashes[filename] = self._content_hash(content)
                    if result == "written":
                        report.files_written += 1
        elif changed:
            for problem in changed:
                filename = problem_filename(problem)
                content = render_problem(problem, diagram_paths.get(problem.id, ()))
                result = self._write_managed(
                    subject_root / "problems" / filename,
                    content,
                    previous_problem_hashes.get(filename),
                )
                if result == "conflict":
                    report.conflicts.append(f"problems/{filename}")
                else:
                    written_problem_names.add(filename)
                    current_problem_hashes[filename] = self._content_hash(content)
                    if result == "written":
                        report.files_written += 1

        current_problem_names = {problem_filename(problem) for problem in problems}
        if write_all:
            managed_problems = current_problem_names
        else:
            managed_problems = (previous_problems & current_problem_names) | written_problem_names

        current_assets = set(asset_plan)
        current_asset_hashes: dict[str, str] = {}
        for name, content in asset_plan.items():
            result = self._write_managed_bytes(
                subject_root / "assets" / name,
                content,
                previous_asset_hashes.get(name),
            )
            if result == "conflict":
                report.conflicts.append(f"assets/{name}")
            else:
                current_asset_hashes[name] = hashlib.sha256(content).hexdigest()
                if result == "written":
                    report.files_written += 1

        index_plan = [
            (path, content)
            for path, content in render_indexes(problems, self.vault_root, self.tag_store)
            if path.parent == subject_root / "indexes"
        ]
        current_indexes = {path.name for path, _content in index_plan}
        current_index_hashes = {
            name: digest
            for name, digest in previous_index_hashes.items()
            if name in previous_indexes
        }
        for path, content in index_plan:
            result = self._write_managed(path, content, previous_index_hashes.get(path.name))
            if result == "conflict":
                report.conflicts.append(f"indexes/{path.name}")
            else:
                current_index_hashes[path.name] = self._content_hash(content)
                if result == "written":
                    report.indexes_written += 1
        removed, conflicts = self._remove_managed(
            subject_root / "problems",
            previous_problems - current_problem_names,
            previous_problem_hashes,
        )
        report.files_removed += removed
        report.conflicts.extend(f"problems/{name}" for name in conflicts)
        removed, conflicts = self._remove_managed(
            subject_root / "indexes",
            previous_indexes - current_indexes,
            previous_index_hashes,
        )
        report.files_removed += removed
        report.conflicts.extend(f"indexes/{name}" for name in conflicts)
        removed, conflicts = self._remove_managed_assets(
            subject_root / "assets",
            previous_assets - current_assets,
            previous_asset_hashes,
        )
        report.files_removed += removed
        report.conflicts.extend(f"assets/{name}" for name in conflicts)
        self._write_manifest(
            subject_root,
            {
                "version": 2,
                "subject": subject,
                "problem_files": sorted(managed_problems),
                "index_files": sorted(current_indexes),
                "problem_hashes": {
                    name: digest
                    for name, digest in current_problem_hashes.items()
                    if name in managed_problems
                },
                "index_hashes": {
                    name: digest
                    for name, digest in current_index_hashes.items()
                    if name in current_indexes
                },
                "asset_files": sorted(current_assets),
                "asset_hashes": current_asset_hashes,
                "conflicts": sorted(set(report.conflicts)),
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

    def _write_managed(self, path: Path, content: str, expected_hash: Optional[str]) -> str:
        """Write only when the existing managed file has not been locally edited."""
        if not path.exists():
            self._atomic_write(path, content)
            return "written"
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            return "conflict"
        candidate_hash = self._content_hash(content)
        if self._content_hash(existing) == candidate_hash:
            return "unchanged"
        if (
            expected_hash
            and MANAGED_MARKER in existing[:2048]
            and self._content_hash(existing) == expected_hash
        ):
            self._atomic_write(path, content)
            return "written"
        return "conflict"

    def _write_managed_bytes(self, path: Path, content: bytes, expected_hash: Optional[str]) -> str:
        digest = hashlib.sha256(content).hexdigest()
        if not path.exists():
            self._atomic_write_bytes(path, content)
            return "written"
        try:
            existing_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return "conflict"
        if existing_hash == digest:
            return "unchanged"
        if expected_hash and existing_hash == expected_hash:
            self._atomic_write_bytes(path, content)
            return "written"
        return "conflict"

    def _read_manifest(self, subject_root: Path) -> dict:
        path = subject_root / MANIFEST_NAME
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RuntimeError(f"Invalid Obsidian ownership manifest: {path}") from error
        if not isinstance(payload, dict) or payload.get("version") not in {1, 2}:
            raise RuntimeError(f"Unsupported Obsidian ownership manifest: {path}")
        return payload

    def _write_manifest(self, subject_root: Path, payload: dict) -> None:
        self._atomic_write(
            subject_root / MANIFEST_NAME,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _remove_managed(
        self,
        directory: Path,
        names: set[str],
        expected_hashes: dict[str, str],
    ) -> tuple[int, list[str]]:
        removed = 0
        conflicts: list[str] = []
        for name in names:
            path = directory / name
            try:
                if not path.is_file():
                    continue
                content = path.read_text(encoding="utf-8")
                if (
                    MANAGED_MARKER in content[:2048]
                    and expected_hashes.get(name)
                    and self._content_hash(content) == expected_hashes[name]
                ):
                    path.unlink()
                    removed += 1
                else:
                    conflicts.append(name)
            except OSError:
                conflicts.append(name)
        return removed, conflicts

    @staticmethod
    def _remove_managed_assets(
        directory: Path,
        names: set[str],
        expected_hashes: dict[str, str],
    ) -> tuple[int, list[str]]:
        removed = 0
        conflicts: list[str] = []
        for name in names:
            path = directory / name
            try:
                if not path.is_file():
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if expected_hashes.get(name) == digest:
                    path.unlink()
                    removed += 1
                else:
                    conflicts.append(name)
            except OSError:
                conflicts.append(name)
        return removed, conflicts

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

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

    @staticmethod
    def _atomic_write_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(content)
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
            task_refs = [
                (task_id, problem.id)
                for problem, task_id in items
                if task_id
            ]
            try:
                report = syncer.sync_problems(problems)
                self.last_error = None
                self.last_errors.pop(key, None)
                message = (
                    "AI 结果已写入；Obsidian 同步完成"
                    if not report.conflicts
                    else f"AI 结果已写入；Obsidian 保留了 {len(report.conflicts)} 个本地修改，待人工处理"
                )
                self._update_tasks(syncer, task_refs, message)
            except Exception as error:  # background failure remains observable
                self.last_error = str(error)
                self.last_errors[key] = str(error)
                self._update_tasks(
                    syncer,
                    task_refs,
                    f"AI 结果已写入；Obsidian 同步失败：{error}",
                )

    @staticmethod
    def _update_tasks(
        syncer: ObsidianSyncer,
        task_refs: list[tuple[str, str]],
        message: str,
    ) -> None:
        for task_id, problem_id in task_refs:
            try:
                syncer.task_store.transition(
                    task_id,
                    expected_statuses={TaskStatus.COMPLETED},
                    expected_active_run_id=None,
                    expected_problem_id=problem_id,
                    stage_message=message,
                )
            except (KeyError, OSError, StateConflict):
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
