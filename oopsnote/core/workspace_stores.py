"""Workspace-bound Core stores.

The factory is the only composition point for user-owned JSON stores. Global
application settings and built-in catalogs intentionally stay outside this
object.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from oopsnote.catalog import KNOWLEDGE_TAGS_PATH, KNOWLEDGE_TREES_PATH

from .assets import AssetStore
from .store import (
    BatchProcessJobStore,
    BatchSessionStore,
    PaperDraftStore,
    ProblemMergeStore,
    RunStore,
    TaskStore,
)
from .tags import TagStore
from .workspace import WorkspaceContext, WorkspaceId


@dataclass(frozen=True, slots=True)
class WorkspaceStores:
    """All currently user-owned stores rooted below one workspace directory."""

    task_store: TaskStore
    tag_store: TagStore
    asset_store: AssetStore
    batch_session_store: BatchSessionStore
    batch_process_job_store: BatchProcessJobStore
    paper_draft_store: PaperDraftStore
    problem_merge_store: ProblemMergeStore
    run_store: RunStore


class WorkspaceStoreFactory:
    """Build and cache stores only from a registry-derived context."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stores: dict[WorkspaceId, WorkspaceStores] = {}

    def for_context(self, context: WorkspaceContext) -> WorkspaceStores:
        key = context.workspace_id
        with self._lock:
            existing = self._stores.get(key)
            if existing is not None:
                return existing

            root = context.root
            settings = root / "settings"
            from oopsnote.control import ControlDatabase, QuotaAwareRunStore, QuotaService

            control_database = ControlDatabase(
                context.root.parent.parent / "control" / "app.sqlite"
            )
            quota = QuotaService(control_database)
            stores = WorkspaceStores(
                task_store=TaskStore(root / "tasks"),
                tag_store=TagStore(
                    user_path=settings / "tags_user.json",
                    builtin_path=KNOWLEDGE_TAGS_PATH,
                    tree_path=KNOWLEDGE_TREES_PATH,
                ),
                asset_store=AssetStore(root / "assets"),
                batch_session_store=BatchSessionStore(settings / "batch_sessions.json"),
                batch_process_job_store=BatchProcessJobStore(root / "batch_jobs"),
                paper_draft_store=PaperDraftStore(root / "papers"),
                problem_merge_store=ProblemMergeStore(settings / "problem_merges.json"),
                run_store=QuotaAwareRunStore(
                    root / "runs",
                    workspace_id=context.workspace_id,
                    quota=quota,
                ),
            )
            self._stores[key] = stores
            return stores
