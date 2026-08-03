from __future__ import annotations

import io
import json
import os
import queue
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from oopsnote.ai import HermesRunner, PiRpcBackend, PiRpcRunner
from oopsnote.ai import runner as runner_module
from oopsnote.ai.backends import pi_rpc as pi_rpc_module
from oopsnote.ai.backends.pi_rpc import RpcProtocolError
from oopsnote.ai.pi_skills import ACTIVE_PI_SKILLS
from oopsnote.ai.rpc.probe import probe_new_session
from oopsnote.core import (
    ContentFormat,
    Problem,
    RunStatus,
    RunStore,
    SolutionCandidate,
    TaskCreateRequest,
    TaskStage,
    TaskStatus,
    TaskStore,
)
from oopsnote.mcp.tool_registry import AI_TOOL_NAMES


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
        path = project_root / "skills" / name / "SKILL.md"
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
    assert [stage.stage for stage in stored.stage_runs] == [
        TaskStage.QUEUED,
        TaskStage.STARTING,
        TaskStage.FINALIZING,
    ]
    assert all(stage.status.value == "completed" for stage in stored.stage_runs)
    assert stored.duration_ms is not None
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
    recovered = run_store.get(run.id)
    assert recovered.status == RunStatus.TIMED_OUT
    assert recovered.duration_ms is not None
    assert recovered.stage_runs[0].stage == TaskStage.QUEUED
    assert recovered.stage_runs[0].status.value == "failed"
    assert task_store.get(task.id).status == TaskStatus.FAILED
    assert task_store.get(legacy.id).status == TaskStatus.FAILED
    assert task_store.get(legacy.id).last_error_code == "legacy_stale"


def test_hermes_process_exit_preserves_the_shared_failure_code(tmp_path, monkeypatch):
    runner, task_store, run_store = make_runner(tmp_path)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)

    class ExitingProcess:
        pid = 4322
        returncode = 7

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 1

        def kill(self):
            self.returncode = 1

    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_a, **_k: ExitingProcess())

    runner.run(task.id, run.id)

    failed_task = task_store.get(task.id)
    failed_run = run_store.get(run.id)
    assert failed_task.status == TaskStatus.FAILED
    assert failed_task.last_error_code == "process_exit"
    assert failed_run.error_code == "process_exit"
    assert failed_run.retryable is False


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


def test_recover_stale_run_cannot_overwrite_newer_run_ownership(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=60)
    task = task_store.create(TaskCreateRequest(subject="math"))
    stale_run = runner.enqueue(task.id)
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    run_store.update(stale_run.id, status=RunStatus.RUNNING, heartbeat_at=old)

    current_run = run_store.create(task.id, backend=runner.backend_name)
    task_store.transition(
        task.id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=stale_run.id,
        active_run_id=current_run.id,
    )
    runner._processes[task.id] = object()

    assert runner.recover_stale() == 1
    assert run_store.get(stale_run.id).status == RunStatus.TIMED_OUT
    current_task = task_store.get(task.id)
    assert current_task.status == TaskStatus.PROCESSING
    assert current_task.active_run_id == current_run.id
    assert run_store.get(current_run.id).status == RunStatus.QUEUED


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


def test_stale_recovery_preserves_a_classified_task_failure(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=60)
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    run_store.update(run.id, status=RunStatus.RUNNING, heartbeat_at=old)
    task_store.transition(
        task.id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=run.id,
        status=TaskStatus.FAILED,
        active_run_id=None,
        last_error="DashScope OCR timeout",
        last_error_code="ocr_timeout",
    )

    assert runner.recover_stale() == 1
    recovered = run_store.get(run.id)
    assert recovered.status == RunStatus.FAILED
    assert recovered.error_code == "ocr_timeout"
    assert recovered.error_message == "DashScope OCR timeout"


def test_recover_orphaned_run_cannot_overwrite_newer_run_ownership(tmp_path):
    runner, task_store, run_store = make_runner(tmp_path, stale_seconds=3600)
    task = task_store.create(TaskCreateRequest(subject="math"))
    orphaned_run = runner.enqueue(task.id)
    run_store.update(orphaned_run.id, status=RunStatus.RUNNING)

    current_run = run_store.create(task.id, backend=runner.backend_name)
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

    def __init__(
        self,
        on_prompt,
        *,
        settle_prompt=True,
        settle_event="agent_settled",
        settle_repetitions=1,
        settle_abort=True,
        terminal_tool_event=False,
        terminal_tool_error=False,
        cost=0.02,
    ):
        self.stdout = RpcOutput()
        self.stderr = io.StringIO("")
        self.stdin = RpcStdin(self.handle_command)
        self.on_prompt = on_prompt
        self.settle_prompt = settle_prompt
        self.settle_event = settle_event
        self.settle_repetitions = settle_repetitions
        self.settle_abort = settle_abort
        self.terminal_tool_event = terminal_tool_event
        self.terminal_tool_error = terminal_tool_error
        self.cost = cost
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
            if self.terminal_tool_event:
                self.stdout.emit({
                    "type": "tool_execution_end",
                    "toolName": (
                        "ocr_image"
                        if self.terminal_tool_error
                        else "mcp__oopsnote_pipeline_finalize_task"
                    ),
                    "toolCallId": "finalize-call",
                    "isError": self.terminal_tool_error,
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
                    "cost": self.cost,
                },
            })
        elif command == "abort":
            self.stdout.emit({
                "type": "response",
                "command": command,
                "success": True,
            })
            if self.settle_abort:
                for _ in range(self.settle_repetitions):
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


