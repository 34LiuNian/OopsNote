"""Persistence tests for the file-based task repository."""

from __future__ import annotations

import json
from pathlib import Path

from app.models import TaskCreateRequest
from app.repository import FileTaskRepository


def test_file_task_repository_persists_across_restarts(tmp_path: Path) -> None:
    """Ensures tasks are reloaded correctly after a restart."""
    repo1 = FileTaskRepository(base_dir=tmp_path)
    task = repo1.create(
        TaskCreateRequest(
            image_url="http://example.com/img.png",
            subject="math",
            grade="G8",
            notes="demo",
            mock_problem_count=1,
            user_tags=[],
        )
    )
    repo1.mark_processing(task.id)

    # Simulate process restart: new repo reading same directory.
    repo2 = FileTaskRepository(base_dir=tmp_path)
    loaded = repo2.get(task.id)
    assert loaded.id == task.id
    assert loaded.payload.subject == "math"
    assert loaded.status.value == "processing"


def test_file_task_repository_writes_valid_json(tmp_path: Path) -> None:
    """Ensures the repository writes valid JSON files."""
    repo = FileTaskRepository(base_dir=tmp_path)
    task = repo.create(
        TaskCreateRequest(
            image_url="http://example.com/img.png",
            subject="math",
            grade=None,
            notes=None,
            mock_problem_count=None,
            user_tags=[],
        )
    )

    path = tmp_path / f"{task.id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["id"] == task.id
    assert raw["payload"]["subject"] == "math"
