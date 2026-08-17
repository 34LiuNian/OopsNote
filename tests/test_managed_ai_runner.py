from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from oopsnote.ai import ManagedAiRunner
from oopsnote.core import RunStatus, RunStore, TaskCreateRequest, TaskStatus, TaskStore


class StubManagedRunner(ManagedAiRunner):
    backend_name = "langchain"

    def run(self, task_id: str, run_id: str) -> None:
        del task_id, run_id


def make_runner(tmp_path, **kwargs):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    runner = StubManagedRunner(
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        **kwargs,
    )
    return runner, task_store, run_store


def test_stale_run_expires_without_inventing_a_replacement_run(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=60)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    old = datetime.now(UTC) - timedelta(hours=1)
    run_store.update(run.id, status=RunStatus.RUNNING, heartbeat_at=old)

    assert runner.recover_stale() == 1

    recovered = run_store.get(run.id)
    assert recovered.status == RunStatus.TIMED_OUT
    assert recovered.error_code == "stale_heartbeat"
    assert task_store.get(task.id).status == TaskStatus.FAILED
    assert len(run_store.list_all()) == 1


def test_stale_recovery_preserves_completed_task(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=60)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    old = datetime.now(UTC) - timedelta(hours=1)
    run_store.update(run.id, status=RunStatus.RUNNING, heartbeat_at=old)
    task_store.update(task.id, status=TaskStatus.COMPLETED, active_run_id=None)

    assert runner.recover_stale() == 1
    assert run_store.get(run.id).status == RunStatus.COMPLETED
    assert task_store.get(task.id).status == TaskStatus.COMPLETED


@pytest.mark.parametrize(
    "terminal_status", [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
)
def test_cancel_is_idempotent_for_terminal_tasks(tmp_path, terminal_status):
    runner, task_store, _run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.mark_status(task.id, terminal_status, "existing terminal evidence")

    runner.cancel(task.id)

    current = task_store.get(task.id)
    assert current.status == terminal_status
    assert current.last_error == "existing terminal evidence"


def test_stale_recovery_cannot_overwrite_newer_run_ownership(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=60)
    task = task_store.create(TaskCreateRequest(subject="math"))
    stale_run = runner.enqueue(task.id)
    old = datetime.now(UTC) - timedelta(hours=1)
    run_store.update(stale_run.id, status=RunStatus.RUNNING, heartbeat_at=old)
    current_run = run_store.create(task.id)
    task_store.transition(
        task.id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=stale_run.id,
        active_run_id=current_run.id,
    )

    assert runner.recover_stale() == 1
    assert run_store.get(stale_run.id).status == RunStatus.TIMED_OUT
    current_task = task_store.get(task.id)
    assert current_task.status == TaskStatus.PROCESSING
    assert current_task.active_run_id == current_run.id
    assert run_store.get(current_run.id).status == RunStatus.QUEUED


def test_orphaned_running_run_requires_a_fresh_retry(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    run_store.update(run.id, status=RunStatus.RUNNING)

    assert runner.recover_orphaned_running() == 1

    recovered = run_store.get(run.id)
    assert recovered.status == RunStatus.FAILED
    assert recovered.error_code == "worker_lost"
    assert recovered.retryable is True
    assert task_store.get(task.id).status == TaskStatus.FAILED


def test_failure_transition_replaces_stale_stage_message_with_terminal_error(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    task_store.update(task.id, stage_message="LangChain provider started")

    runner._fail_start(task.id, run.id, "供应商返回 503", "provider_unavailable")

    failed = task_store.get(task.id)
    assert failed.status == TaskStatus.FAILED
    assert failed.stage_message == "供应商返回 503"
    assert failed.last_error == "供应商返回 503"
    assert run_store.get(run.id).error_code == "provider_unavailable"


def test_orphan_recovery_cannot_overwrite_newer_run_ownership(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    orphaned_run = runner.enqueue(task.id)
    run_store.update(orphaned_run.id, status=RunStatus.RUNNING)
    current_run = run_store.create(task.id)
    task_store.transition(
        task.id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=orphaned_run.id,
        active_run_id=current_run.id,
    )

    assert runner.recover_orphaned_running() == 1
    assert run_store.get(orphaned_run.id).status == RunStatus.FAILED
    current_task = task_store.get(task.id)
    assert current_task.status == TaskStatus.PROCESSING
    assert current_task.active_run_id == current_run.id
    assert run_store.get(current_run.id).status == RunStatus.QUEUED


def test_enqueue_admission_is_atomic_across_threads(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    barrier = threading.Barrier(2)
    outcomes: list[tuple[str, str]] = []

    def enqueue_once() -> None:
        barrier.wait(timeout=1)
        try:
            outcomes.append(("ok", runner.enqueue(task.id).id))
        except RuntimeError as error:
            outcomes.append(("error", str(error)))

    threads = [threading.Thread(target=enqueue_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert [kind for kind, _ in outcomes].count("ok") == 1
    assert [kind for kind, _ in outcomes].count("error") == 1
    assert len([run for run in run_store.list_all() if run.task_id == task.id]) == 1


def test_recover_queued_schedules_the_persisted_langchain_run(tmp_path, monkeypatch):
    runner, task_store, _run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(runner._dispatcher, "schedule", lambda *item: scheduled.append(item))

    assert runner.recover_queued() == 1
    assert scheduled == [(task.id, run.id)]


def test_retry_classifier_uses_error_codes_not_message_substrings():
    assert ManagedAiRunner.is_retryable_error("network_error", "connection refused")
    assert ManagedAiRunner.is_retryable_error("rate_limit", "429 from provider")
    assert ManagedAiRunner.is_retryable_error("ocr_timeout", "provider timeout")
    assert not ManagedAiRunner.is_retryable_error("ocr_unreadable", "unreadable")
    assert not ManagedAiRunner.is_retryable_error("runner_error", "network unavailable")
    assert not ManagedAiRunner.is_retryable_error("process_timeout", "network timeout")


def test_retry_is_a_fresh_run_with_original_retry_lineage(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    first = runner.enqueue(task.id)
    task_store.mark_status(task.id, TaskStatus.FAILED, "network unavailable")
    run_store.finish(
        first.id,
        RunStatus.FAILED,
        error_code="network_error",
        error_message="network unavailable",
    )
    run_store.update(first.id, retryable=True)

    retry = runner.retry_if_eligible(task.id, first.id, execute_inline=True)

    assert retry is not None
    assert retry.id != first.id
    assert retry.backend == "langchain"
    assert retry.retry_count == 1
    assert retry.retry_of_run_id == first.id
    assert retry.retry_root_run_id == first.id


def test_manual_rerun_starts_a_new_retry_budget(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    for _ in range(3):
        run = runner.enqueue(task.id)
        task_store.mark_status(task.id, TaskStatus.FAILED, "historical failure")
        run_store.finish(run.id, RunStatus.FAILED)

    manual = runner.enqueue(task.id)

    assert manual.attempt == 4
    assert manual.retry_count == 0
    assert manual.retry_of_run_id is None
