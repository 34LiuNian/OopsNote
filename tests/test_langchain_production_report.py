from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from oopsnote.core import RunArtifact, RunStatus, TaskRecord, TaskRun, TaskStage
from scripts.benchmarks.langchain_production_report import (
    EvaluationEvidence,
    LangChainStrategy,
    build_report,
    evidence_template,
    markdown_report,
)


def test_report_groups_retries_per_task_and_never_inferrs_unobserved_gates():
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    task = TaskRecord(id="task-1")
    snapshot = _snapshot()
    failed = TaskRun(id="run-1", task_id=task.id, backend="langchain", provider_profile_snapshot=snapshot, status=RunStatus.FAILED, queued_at=start, ended_at=start + timedelta(seconds=2))
    completed = TaskRun(id="run-2", task_id=task.id, backend="langchain", provider_profile_snapshot=snapshot, status=RunStatus.COMPLETED, retry_count=1, queued_at=start + timedelta(seconds=3), ended_at=start + timedelta(seconds=10), cost=0.12)

    report = build_report([task], [failed, completed], policy_version=1)

    assert report["population"] == {"tasks": 1, "completed": 1, "completion_rate": 1.0}
    assert report["outcomes"][0]["duration_ms"] == 10_000
    assert report["gates"]["no_lost_or_duplicate_finalize"] is None
    assert report["all_gates_pass"] is False
    assert "not observed" in markdown_report(report)


def _snapshot():
    stage = {
        "channel_id": "deepseek-primary",
        "provider": "deepseek",
        "model": "m",
        "version": 3,
        "credential_ref": "opaque",
    }
    return {
        "policy_version": 1,
        "vision": stage,
        "agent": stage,
        "review": stage,
    }


def _strategy():
    return {
        "policy_version": 1,
        "vision": {"channel_id": "deepseek-primary", "provider": "deepseek", "model": "m", "version": 3},
        "agent": {"channel_id": "deepseek-primary", "provider": "deepseek", "model": "m", "version": 3},
        "review": {"channel_id": "deepseek-primary", "provider": "deepseek", "model": "m", "version": 3},
    }


def _passing_cohort():
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    snapshot = _snapshot()
    tasks = [TaskRecord(id=f"task-{index}") for index in range(30)]
    runs = [
        TaskRun(
            id=f"run-{index}",
            task_id=task.id,
            backend="langchain",
            provider_profile_snapshot=snapshot,
            status=RunStatus.COMPLETED,
            queued_at=start + timedelta(seconds=index * 2),
            ended_at=start + timedelta(seconds=index * 2 + 1),
            cost=0.1,
            artifacts=[RunArtifact(
                stage=TaskStage.FINALIZING,
                kind="verifier_submission",
                raw_output="{}",
                parsed_output={},
            )],
        )
        for index, task in enumerate(tasks)
    ]
    cancellation_task = TaskRecord(
        id="cancellation-task",
        metadata={"source": "langchain-cancellation-trial"},
    )
    tasks.append(cancellation_task)
    runs.append(TaskRun(
        id="cancelled-run",
        task_id=cancellation_task.id,
        backend="langchain",
        provider_profile_snapshot=snapshot,
        status=RunStatus.CANCELLED,
        queued_at=start,
        ended_at=start + timedelta(milliseconds=100),
    ))
    evidence = EvaluationEvidence.model_validate({
        "schema_version": 2,
        "strategy": _strategy(),
        "baseline_p95_ms": 1000,
        "task_results": [
            {
                "task_id": task.id,
                "langchain_quality_pass": True,
                "baseline_quality_pass": True,
            }
            for task in tasks[:30]
        ],
        "cancellation_trials": [{
            "run_id": "cancelled-run",
            "cancellation_requested": True,
            "reached_cancelled_terminal": True,
            "terminal_state_preserved": True,
        }],
        "cost_approval": {
            "approved": True,
            "maximum_total_cost": 3.01,
            "currency": "USD",
            "approved_by": "evaluation-owner",
            "approved_at": "2026-08-02T00:00:00Z",
        },
    })
    return tasks, runs, evidence


