from __future__ import annotations

from datetime import UTC, datetime, timedelta

from oopsnote.core import RunStatus, TaskRecord, TaskRun
from scripts.benchmarks.pi_production_report import build_report, markdown_report


def test_report_counts_one_final_outcome_per_task_and_preserves_unknown_metrics():
    started = datetime(2026, 7, 1, tzinfo=UTC)
    task = TaskRecord(id="task-1", revision_count=0)
    retried = TaskRun(
        id="run-1",
        task_id=task.id,
        runtime_kind="pi-rust",
        prompt_version="current",
        status=RunStatus.FAILED,
        queued_at=started,
        ended_at=started + timedelta(seconds=2),
    )
    completed = TaskRun(
        id="run-2",
        task_id=task.id,
        runtime_kind="pi-rust",
        prompt_version="current",
        status=RunStatus.COMPLETED,
        retry_count=1,
        queued_at=started + timedelta(seconds=4),
        ended_at=started + timedelta(seconds=10),
        peak_memory_bytes=2048,
        cost=0.25,
    )
    report = build_report([task], [retried, completed], prompt_version="current")

    assert report["population"]["tasks"] == 1
    assert report["population"]["successful_tasks"] == 1
    assert report["metrics"]["p50_duration_ms"] == 10_000
    assert report["metrics"]["memory_coverage"] == 1.0
    assert report["metrics"]["revision_coverage"] == 1.0
    assert report["retirement_gates"]["at_least_30_tasks"] is False
    assert report["retirement_gates"]["fault_injection_passed"] is None
    assert report["all_retirement_gates_pass"] is False


def test_report_never_converts_historic_unknowns_to_zero():
    started = datetime(2026, 7, 1, tzinfo=UTC)
    task = TaskRecord(id="task-1")
    run = TaskRun(
        id="run-1",
        task_id=task.id,
        runtime_kind="pi-rust",
        status=RunStatus.COMPLETED,
        queued_at=started,
        ended_at=started + timedelta(seconds=1),
    )
    report = build_report([task], [run])

    assert report["metrics"]["memory_coverage"] == 0.0
    assert report["metrics"]["cost_coverage"] == 0.0
    assert report["metrics"]["revision_coverage"] == 0.0
    assert "memory coverage | 0.0%" in markdown_report(report)
    assert "fault injection passed | not observed" in markdown_report(report)


def test_report_keeps_orphaned_runs_out_of_task_metrics_but_preserves_evidence():
    started = datetime(2026, 7, 1, tzinfo=UTC)
    orphaned = TaskRun(
        id="orphaned-run",
        task_id="deleted-task",
        runtime_kind="pi-rust",
        status=RunStatus.FAILED,
        error_code="runner_error",
        queued_at=started,
        ended_at=started + timedelta(seconds=1),
    )

    report = build_report([], [orphaned])

    assert report["population"]["tasks"] == 0
    assert report["population"]["successful_tasks"] == 0
    assert report["orphaned_terminal_runs"] == {
        "count": 1,
        "by_status": {"failed": 1},
        "by_result_code": {"runner_error": 1},
        "run_ids": ["orphaned-run"],
    }
    assert "orphaned terminal runs excluded from task cohort | 1" in markdown_report(report)
