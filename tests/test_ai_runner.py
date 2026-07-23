from __future__ import annotations

import io
import threading
from datetime import datetime, timedelta, timezone

from oopsnote.ai import HermesRunner, PiRpcBackend, PiRpcRunner
from oopsnote.ai import runner as runner_module
from oopsnote.ai.pi_skills import ACTIVE_PI_SKILLS
from oopsnote.core import RunStatus, RunStore, TaskCreateRequest, TaskStage, TaskStatus, TaskStore


class CompletingProcess:
    pid = 4321

    def __init__(self, on_complete):
        self.on_complete = on_complete
        self.poll_count = 0
        self.returncode = None

    def poll(self):
        self.poll_count += 1
        if self.poll_count == 1:
            return None
        if self.returncode is None:
            self.on_complete()
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self.returncode = 1

    def kill(self):
        self.returncode = 1

    def wait(self, timeout=None):
        return self.returncode


def make_runner(tmp_path, **kwargs):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    runner = HermesRunner(
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        heartbeat_seconds=0.05,
        poll_seconds=0.05,
        **kwargs,
    )
    return runner, task_store, run_store


def write_pi_skill_pack(project_root):
    for name in ACTIVE_PI_SKILLS:
        path = project_root / ".pi" / "skills" / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")


def test_managed_runner_restricts_tools_and_records_completion(tmp_path, monkeypatch):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math", asset_path="/assets/q.png"))
    run = runner.enqueue(task.id)

    def complete_task():
        task_store.update(
            task.id,
            status=TaskStatus.COMPLETED,
            stage=TaskStage.FINALIZING,
            stage_message="完成",
            active_run_id=None,
        )

    captured = {}

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return CompletingProcess(complete_task)

    monkeypatch.setattr(runner_module.subprocess, "Popen", fake_popen)
    runner.run(task.id, run.id)

    stored = run_store.get(run.id)
    assert stored.status == RunStatus.COMPLETED
    assert stored.exit_code == 0
    assert [stage.stage for stage in stored.stage_runs] == [TaskStage.STARTING, TaskStage.FINALIZING]
    toolsets = captured["command"][captured["command"].index("-t") + 1]
    assert toolsets == "vision,oopsnote_pipeline"
    assert "terminal" not in toolsets


def test_recover_stale_run_and_legacy_task(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=60)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    run_store.update(run.id, status=RunStatus.RUNNING, heartbeat_at=old)

    legacy = task_store.create(TaskCreateRequest(subject="physics"))
    task_store.update(legacy.id, status=TaskStatus.PROCESSING, updated_at=old)

    assert runner.recover_stale() == 2
    assert run_store.get(run.id).status == RunStatus.TIMED_OUT
    assert task_store.get(task.id).status == TaskStatus.FAILED
    assert task_store.get(legacy.id).status == TaskStatus.FAILED


def test_recover_stale_run_preserves_completed_task(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=60)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    run_store.update(run.id, status=RunStatus.RUNNING, heartbeat_at=old)
    task_store.update(
        task.id,
        status=TaskStatus.COMPLETED,
        active_run_id=None,
    )

    assert runner.recover_stale() == 1
    assert run_store.get(run.id).status == RunStatus.COMPLETED
    assert task_store.get(task.id).status == TaskStatus.COMPLETED


class RpcStdin(io.StringIO):
    def __init__(self, on_close):
        super().__init__()
        self.on_close = on_close

    def close(self):
        if not self.closed:
            self.on_close()
        super().close()


class SettlingRpcProcess:
    pid = 9876

    def __init__(self, on_close):
        self.stdin = RpcStdin(on_close)
        self.stdout = io.StringIO(
            '{"type":"response","command":"prompt","success":true}\n'
            '{"type":"message_update","message":{"content":"must-not-be-persisted"}}\n'
            '{"type":"agent_settled"}\n'
            '{"type":"response","command":"get_session_stats","data":'
            '{"tokens":{"input":12,"output":8,"cacheRead":3,"cacheWrite":1},"cost":0.02}}\n'
        )
        self.returncode = None

    def poll(self):
        return 0 if self.stdin.closed else None

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def terminate(self):
        self.returncode = 1

    def kill(self):
        self.returncode = 1


