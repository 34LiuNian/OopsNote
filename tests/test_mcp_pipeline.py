from __future__ import annotations

import json

import pytest

from oopsnote.core import TagStore, TaskCreateRequest, TaskStore
from oopsnote.mcp import server


def configure_stores(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    tag_store = TagStore(
        user_path=tmp_path / "storage" / "settings" / "tags_user.json",
        builtin_path=tmp_path / "storage" / "settings" / "tags_builtin.json",
    )
    monkeypatch.setattr(server, "TASK_STORE", task_store)
    monkeypatch.setattr(server, "TAG_STORE", tag_store)
    return task_store


def valid_problem():
    return {
        "content_format": "oopsmark-v1",
        "subject": "math",
        "question_type": "解答题",
        "problem_text": "求 $x+1=2$ 的解。",
        "answer": "$x=1$",
        "short_answer": "$x=1$",
        "explanation": "移项得 $x=1$。",
        "difficulty": "简单",
        "knowledge_points": ["一元一次方程"],
        "error_hypothesis": [],
    }


def test_finalize_validates_and_commits_managed_task(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="auto"))
    task_store.update(task.id, active_run_id="run-1")

    completed = server.finalize_task(
        task.id,
        json.dumps([valid_problem()], ensure_ascii=False),
        run_id="run-1",
        sync_to_obsidian=False,
    )

    assert completed.status.value == "completed"
    assert completed.subject == "math"
    assert completed.problems[0].short_answer == "$x=1$"
    assert completed.problems[0].content_format.value == "oopsmark-v1"
    assert completed.active_run_id is None


def test_finalize_rejects_missing_answer_and_wrong_run(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, active_run_id="run-1")
    problem = valid_problem()
    problem["answer"] = ""

    with pytest.raises(ValueError, match="answer"):
        server.finalize_task(
            task.id,
            json.dumps([problem], ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )
    with pytest.raises(ValueError, match="not active"):
        server.report_task_stage(task.id, "ocr", run_id="wrong-run")
