from __future__ import annotations

from datetime import datetime, timedelta, timezone

from oopsnote.core import RunStatus, TaskRecord, TaskRun
from scripts.benchmarks.langchain_production_report import build_report, markdown_report


def test_report_groups_retries_per_task_and_never_inferrs_unobserved_gates():
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    task = TaskRecord(id="task-1")
    snapshot = {"id": "deepseek-primary", "version": 3, "provider": "deepseek", "model": "m", "credential_ref": "opaque", "base_url": "https://provider.example", "enabled": True}
    failed = TaskRun(id="run-1", task_id=task.id, backend="langchain", provider_profile_snapshot=snapshot, status=RunStatus.FAILED, queued_at=start, ended_at=start + timedelta(seconds=2))
    completed = TaskRun(id="run-2", task_id=task.id, backend="langchain", provider_profile_snapshot=snapshot, status=RunStatus.COMPLETED, retry_count=1, queued_at=start + timedelta(seconds=3), ended_at=start + timedelta(seconds=10), cost=0.12)

    report = build_report([task], [failed, completed], profile_id="deepseek-primary", profile_version=3)

    assert report["population"] == {"tasks": 1, "completed": 1, "completion_rate": 1.0}
    assert report["outcomes"][0]["duration_ms"] == 10_000
    assert report["gates"]["no_lost_or_duplicate_finalize"] is None
    assert report["all_gates_pass"] is False
    assert "not observed" in markdown_report(report)
