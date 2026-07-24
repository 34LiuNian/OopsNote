from __future__ import annotations

import io
import json
import queue
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


def test_recover_orphaned_running_requires_fresh_retry(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=3600)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    run_store.update(run.id, status=RunStatus.RUNNING)

    assert runner.recover_orphaned_running() == 1

    recovered = run_store.get(run.id)
    assert recovered.status == RunStatus.FAILED
    assert recovered.error_code == "worker_lost"
    assert recovered.retryable is True
    assert task_store.get(task.id).status == TaskStatus.FAILED


def test_enqueue_admission_is_atomic_across_threads(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    barrier = threading.Barrier(2)
    outcomes = []

    def enqueue_once():
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


def test_recover_queued_filters_runs_by_backend(tmp_path, monkeypatch):
    runner, task_store, _run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    scheduled = []
    monkeypatch.setattr(runner._dispatcher, "schedule", lambda *item: scheduled.append(item))

    assert runner.recover_queued() == 1
    assert scheduled == [(task.id, run.id)]

    runner.backend_name = "pi"
    scheduled.clear()
    assert runner.recover_queued() == 0
    assert scheduled == []


class RpcOutput:
    def __init__(self):
        self.lines = queue.Queue()

    def emit(self, payload):
        self.lines.put(json.dumps(payload) + "\n")

    def readline(self):
        return self.lines.get()

    def close(self):
        self.lines.put("")


class RpcStdin:
    def __init__(self, on_command):
        self.on_command = on_command
        self.closed = False

    def write(self, value):
        self.on_command(json.loads(value))
        return len(value)

    def flush(self):
        return None

    def close(self):
        self.closed = True


class SettlingRpcProcess:
    pid = 9876

    def __init__(self, on_prompt, *, settle_prompt=True, settle_event="agent_settled"):
        self.stdout = RpcOutput()
        self.stderr = io.StringIO("")
        self.stdin = RpcStdin(self.handle_command)
        self.on_prompt = on_prompt
        self.settle_prompt = settle_prompt
        self.settle_event = settle_event
        self.commands = []
        self.returncode = None

    def handle_command(self, payload):
        self.commands.append(payload)
        command = payload["type"]
        if command == "new_session":
            self.stdout.emit({
                "type": "response",
                "id": payload["id"],
                "command": command,
                "success": True,
                "data": {"cancelled": False},
            })
        elif command == "prompt":
            self.on_prompt(payload)
            self.stdout.emit({
                "type": "response",
                "id": payload["id"],
                "command": command,
                "success": True,
            })
            self.stdout.emit({
                "type": "message_update",
                "message": {"content": "must-not-be-persisted"},
            })
            if self.settle_prompt:
                self.stdout.emit({"type": self.settle_event})
        elif command == "get_session_stats":
            self.stdout.emit({
                "type": "response",
                "id": payload["id"],
                "command": command,
                "success": True,
                "data": {
                    "tokens": {
                        "input": 12,
                        "output": 8,
                        "cacheRead": 3,
                        "cacheWrite": 1,
                    },
                    "cost": 0.02,
                },
            })
        elif command == "abort":
            self.stdout.emit({
                "type": "response",
                "command": command,
                "success": True,
            })
            self.stdout.emit({"type": self.settle_event})

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = 1
        self.stdin.close()
        self.stdout.close()

    def kill(self):
        self.terminate()


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

    def finish_task(_payload):
        task_store.update(task.id, status=TaskStatus.COMPLETED, active_run_id=None)

    captured = {}

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        captured["process"] = SettlingRpcProcess(finish_task)
        return captured["process"]

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
    assert '"type": "new_session"' in rpc_log
    assert "must-not-be-persisted" not in rpc_log
    assert "oopsnote-solve-problem" not in rpc_log
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["process"].poll() is None
    runner.shutdown()


def test_pi_rust_runtime_isolated_cli_environment_and_mcp_flags(tmp_path):
    config_dir = tmp_path / ".pi-rust"
    extension_dir = config_dir / "extensions"
    extension_dir.mkdir(parents=True)
    bridge = extension_dir / "oopsnote_mcp.js"
    bridge.write_text("", encoding="utf-8")
    (config_dir / "runtime.json").write_text(
        json.dumps(
            {
                "command": [".pi-rust/bin/pi.exe"],
                "version": "0.1.22",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "agent_dir": ".pi-rust/agent",
                "sessions_dir": ".pi-rust/sessions",
            }
        ),
        encoding="utf-8",
    )

    backend = PiRpcBackend(tmp_path, runtime="pi-rust")
    backend.runtime.configure_child_environment(
        {
            "OOPSNOTE_MCP_URL": "http://127.0.0.1:43123/mcp",
            "OOPSNOTE_MCP_TOKEN": "ephemeral-test-token",
        }
    )
    command = backend.build_command("task", "run")
    environment = backend.build_environment()

    assert backend.runtime_kind == "pi-rust"
    assert backend.runtime_version == "0.1.22"
    assert "--no-tools" in command
    assert "--no-extensions" in command
    assert "--no-skills" in command
    assert "--extension-policy" in command
    assert "permissive" in command
    assert str(bridge) in command
    assert command[command.index("--oopsnote-mcp-url") + 1] == "http://127.0.0.1:43123/mcp"
    assert command[command.index("--oopsnote-mcp-token") + 1] == "ephemeral-test-token"
    assert environment["PI_CODING_AGENT_DIR"] == str((config_dir / "agent").resolve())
    assert environment["PI_SESSIONS_DIR"] == str((config_dir / "sessions").resolve())
    assert environment["PI_HTTP_ALLOW_LOOPBACK"] == "1"


def test_pi_rust_runner_settles_on_agent_end(tmp_path, monkeypatch):
    config_dir = tmp_path / ".pi-rust"
    config_dir.mkdir(parents=True)
    (config_dir / "runtime.json").write_text(
        '{"command":["pi.exe"],"version":"0.1.22"}',
        encoding="utf-8",
    )
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path, runtime="pi-rust"),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.05,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)

    def finish_task(_payload):
        task_store.update(task.id, status=TaskStatus.COMPLETED, active_run_id=None)

    process = SettlingRpcProcess(finish_task, settle_event="agent_end")
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_a, **_k: process)
    runner.run(task.id, run.id)

    completed = run_store.get(run.id)
    assert completed.status == RunStatus.COMPLETED
    assert completed.runtime_kind == "pi-rust"
    assert completed.runtime_version == "0.1.22"
    runner.shutdown()