class StartupFailureRpcProcess:
    pid = 9877

    def __init__(self, message: str):
        self.stdout = io.StringIO("")
        self.stderr = io.StringIO(f"{message}\n")
        self.stdin = RpcStdin(self.handle_command)
        self.returncode = None

    def handle_command(self, _payload):
        self.returncode = 1

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = 1

    def kill(self):
        self.terminate()


class FailingPromptRpcProcess(SettlingRpcProcess):
    def __init__(self, failure: str):
        super().__init__(lambda _payload: None, settle_prompt=False)
        self.failure = failure
        self._post_prompt_polls = 0

    def handle_command(self, payload):
        if payload["type"] != "prompt":
            return super().handle_command(payload)
        self.commands.append(payload)
        if self.failure == "invalid_json":
            self.stdout.lines.put("not-json\n")
            return
        self.stdout.close()

    def poll(self):
        if self.failure != "process_exit" or not any(
            command["type"] == "prompt" for command in self.commands
        ):
            return self.returncode
        self._post_prompt_polls += 1
        if self._post_prompt_polls == 1:
            return None
        self.returncode = 7
        return self.returncode


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
    monkeypatch.setattr(
        pi_rpc_module,
        "process_working_set_bytes",
        lambda _pid: 123_456,
    )
    runner.run(task.id, run.id)

    stored = run_store.get(run.id)
    assert stored.status == RunStatus.COMPLETED
    assert stored.backend == "pi"
    assert stored.model == "deepseek-v4-flash"
    assert stored.input_tokens == 12
    assert stored.output_tokens == 8
    assert stored.cache_tokens == 4
    assert stored.cost == 0.02
    assert stored.peak_memory_bytes == 123_456
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


def test_pi_rpc_runner_preserves_startup_stderr_and_log_paths(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.01,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    process = StartupFailureRpcProcess("extension sandbox denied contract path")
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_a, **_k: process)

    runner.run(task.id, run.id)

    failed_task = task_store.get(task.id)
    failed_run = run_store.get(run.id)
    assert failed_task.status == TaskStatus.FAILED
    assert "extension sandbox denied contract path" in (failed_task.last_error or "")
    assert failed_run.status == RunStatus.FAILED
    assert failed_run.error_code == "runner_error"
    assert "extension sandbox denied contract path" in (failed_run.error_message or "")
    assert failed_run.log_path == f"runs/{run.id}.log"
    assert failed_run.rpc_log_path == f"runs/{run.id}.rpc.jsonl"
    assert (run_store.base_dir / f"{run.id}.log").read_text(encoding="utf-8") == (
        "extension sandbox denied contract path\n"
    )
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
        run_id = payload["id"].removeprefix("prompt-").removesuffix("-solver")
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


def test_pi_rpc_runner_verifies_a_persisted_candidate_in_a_fresh_session(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.01,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)

    def respond_to_prompt(payload):
        if payload["id"].endswith("-solver"):
            run_store.submit_solution_candidate(
                run.id,
                SolutionCandidate(
                    problem=Problem(
                        content_format=ContentFormat.OOPSMARK_V1,
                        subject="math",
                        question_type="解答题",
                        problem_text="求 $x+1=2$ 的解。",
                        answer="$x=1$",
                        explanation="移项得 $x=1$。",
                    ),
                ),
            )
        else:
            task_store.update(
                task.id,
                status=TaskStatus.COMPLETED,
                active_run_id=None,
            )

    process = SettlingRpcProcess(respond_to_prompt)
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_args, **_kwargs: process)

    runner.run(task.id, run.id)

    stored = run_store.get(run.id)
    commands = [command["type"] for command in process.commands]
    prompts = [command["message"] for command in process.commands if command["type"] == "prompt"]
    assert commands == [
        "new_session",
        "prompt",
        "get_session_stats",
        "new_session",
        "prompt",
        "get_session_stats",
    ]
    assert len(prompts) == 2
    assert "solver session" in prompts[0]
    assert "fresh, independent Pi session" in prompts[1]
    assert stored.verification_started_at is not None
    assert stored.stats_sessions == 2
    assert stored.input_tokens == 24
    assert stored.output_tokens == 16
    assert stored.cache_tokens == 8
    assert stored.cost == 0.04
    runner.shutdown()


