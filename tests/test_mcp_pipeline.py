from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from oopsnote.core import (
    RunStatus,
    RunStore,
    TagStore,
    TaskCreateRequest,
    TaskRun,
    TaskStage,
    TaskStatus,
    TaskStore,
)
from oopsnote.mcp import server
from oopsnote.mcp.restricted import managed_create_tag, managed_list_tags


def configure_stores(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    tag_store = TagStore(
        user_path=tmp_path / "storage" / "settings" / "tags_user.json",
        builtin_path=tmp_path / "storage" / "settings" / "tags_builtin.json",
    )
    monkeypatch.setattr(server, "TASK_STORE", task_store)
    monkeypatch.setattr(server, "TAG_STORE", tag_store)
    monkeypatch.setattr(server, "RUN_STORE", RunStore(tmp_path / "storage" / "runs"))
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


def advance_to_finalizing(
    task_id: str,
    run_id: str = "run-1",
    *,
    review_reason: str = "",
    student_response_status: str = "unknown",
    authorize_candidate_knowledge: bool = True,
) -> None:
    try:
        server.RUN_STORE.get(run_id)
    except KeyError:
        server.RUN_STORE._write(
            TaskRun(
                id=run_id,
                task_id=task_id,
                status=RunStatus.RUNNING,
            )
        )
    server.report_task_stage(task_id, "ocr", run_id=run_id)
    server.report_task_stage(task_id, "solving", run_id=run_id)
    server.submit_solution_candidate(
        task_id,
        json.dumps(valid_problem(), ensure_ascii=False),
        run_id=run_id,
        review_reason=review_reason,
        student_response_status=student_response_status,
    )
    server.RUN_STORE.begin_verification(run_id)
    server.report_task_stage(task_id, "verifying", run_id=run_id)
    server.report_task_stage(task_id, "tagging", run_id=run_id)
    if authorize_candidate_knowledge:
        authorize_knowledge_point(
            task_id,
            valid_problem()["knowledge_points"][0],
            run_id=run_id,
        )
    server.report_task_stage(task_id, "finalizing", run_id=run_id)


def authorize_knowledge_point(
    task_id: str,
    value: str,
    run_id: str = "run-1",
) -> None:
    catalog = server.list_tags(dimension="knowledge", subject="math")
    for group in catalog["items"]:
        for branch in group["children"]:
            leaves = server.list_tags(
                dimension="knowledge",
                subject="math",
                branch_ids=[branch["id"]],
            )["items"]
            if value in leaves:
                managed_list_tags(
                    dimension="knowledge",
                    task_id=task_id,
                    run_id=run_id,
                    subject="math",
                    branch_ids=[branch["id"]],
                )
                return
    raise AssertionError(f"No branch contains knowledge leaf {value}")


def test_solver_candidate_requires_a_runner_started_verifier_session(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    server.RUN_STORE._write(
        TaskRun(
            id="run-1",
            task_id=task.id,
            status=RunStatus.RUNNING,
        )
    )
    server.report_task_stage(task.id, "ocr", run_id="run-1")
    server.report_task_stage(task.id, "solving", run_id="run-1")
    server.submit_solution_candidate(
        task.id,
        json.dumps(valid_problem(), ensure_ascii=False),
        run_id="run-1",
    )

    with pytest.raises(ValueError, match="runner-started independent session"):
        server.report_task_stage(task.id, "verifying", run_id="run-1")


def test_solver_candidate_accepts_equivalent_localized_subject(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="数学"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    server.RUN_STORE._write(TaskRun(id="run-1", task_id=task.id, status=RunStatus.RUNNING))
    server.report_task_stage(task.id, "ocr", run_id="run-1")
    server.report_task_stage(task.id, "solving", run_id="run-1")

    result = server.submit_solution_candidate(
        task.id,
        json.dumps(valid_problem(), ensure_ascii=False),
        run_id="run-1",
    )

    assert result["candidate_submitted"] is True
    assert server.RUN_STORE.get("run-1").solution_candidate is not None

    task_store.update(task.id, stage=TaskStage.FINALIZING)
    with pytest.raises(ValueError, match="reviewed in an independent session"):
        server.finalize_task(
            task.id,
            json.dumps(valid_problem(), ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )

    server.RUN_STORE.begin_verification("run-1")
    task_store.update(task.id, stage=TaskStage.SOLVING)
    assert server.report_task_stage(task.id, "verifying", run_id="run-1")["stage"] == "verifying"


def test_task_run_cannot_deserialize_verification_without_a_candidate():
    with pytest.raises(ValueError, match="requires a solution_candidate"):
        TaskRun(
            task_id="task-1",
            verification_started_at=datetime.now(UTC),
        )


def test_solution_candidate_is_single_write_and_never_updates_the_task_problem(
    tmp_path, monkeypatch
):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    server.RUN_STORE._write(
        TaskRun(
            id="run-1",
            task_id=task.id,
            status=RunStatus.RUNNING,
        )
    )
    server.report_task_stage(task.id, "ocr", run_id="run-1")
    server.report_task_stage(task.id, "solving", run_id="run-1")
    payload = json.dumps(valid_problem(), ensure_ascii=False)

    submitted = server.submit_solution_candidate(task.id, payload, run_id="run-1")
    assert submitted["candidate_submitted"] is True
    assert task_store.get(task.id).problem is None
    stored_run = server.RUN_STORE.get("run-1")
    assert stored_run.solution_candidate is not None
    assert stored_run.artifacts[0].kind == "solver_candidate"
    assert stored_run.artifacts[0].raw_output == payload
    assert stored_run.artifacts[0].parsed_output["problem"]["answer"] == "$x=1$"

    with pytest.raises(ValueError, match="already has a solution candidate"):
        server.submit_solution_candidate(task.id, payload, run_id="run-1")
    assert task_store.get(task.id).problem is None


def test_finalize_validates_and_commits_managed_task(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="auto"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    advance_to_finalizing(task.id, review_reason="multiple_questions")

    result = server.finalize_task(
        task.id,
        json.dumps(valid_problem(), ensure_ascii=False),
        run_id="run-1",
        sync_to_obsidian=False,
        review_reason="multiple_questions",
    )

    completed = task_store.get(task.id)
    assert result == {
        "ok": True,
        "task_id": task.id,
        "status": "completed",
        "problem_id": completed.problem.id,
        "review_reason": "multiple_questions",
        "sync_queued": False,
    }
    assert completed.status.value == "completed"
    assert completed.subject == "math"
    assert completed.problem is not None
    assert completed.problem.short_answer == "$x=1$"
    assert completed.problem.content_format.value == "oopsmark-v1"
    assert completed.active_run_id is None
    assert completed.revision_count == 0
    assert completed.last_revised_at is None
    assert completed.metadata["intake_review_reason"] == "multiple_questions"
    artifacts = server.RUN_STORE.get("run-1").artifacts
    assert [artifact.kind for artifact in artifacts] == [
        "solver_candidate",
        "verifier_submission",
    ]
    assert artifacts[-1].raw_output == json.dumps(valid_problem(), ensure_ascii=False)
    assert artifacts[-1].parsed_output["short_answer"] == "$x=1$"


def test_repeated_finalize_is_rejected_without_rewriting_completed_result(
    tmp_path,
    monkeypatch,
):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="auto"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    advance_to_finalizing(task.id)
    server.finalize_task(
        task.id,
        json.dumps(valid_problem(), ensure_ascii=False),
        run_id="run-1",
        sync_to_obsidian=False,
    )
    committed = task_store.get(task.id)

    replacement = valid_problem()
    replacement["problem_text"] = "不应覆盖已提交结果。"
    with pytest.raises(ValueError, match="is not active"):
        server.finalize_task(
            task.id,
            json.dumps(replacement, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )

    current = task_store.get(task.id)
    assert current == committed
    assert current.status == TaskStatus.COMPLETED
    assert current.active_run_id is None


def test_finalize_sync_message_cannot_overwrite_newer_run(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="auto"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    advance_to_finalizing(task.id)

    class RacingQueue:
        @staticmethod
        def enqueue(_syncer, _problem, *, task_id):
            task_store.update(
                task_id,
                status=TaskStatus.PROCESSING,
                active_run_id="run-2",
                stage=TaskStage.SOLVING,
                stage_message="new run solving",
            )

    monkeypatch.setattr(server, "OBSIDIAN_SYNC_QUEUE", RacingQueue())

    result = server.finalize_task(
        task.id,
        json.dumps(valid_problem(), ensure_ascii=False),
        run_id="run-1",
        sync_to_obsidian=True,
    )

    assert result["sync_queued"] is True
    current = task_store.get(task.id)
    assert current.status == TaskStatus.PROCESSING
    assert current.active_run_id == "run-2"
    assert current.stage_message == "new run solving"


def test_finalize_enforces_subject_and_enriches_trusted_source(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(
        TaskCreateRequest(
            subject="math",
            metadata={"source": "卷一.pdf", "source_page": 2},
        )
    )
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    advance_to_finalizing(task.id)

    wrong_subject = valid_problem()
    wrong_subject["subject"] = "physics"
    with pytest.raises(ValueError, match="does not match task subject"):
        server.finalize_task(
            task.id,
            json.dumps(wrong_subject, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )

    server.finalize_task(
        task.id,
        json.dumps(valid_problem(), ensure_ascii=False),
        run_id="run-1",
        sync_to_obsidian=False,
    )
    problem = task_store.get(task.id).problem
    assert problem is not None
    assert problem.source == "卷一.pdf"
    assert problem.source_page == 2


def test_finalize_rejects_missing_answer_and_wrong_run(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    problem = valid_problem()
    problem["answer"] = ""
    advance_to_finalizing(task.id)

    with pytest.raises(ValueError, match="answer"):
        server.finalize_task(
            task.id,
            json.dumps(problem, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )
    validation_error = server.RUN_STORE.get("run-1").validation_errors[-1]
    assert validation_error.stage == TaskStage.FINALIZING
    assert validation_error.raw_output == json.dumps(problem, ensure_ascii=False)
    assert "answer" in validation_error.message
    with pytest.raises(ValueError, match="not active"):
        server.report_task_stage(task.id, "ocr", run_id="wrong-run")


def test_finalize_rejects_answer_derivation_without_consuming_the_active_run(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    problem = valid_problem()
    problem["answer"] = "因为 $x+1=2$，所以 $x=1$。"
    advance_to_finalizing(task.id)

    with pytest.raises(ValueError, match="answer-contains-derivation"):
        server.finalize_task(
            task.id,
            json.dumps(problem, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )

    unchanged = task_store.get(task.id)
    assert unchanged.status == TaskStatus.PROCESSING
    assert unchanged.active_run_id == "run-1"


def test_finalize_rejects_multiple_independent_problems(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    advance_to_finalizing(task.id, authorize_candidate_knowledge=False)

    with pytest.raises(ValueError, match="JSON object"):
        server.finalize_task(
            task.id,
            json.dumps([valid_problem(), valid_problem()], ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )


def test_finalize_rejects_invented_error_for_unanswered_question(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    problem = valid_problem()
    problem["knowledge_points"] = []
    problem["error_hypothesis"] = ["计算失误"]
    advance_to_finalizing(task.id, student_response_status="unanswered")

    with pytest.raises(ValueError, match="readable student response"):
        server.finalize_task(
            task.id,
            json.dumps(problem, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
            student_response_status="unanswered",
        )


def test_finalize_allows_no_error_for_unanswered_question(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    problem = valid_problem()
    problem["knowledge_points"] = []
    advance_to_finalizing(task.id, student_response_status="unanswered")

    server.finalize_task(
        task.id,
        json.dumps(problem, ensure_ascii=False),
        run_id="run-1",
        sync_to_obsidian=False,
        student_response_status="unanswered",
    )

    completed = task_store.get(task.id)
    assert completed.problem is not None
    assert completed.problem.error_hypothesis == []
    assert completed.metadata["student_response_status"] == "unanswered"


def test_finalize_preserves_user_provided_error_for_unanswered_question(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(
        TaskCreateRequest(
            subject="math",
            metadata={"error_tags": ["计算失误"]},
        )
    )
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    server.create_tag("error", "计算失误", subject="math")
    problem = valid_problem()
    problem["knowledge_points"] = []
    problem["error_hypothesis"] = ["计算失误"]
    advance_to_finalizing(task.id, student_response_status="unanswered")

    server.finalize_task(
        task.id,
        json.dumps(problem, ensure_ascii=False),
        run_id="run-1",
        sync_to_obsidian=False,
        student_response_status="unanswered",
    )

    completed = task_store.get(task.id)
    assert completed.problem is not None
    assert completed.problem.error_hypothesis == ["计算失误"]


def test_fail_task_persists_structured_review_reason(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="auto"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")

    result = server.fail_task(
        task.id,
        "题目区域被裁断",
        run_id="run-1",
        review_reason="incomplete",
    )

    failed = task_store.get(task.id)
    assert result == {
        "ok": True,
        "task_id": task.id,
        "status": "failed",
        "review_reason": "incomplete",
    }
    assert failed.status.value == "failed"
    assert failed.last_error_code == "pipeline_failed"
    assert failed.metadata["intake_review_reason"] == "incomplete"

    another = task_store.create(TaskCreateRequest(subject="auto"))
    task_store.update(
        another.id,
        status=TaskStatus.PROCESSING,
        active_run_id="run-2",
    )
    with pytest.raises(ValueError, match="invalid review_reason"):
        server.fail_task(
            another.id,
            "bad",
            run_id="run-2",
            review_reason="unsupported",
        )


def test_ai_tag_tool_requires_subject_for_knowledge(tmp_path, monkeypatch):
    configure_stores(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="subject is required"):
        server.list_tags(dimension="knowledge")


def test_managed_task_and_stage_results_are_compact(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(
        TaskCreateRequest(
            subject="math",
            asset_path="/assets/question.png",
            metadata={
                "question_no": "12",
                "source": "test.pdf · 第 2 页",
                "trace": {"large": "must not leak into agent context"},
            },
        )
    )
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")

    context = server.get_task(task.id, "run-1")
    stage = server.report_task_stage(task.id, "ocr", "run-1", "OCR")

    assert context["task_id"] == task.id
    assert context["question_no"] == "12"
    assert "metadata" not in context
    assert "trace" not in json.dumps(context, ensure_ascii=False)
    assert stage == {
        "ok": True,
        "task_id": task.id,
        "status": "processing",
        "stage": "ocr",
    }

    with pytest.raises(ValueError, match="cannot follow"):
        server.report_task_stage(task.id, "tagging", "run-1")


def test_ai_tag_tool_progressively_returns_branches_then_leaves(tmp_path, monkeypatch):
    configure_stores(tmp_path, monkeypatch)

    catalog = server.list_tags(dimension="knowledge", subject="math")
    localized_catalog = server.list_tags(dimension="knowledge", subject="数学")
    branch_ids = [child["id"] for group in catalog["items"] for child in group["children"]]
    leaves = server.list_tags(
        dimension="knowledge",
        subject="math",
        branch_ids=branch_ids[:6],
    )

    assert catalog["mode"] == "branches"
    assert localized_catalog == catalog
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
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    problem = valid_problem()
    problem["knowledge_points"] = ["集合"]
    advance_to_finalizing(task.id, authorize_candidate_knowledge=False)

    with pytest.raises(ValueError, match="require branches selected"):
        server.finalize_task(
            task.id,
            json.dumps(problem, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )


def test_finalize_tag_rejection_reports_authorized_leaf_values(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    advance_to_finalizing(task.id)
    problem = valid_problem()
    problem["knowledge_points"] = ["集合"]

    with pytest.raises(ValueError) as captured:
        server.finalize_task(
            task.id,
            json.dumps(problem, ensure_ascii=False),
            run_id="run-1",
            sync_to_obsidian=False,
        )

    message = str(captured.value)
    assert "invalid: 集合" in message
    assert "allowed leaves:" in message
    assert valid_problem()["knowledge_points"][0] in message


def test_managed_ai_cannot_create_knowledge_tag(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="cannot create knowledge tags"):
        server.create_tag("knowledge", "自由生成标签", subject="math")

    server.create_tag("error", "忽略约束条件", subject="math")
    response = server.list_tags("error", subject="math")
    assert response["mode"] == "values"
    assert "忽略约束条件" in response["items"]

    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    with pytest.raises(ValueError, match="only error tags"):
        managed_create_tag(
            dimension="meta",
            value="越权来源",
            task_id=task.id,
            run_id="run-1",
            subject="math",
        )
    advance_to_finalizing(task.id)
    with pytest.raises(ValueError, match="list existing error tags"):
        managed_create_tag(
            dimension="error",
            value="忽略端点",
            task_id=task.id,
            run_id="run-1",
            subject="math",
        )
    managed_list_tags(
        dimension="error",
        task_id=task.id,
        run_id="run-1",
        subject="math",
    )
    managed_create_tag(
        dimension="error",
        value="忽略端点",
        task_id=task.id,
        run_id="run-1",
        subject="math",
    )
    with pytest.raises(ValueError, match="matches existing candidate"):
        managed_create_tag(
            dimension="error",
            value="忽略约束条件",
            task_id=task.id,
            run_id="run-1",
            subject="math",
        )
    server.create_tag("error", "定义域遗漏", aliases=["忽略定义域"], subject="math")
    managed_list_tags(
        dimension="error",
        task_id=task.id,
        run_id="run-1",
        subject="math",
    )
    with pytest.raises(ValueError, match="matches existing candidate"):
        managed_create_tag(
            dimension="error",
            value="忽略定义域",
            task_id=task.id,
            run_id="run-1",
            subject="math",
        )
    with pytest.raises(ValueError, match="not active"):
        managed_list_tags(
            dimension="error",
            task_id=task.id,
            run_id="wrong-run",
            subject="math",
        )


def test_managed_knowledge_tag_queries_persist_progress_and_cleanup(tmp_path, monkeypatch):
    task_store = configure_stores(tmp_path, monkeypatch)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    advance_to_finalizing(task.id, authorize_candidate_knowledge=False)
    task_store.update(task.id, stage=TaskStage.TAGGING)

    branches = managed_list_tags(
        dimension="knowledge",
        task_id=task.id,
        run_id="run-1",
        subject="math",
    )
    branch_ids = [child["id"] for group in branches["items"] for child in group["children"]]
    persisted = task_store.get(task.id).metadata["_managed_knowledge_branches"]
    assert persisted["run_id"] == "run-1"
    assert persisted["branch_ids"] == branch_ids

    managed_list_tags(
        dimension="knowledge",
        task_id=task.id,
        run_id="run-1",
        subject="math",
        branch_ids=[branch_ids[0]],
    )
    metadata = task_store.get(task.id).metadata
    assert "_managed_knowledge_branches" not in metadata
    assert metadata["_managed_tag_selection"]["branch_ids"] == [branch_ids[0]]

    cleaned = server._task_metadata_with_review(task_store.get(task.id), "")
    assert "_managed_knowledge_branches" not in cleaned
    assert "_managed_tag_selection" not in cleaned