def test_pi_rpc_runner_reuses_process_with_clean_session_per_task(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.05,
    )
    tasks = [task_store.create(TaskCreateRequest(subject="math")) for _ in range(2)]
    runs = [runner.enqueue(task.id) for task in tasks]
    tasks_by_run = {run.id: task for task, run in zip(tasks, runs)}
    spawned = []

    def finish_prompt(payload):
        run_id = payload["id"].removeprefix("prompt-")
        task = tasks_by_run[run_id]
        task_store.update(task.id, status=TaskStatus.COMPLETED, active_run_id=None)

    def fake_popen(*_args, **_kwargs):
        process = SettlingRpcProcess(finish_prompt)
        spawned.append(process)
        return process

    monkeypatch.setattr(runner_module.subprocess, "Popen", fake_popen)
    for task, run in zip(tasks, runs):
        runner.run(task.id, run.id)

    assert len(spawned) == 1
    commands = [command["type"] for command in spawned[0].commands]
    assert commands == [
        "new_session",
        "prompt",
        "get_session_stats",
        "new_session",
        "prompt",
        "get_session_stats",
    ]
    assert all(run_store.get(run.id).status == RunStatus.COMPLETED for run in runs)
    runner.shutdown()


def test_pi_rpc_cancel_aborts_task_without_killing_shared_worker(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.05,
    )
    prompt_started = threading.Event()
    process = SettlingRpcProcess(
        lambda _payload: prompt_started.set(), settle_prompt=False
    )
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_args, **_kwargs: process)

    cancelled_task = task_store.create(TaskCreateRequest(subject="math"))
    cancelled_run = runner.enqueue(cancelled_task.id)
    worker_thread = threading.Thread(
        target=runner.run, args=(cancelled_task.id, cancelled_run.id)
    )
    worker_thread.start()
    assert prompt_started.wait(timeout=1)
    runner.cancel(cancelled_task.id)
    worker_thread.join(timeout=2)

    assert not worker_thread.is_alive()
    assert process.poll() is None
    assert task_store.get(cancelled_task.id).status == TaskStatus.CANCELLED
    assert run_store.get(cancelled_run.id).status == RunStatus.CANCELLED

    next_task = task_store.create(TaskCreateRequest(subject="math"))
    next_run = runner.enqueue(next_task.id)
    process.settle_prompt = True
    process.on_prompt = lambda _payload: task_store.update(
        next_task.id, status=TaskStatus.COMPLETED, active_run_id=None
    )
    runner.run(next_task.id, next_run.id)

    assert run_store.get(next_run.id).status == RunStatus.COMPLETED
    assert sum(command["type"] == "new_session" for command in process.commands) == 2
    runner.shutdown()