def test_pi_rpc_runner_aborts_unused_summary_after_terminal_tool(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.01,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)

    def finish_task(_payload):
        task_store.update(task.id, status=TaskStatus.COMPLETED, active_run_id=None)

    process = SettlingRpcProcess(
        finish_task,
        settle_prompt=False,
        settle_repetitions=2,
        terminal_tool_event=True,
        cost=0,
    )
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_a, **_k: process)

    runner.run(task.id, run.id)

    assert run_store.get(run.id).status == RunStatus.COMPLETED
    assert run_store.get(run.id).cost is None
    commands = [command["type"] for command in process.commands]
    assert commands == ["new_session", "prompt", "abort", "get_session_stats"]
    assert process.poll() is None
    runner.shutdown()


def test_pi_rpc_terminal_cleanup_failure_cannot_downgrade_completed_task(
    tmp_path,
    monkeypatch,
):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.01,
        terminal_cleanup_seconds=0.05,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)

    def finish_task(_payload):
        task_store.update(task.id, status=TaskStatus.COMPLETED, active_run_id=None)

    process = SettlingRpcProcess(
        finish_task,
        settle_prompt=False,
        settle_abort=False,
        terminal_tool_event=True,
    )
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_a, **_k: process)

    runner.run(task.id, run.id)

    completed = run_store.get(run.id)
    assert completed.status == RunStatus.COMPLETED
    assert completed.duration_ms is not None
    assert [command["type"] for command in process.commands] == [
        "new_session",
        "prompt",
        "abort",
    ]
    assert process.poll() == 1
    runner.shutdown()


def test_pi_rpc_invalid_json_is_a_protocol_error(tmp_path):
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=TaskStore(tmp_path / "storage"),
        run_store=RunStore(tmp_path / "storage" / "runs"),
    )
    rpc_log = io.StringIO()

    with pytest.raises(RpcProtocolError, match="invalid JSON"):
        runner._decode_event("not-json", rpc_log)

    assert '"type": "invalid_json"' in rpc_log.getvalue()


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_message"),
    [
        ("invalid_json", "rpc_protocol_error", "invalid JSON"),
        ("process_exit", "process_exit", "exited with code 7"),
    ],
)
def test_pi_rpc_failure_keeps_the_earliest_terminal_evidence(
    tmp_path,
    monkeypatch,
    failure,
    expected_code,
    expected_message,
):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.01,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)
    process = FailingPromptRpcProcess(failure)
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_a, **_k: process)

    runner.run(task.id, run.id)

    failed_task = task_store.get(task.id)
    failed_run = run_store.get(run.id)
    assert failed_task.status == TaskStatus.FAILED
    assert failed_task.active_run_id is None
    assert expected_message in (failed_task.last_error or "")
    assert failed_run.status == RunStatus.FAILED
    assert failed_run.error_code == expected_code
    assert expected_message in (failed_run.error_message or "")
    assert failed_run.exit_code == (7 if failure == "process_exit" else None)
    assert failed_run.retryable is False
    assert not runner._processes
    runner.shutdown()