def test_explicit_evidence_can_prove_every_rustpi_deletion_gate():
    tasks, runs, evidence = _passing_cohort()

    report = build_report(tasks, runs, evidence=evidence)

    assert report["population"] == {"tasks": 30, "completed": 30, "completion_rate": 1.0}
    assert all(value is True for value in report["gates"].values())
    assert report["all_gates_pass"] is True
    assert report["evidence"]["cohort_matches_persisted_runs"] is True


def test_evidence_cannot_attest_to_a_task_missing_from_persisted_runs():
    tasks, runs, evidence = _passing_cohort()
    evidence = evidence.model_copy(update={
        "task_results": [
            *evidence.task_results[:-1],
            evidence.task_results[-1].model_copy(update={"task_id": "missing-task"}),
        ]
    })

    report = build_report(tasks, runs, evidence=evidence)

    assert report["evidence"]["cohort_matches_persisted_runs"] is False
    assert report["gates"]["at_least_30_real_tasks"] is False
    assert report["gates"]["no_lost_or_duplicate_finalize"] is False
    assert report["all_gates_pass"] is False


def test_evidence_rejects_a_run_with_a_different_frozen_stage_strategy():
    tasks, runs, evidence = _passing_cohort()
    altered = _snapshot()
    altered["review"] = {**altered["review"], "model": "different-review-model"}
    runs[-2] = runs[-2].model_copy(update={"provider_profile_snapshot": altered})

    report = build_report(tasks, runs, evidence=evidence)

    assert report["population"]["tasks"] == 29
    assert report["evidence"]["cohort_matches_persisted_runs"] is False
    assert report["all_gates_pass"] is False


def test_report_excludes_legacy_single_profile_snapshots():
    task = TaskRecord(id="legacy-task")
    legacy_run = TaskRun(
        id="legacy-run",
        task_id=task.id,
        backend="langchain",
        provider_profile_snapshot={"id": "old-profile", "version": 1, "provider": "deepseek", "model": "m"},
        status=RunStatus.COMPLETED,
    )

    report = build_report([task], [legacy_run])

    assert report["population"]["tasks"] == 0


def test_report_rejects_duplicate_finalize_artifacts_from_persisted_evidence():
    tasks, runs, evidence = _passing_cohort()
    runs[0] = runs[0].model_copy(update={"artifacts": [*runs[0].artifacts, runs[0].artifacts[0]]})

    report = build_report(tasks, runs, evidence=evidence)

    assert report["gates"]["no_lost_or_duplicate_finalize"] is False
    assert report["all_gates_pass"] is False


def test_report_rejects_finalize_in_an_earlier_retry_attempt():
    tasks, runs, evidence = _passing_cohort()
    earlier = runs[0].model_copy(update={"id": "earlier-finalize", "retry_count": 0})
    runs[0] = runs[0].model_copy(update={"retry_count": 1})
    runs.insert(0, earlier)

    report = build_report(tasks, runs, evidence=evidence)

    assert report["gates"]["no_lost_or_duplicate_finalize"] is False
    assert report["all_gates_pass"] is False


def test_evidence_rejects_duplicate_task_references():
    _, _, evidence = _passing_cohort()
    duplicate = evidence.task_results[0].model_dump(mode="json")
    payload = evidence.model_dump(mode="json")
    payload["task_results"] = [duplicate, duplicate]

    with pytest.raises(ValueError, match="duplicate task_id"):
        EvaluationEvidence.model_validate(payload)


def test_generated_evidence_template_requires_explicit_human_review():
    tasks, runs, _ = _passing_cohort()
    report = build_report(tasks, runs, policy_version=1)

    template = evidence_template(
        report,
        strategy=LangChainStrategy.model_validate(_strategy()),
    )

    assert len(template["task_results"]) == 30
    assert template["task_results"][0]["langchain_quality_pass"] is None
    assert template["baseline_p95_ms"] is None
    assert template["cost_approval"]["maximum_total_cost"] is None
    with pytest.raises(ValueError):
        EvaluationEvidence.model_validate(template)