def test_pi_rpc_runner_persists_jsonl_and_stats(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    backend = PiRpcBackend(tmp_path, model="deepseek-v4-flash")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=backend,
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        heartbeat_seconds=0.05,
        poll_seconds=0.05,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)

    def finish_task():
        task_store.update(task.id, status=TaskStatus.COMPLETED, active_run_id=None)

    captured = {}

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        return SettlingRpcProcess(finish_task)

    monkeypatch.setattr(runner_module.subprocess, "Popen", fake_popen)
    runner.run(task.id, run.id)

    stored = run_store.get(run.id)
    assert stored.status == RunStatus.COMPLETED
    assert stored.backend == "pi"
    assert stored.model == "deepseek-v4-flash"
    assert stored.input_tokens == 12
    assert stored.output_tokens == 8
    assert stored.cache_tokens == 4
    assert stored.cost == 0.02
    assert stored.retry_count == 0
    assert not stored.retryable
    assert stored.rpc_log_path
    rpc_log = (run_store.base_dir / f"{run.id}.rpc.jsonl").read_text(encoding="utf-8")
    assert '"direction": "command"' in rpc_log
    assert '"message_chars"' in rpc_log
    assert '"command": "get_session_stats"' in rpc_log
    assert "must-not-be-persisted" not in rpc_log
    assert "oopsnote-solve-problem" not in rpc_log
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"


def test_pi_runner_limits_concurrency_and_skips_cancelled_queue_item(
    tmp_path,
    monkeypatch,
):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        max_concurrent_tasks=2,
    )
    tasks = [task_store.create(TaskCreateRequest(subject="math")) for _ in range(3)]
    runs = [runner.enqueue(task.id) for task in tasks]
    entered: list[str] = []
    entered_two = threading.Event()
    release = threading.Event()
    lock = threading.Lock()

    def block_in_slot(task_id, _run_id):
        with lock:
            entered.append(task_id)
            if len(entered) == 2:
                entered_two.set()
        release.wait(timeout=2)

    monkeypatch.setattr(runner, "_run_in_slot", block_in_slot)
    active_threads = [
        threading.Thread(target=runner.run, args=(task.id, run.id))
        for task, run in zip(tasks[:2], runs[:2])
    ]
    for thread in active_threads:
        thread.start()

    assert entered_two.wait(timeout=1)
    assert len(entered) == 2
    queued_thread = threading.Thread(
        target=runner.run,
        args=(tasks[2].id, runs[2].id),
    )
    queued_thread.start()
    runner.cancel(tasks[2].id)
    release.set()
    for thread in [*active_threads, queued_thread]:
        thread.join(timeout=2)

    assert len(entered) == 2
    assert task_store.get(tasks[2].id).status == TaskStatus.CANCELLED
    assert run_store.get(runs[2].id).status == RunStatus.CANCELLED


def test_pi_prompt_contains_synced_skill_pack(tmp_path):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)

    prompt = runner._prompt(task.id, run.id)

    assert "<oopsnote_runtime_skills>" in prompt
    assert '<skill name="oopsnote-solve-problem">' in prompt


def test_pi_backend_reads_non_secret_local_runtime_config(tmp_path):
    config = tmp_path / ".pi" / "runtime.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        '{"command":["node","C:/pi/dist/cli.js"],"provider":"deepseek","model":"deepseek-v4-flash"}',
        encoding="utf-8",
    )

    backend = PiRpcBackend(tmp_path)

    assert backend.build_command("task", "run")[:2] == ["node", "C:/pi/dist/cli.js"]
    assert backend.provider == "deepseek"
    assert "--no-extensions" in backend.build_command("task", "run")


def test_pi_retries_only_retryable_failures_in_new_run(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    first = runner.enqueue(task.id)
    task_store.mark_status(task.id, TaskStatus.FAILED, "network unavailable")
    run_store.finish(first.id, RunStatus.FAILED, error_code="network_error", error_message="network unavailable")
    run_store.update(first.id, retryable=True)
    captured = []
    monkeypatch.setattr(runner, "run", lambda task_id, run_id: captured.append((task_id, run_id)))

    runner._retry_if_eligible(task.id, first.id)

    assert len(captured) == 1
    retry = run_store.get(captured[0][1])
    assert retry.backend == "pi"
    assert retry.attempt == 2
    assert retry.retry_count == 1