def test_pi_rpc_aborts_after_ocr_error_persists_a_terminal_task(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "storage")
    run_store = RunStore(tmp_path / "storage" / "runs")
    write_pi_skill_pack(tmp_path)
    runner = PiRpcRunner(
        backend=PiRpcBackend(tmp_path),
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
        poll_seconds=0.01,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    run = runner.enqueue(task.id)

    def fail_ocr(_payload):
        task_store.transition(
            task.id,
            expected_statuses={TaskStatus.PROCESSING},
            expected_active_run_id=run.id,
            status=TaskStatus.FAILED,
            active_run_id=None,
            last_error="OCR could not read a complete question",
            last_error_code="ocr_unreadable",
        )

    process = SettlingRpcProcess(
        fail_ocr,
        settle_prompt=False,
        terminal_tool_event=True,
        terminal_tool_error=True,
    )
    monkeypatch.setattr(runner_module.subprocess, "Popen", lambda *_a, **_k: process)

    runner.run(task.id, run.id)

    failed = run_store.get(run.id)
    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "ocr_unreadable"
    assert failed.retryable is False
    assert [command["type"] for command in process.commands] == [
        "new_session",
        "prompt",
        "abort",
        "get_session_stats",
    ]
    assert process.poll() is None
    runner.shutdown()


def test_pi_rpc_copies_classified_pipeline_failure_to_the_run(tmp_path):
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
    task_store.transition(
        task.id,
        expected_statuses={TaskStatus.PROCESSING},
        expected_active_run_id=run.id,
        status=TaskStatus.FAILED,
        active_run_id=None,
        last_error="DashScope OCR timeout",
        last_error_code="ocr_timeout",
    )

    runner._complete_after_task(
        task.id,
        run.id,
        None,
        run_store.base_dir / f"{run.id}.log",
        False,
        None,
    )

    failed = run_store.get(run.id)
    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "ocr_timeout"
    assert failed.error_message == "DashScope OCR timeout"
    assert failed.retryable is True


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
    write_pi_skill_pack(tmp_path)
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
    write_pi_skill_pack(tmp_path)
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
    legacy_ocr = tmp_path / ".pi" / "extensions" / "ocr_image.js"
    legacy_ocr.parent.mkdir(parents=True)
    legacy_ocr.write_text("throw new Error('legacy OCR loaded')\n", encoding="utf-8")
    mcp_adapter = tmp_path / ".pi" / "node_modules" / "pi-mcp-adapter" / "index.ts"
    mcp_adapter.parent.mkdir(parents=True)
    mcp_adapter.write_text("export {}\n", encoding="utf-8")

    backend = PiRpcBackend(tmp_path)
    backend.runtime.configure_child_environment(
        {
            "OOPSNOTE_MCP_URL": "http://127.0.0.1:43123/mcp",
            "OOPSNOTE_MCP_TOKEN": "ephemeral-test-token",
        }
    )

    assert backend.build_command("task", "run")[:2] == ["node", "C:/pi/dist/cli.js"]
    assert backend.provider == "deepseek"
    command = backend.build_command("task", "run")
    assert "--no-builtin-tools" in command
    assert "--no-extensions" in command
    assert str(mcp_adapter) in command
    assert str(legacy_ocr) not in command
    assert "--no-session" not in backend.build_command("task", "run")
    config_path = Path(command[command.index("--mcp-config") + 1])
    managed_config = json.loads(config_path.read_text(encoding="utf-8"))
    server = managed_config["mcpServers"]["oopsnote_pipeline"]
    assert server["url"] == "http://127.0.0.1:43123/mcp"
    assert server["headers"]["Authorization"] == "Bearer ephemeral-test-token"
    assert server["directTools"] == list(AI_TOOL_NAMES)

    backend.runtime.cleanup()
    assert not config_path.exists()


def test_rpc_startup_probe_keeps_stdin_open_until_response(tmp_path):
    program = (
        "import json,sys; "
        "command=json.loads(sys.stdin.readline()); "
        "print(json.dumps({'type':'extension_ui_request'}), flush=True); "
        "print(json.dumps({'type':'response','id':command['id'],"
        "'success':True,'data':{}}), flush=True); "
        "sys.stdin.readline()"
    )

    result = probe_new_session(
        [sys.executable, "-u", "-c", program],
        cwd=tmp_path,
        environment=os.environ,
        timeout_seconds=5,
    )

    assert result.success is True
    assert result.events[-1]["id"] == "setup-probe"


def test_pi_retries_only_retryable_failures_in_new_run(tmp_path, monkeypatch):
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
    assert retry.retry_of_run_id == first.id
    assert retry.retry_root_run_id == first.id


def test_retry_classifier_uses_error_codes_not_message_substrings():
    assert PiRpcRunner.is_retryable_error("network_error", "connection refused")
    assert PiRpcRunner.is_retryable_error("rate_limit", "429 from provider")
    assert PiRpcRunner.is_retryable_error("ocr_rate_limit", "HTTP 429")
    assert PiRpcRunner.is_retryable_error("ocr_timeout", "provider timeout")
    assert not PiRpcRunner.is_retryable_error("ocr_unreadable", "unreadable")
    assert not PiRpcRunner.is_retryable_error("ocr_provider_error", "HTTP 401")
    assert not PiRpcRunner.is_retryable_error("rpc_protocol_error", "invalid JSON")
    assert not PiRpcRunner.is_retryable_error("process_timeout", "network timeout")
    assert not PiRpcRunner.is_retryable_error("runner_error", "network unavailable")
    assert not PiRpcRunner.is_retryable_error("rpc_error", "503 from provider")


def test_manual_rerun_starts_a_new_retry_budget(tmp_path):
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
    for _ in range(3):
        run = runner.enqueue(task.id)
        task_store.mark_status(task.id, TaskStatus.FAILED, "historical failure")
        run_store.finish(run.id, RunStatus.FAILED)

    manual = runner.enqueue(task.id)

    assert manual.attempt == 4
    assert manual.retry_count == 0
    assert manual.retry_of_run_id is None
