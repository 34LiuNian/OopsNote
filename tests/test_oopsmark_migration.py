from __future__ import annotations

import pytest

from oopsnote.core import ContentFormat, Problem, TaskCreateRequest, TaskStore
from scripts.migrate_oopsmark import migrate_storage


def test_migration_reports_blocks_and_applies_only_valid_records(tmp_path):
    store = TaskStore(tmp_path / "storage")
    ready_task = store.create(TaskCreateRequest(subject="math"))
    blocked_task = store.create(TaskCreateRequest(subject="math"))
    store.set_problem(ready_task.id, Problem(problem_text="题目", options=["A. x"], answer="A"))
    store.set_problem(
        blocked_task.id,
        Problem(problem_text=r"\begin{tabular}{cc}a&b\end{tabular}"),
    )

    report = migrate_storage(store.base_dir)

    assert report["mode"] == "report"
    assert report["ready"] == 1
    assert report["blocked"] == 1
    assert store.get(ready_task.id).problem.content_format == ContentFormat.LEGACY_MARKDOWN_LATEX

    applied = migrate_storage(store.base_dir, apply=True)

    assert applied["migrated"] == 1
    assert applied["blocked"] == 1
    assert store.get(ready_task.id).problem.content_format == ContentFormat.OOPSMARK_V1
    assert store.get(ready_task.id).problem.options == ["x"]
    assert store.get(blocked_task.id).problem.content_format == ContentFormat.LEGACY_MARKDOWN_LATEX
    assert migrate_storage(store.base_dir, apply=True)["migrated"] == 0


def test_migration_rejects_a_missing_storage_directory(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        migrate_storage(tmp_path / "missing")