def test_pi_runner_single_worker_skips_cancelled_queue_item(
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
        max_concurrent_tasks=1,
    )
    tasks = [task_store.create(TaskCreateRequest(subject="math")) for _ in range(2)]
    runs = [runner.enqueue(task.id) for task in tasks]
    entered: list[str] = []
    entered_one = threading.Event()
    release = threading.Event()

    def block_in_slot(task_id, _run_id):
        entered.append(task_id)
        entered_one.set()
        release.wait(timeout=2)

    monkeypatch.setattr(runner, "_run_in_slot", block_in_slot)
    active_thread = threading.Thread(target=runner.run, args=(tasks[0].id, runs[0].id))
    active_thread.start()
    assert entered_one.wait(timeout=1)
    queued_thread = threading.Thread(
        target=runner.run, args=(tasks[1].id, runs[1].id)
    )
    queued_thread.start()
    runner.cancel(tasks[1].id)
    assert len(entered) == 1
    release.set()
    for thread in [active_thread, queued_thread]:
        thread.join(timeout=2)

    assert entered == [tasks[0].id]
    assert runner.max_concurrent_tasks == 1
    assert task_store.get(tasks[1].id).status == TaskStatus.CANCELLED
    assert run_store.get(runs[1].id).status == RunStatus.CANCELLED


def test_pi_runner_pool_executes_on_distinct_workers(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        max_concurrent_tasks=2,
    )
    tasks = [task_store.create(TaskCreateRequest(subject="math")) for _ in range(2)]
    runs = [runner.enqueue(task.id) for task in tasks]
    both_entered = threading.Event()
    release = threading.Event()
    entered: list[tuple[str, str]] = []
    entered_lock = threading.Lock()

    def block_in_slot(task_id, _run_id):
        with entered_lock:
            entered.append((task_id, runner._current_worker().worker_id))
            if len(entered) == 2:
                both_entered.set()
        release.wait(timeout=2)

    monkeypatch.setattr(runner, "_run_in_slot", block_in_slot)
    threads = [
        threading.Thread(target=runner.run, args=(task.id, run.id))
        for task, run in zip(tasks, runs)
    ]
    for thread in threads:
        thread.start()

    assert both_entered.wait(timeout=1)
    assert runner.max_concurrent_tasks == 2
    assert len({worker_id for _, worker_id in entered}) == 2

    release.set()
    for thread in threads:
        thread.join(timeout=2)
        assert not thread.is_alive()


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
    command = backend.build_command("task", "run")
    assert "--no-builtin-tools" in command
    assert "--no-extensions" in command
    assert "--no-session" not in backend.build_command("task", "run")


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
