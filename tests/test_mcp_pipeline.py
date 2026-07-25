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
        "knowledge_points": ["判断元素能否构成集合"],
        "error_hypothesis": [],
    }


def test_finalize_validates_and_commits_managed_task(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="auto"))
    task_store.update(task.id, active_run_id="run-1")

    completed = server.finalize_task(
        task.id,
        json.dumps(valid_problem(), ensure_ascii=False),
        run_id="run-1",
        sync_to_obsidian=False,
        review_reason="multiple_questions",
    )

    assert completed.status.value == "completed"
    assert completed.subject == "math"
    assert completed.problem is not None
    assert completed.problem.short_answer == "$x=1$"
    assert completed.problem.content_format.value == "oopsmark-v1"
    assert completed.active_run_id is None
    assert completed.metadata["intake_review_reason"] == "multiple_questions"


def test_finalize_rejects_missing_answer_and_wrong_run(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, active_run_id="run-1")
    problem = valid_problem()
    problem["answer"] = ""

    with pytest.raises(ValueError, match="answer"):
        server.finalize_task(
            task.id,
            json.dumps(problem, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )
    with pytest.raises(ValueError, match="not active"):
        server.report_task_stage(task.id, "ocr", run_id="wrong-run")


def test_finalize_rejects_multiple_independent_problems(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, active_run_id="run-1")

    with pytest.raises(ValueError, match="JSON object"):
        server.finalize_task(
            task.id,
            json.dumps([valid_problem(), valid_problem()], ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )


def test_fail_task_persists_structured_review_reason(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="auto"))
    task_store.update(task.id, active_run_id="run-1")

    failed = server.fail_task(
        task.id,
        "题目区域被裁断",
        run_id="run-1",
        review_reason="incomplete",
    )

    assert failed.status.value == "failed"
    assert failed.metadata["intake_review_reason"] == "incomplete"

    with pytest.raises(ValueError, match="invalid review_reason"):
        server.fail_task(task.id, "bad", review_reason="unsupported")


def test_ai_tag_tool_requires_subject_for_knowledge(tmp_path, monkeypatch):
    configure_stores(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="subject is required"):
        server.list_tags(dimension="knowledge")


def test_ai_tag_tool_progressively_returns_branches_then_leaves(tmp_path, monkeypatch):
    configure_stores(tmp_path, monkeypatch)

    catalog = server.list_tags(dimension="knowledge", subject="math")
    branch_ids = [
        child["id"]
        for group in catalog["items"]
        for child in group["children"]
    ]
    leaves = server.list_tags(
        dimension="knowledge",
        subject="math",
        branch_ids=branch_ids[:6],
    )

    assert catalog["mode"] == "branches"
    assert catalog["max_branches"] == 6
    assert leaves["mode"] == "leaves"
    assert leaves["items"]
    assert all(isinstance(value, str) for value in leaves["items"])
    with pytest.raises(ValueError, match="between 1 and 6"):
        server.list_tags(
            dimension="knowledge",
            subject="math",
            branch_ids=branch_ids[:7],
        )


def test_finalize_rejects_non_leaf_knowledge_tag(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, active_run_id="run-1")
    problem = valid_problem()
    problem["knowledge_points"] = ["集合"]

    with pytest.raises(ValueError, match="only knowledge-tree leaf tags"):
        server.finalize_task(
            task.id,
            json.dumps(problem, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )


def test_managed_ai_cannot_create_knowledge_tag(tmp_path, monkeypatch):
    configure_stores(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="cannot create knowledge tags"):
        server.create_tag("knowledge", "自由生成标签", subject="math")

    server.create_tag("error", "忽略约束条件", subject="math")
    response = server.list_tags("error", subject="math")
    assert response["mode"] == "values"
    assert "忽略约束条件" in response["items"]
