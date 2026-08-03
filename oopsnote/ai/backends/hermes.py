"""Temporary Hermes compatibility backend."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from oopsnote.ai.managed import ManagedAiRunner
from oopsnote.ai.process_metrics import process_working_set_bytes
from oopsnote.core import RunStatus, StateConflict, TaskStage, TaskStatus


class HermesRunner(ManagedAiRunner):
    """Run the legacy Hermes worker through the shared managed lifecycle."""

    backend_name = "hermes"
    SKILLS = ",".join(
        (
            "oopsnote-orchestrator",
            "oopsnote-ocr-extract",
            "oopsnote-solve-problem",
            "oopsnote-tag-problem",
        )
    )

    def _run_metadata(self) -> dict[str, str]:
        return {"prompt_version": "hermes-legacy"}

    def build_command(self, task_id: str, run_id: str) -> list[str]:
        task = self.task_store.get(task_id)
        prompt = (
            f"处理已有 OopsNote 任务 {task.id}，run_id={run_id}，"
            f"图片资产为 {task.asset_path or '无'}。严格按预加载 skill 顺序执行；"
            "只使用 vision 和 mcp__oopsnote_pipeline__* 工具；每个阶段先调用 report_task_stage；"
            "最终必须调用 finalize_task，禁止直接读写仓库或存储文件。"
        )
        return [
            "hermes",
            "--profile",
            "oopsnote",
            "chat",
            "-q",
            prompt,
            "-Q",
            "--source",
            "tool",
            "--max-turns",
            "18",
            "-t",
            "vision,oopsnote_pipeline",
            "-s",
            self.SKILLS,
        ]

    def run(self, task_id: str, run_id: str) -> None:
        log_path = self.run_store.base_dir / f"{run_id}.log"
        process: Optional[subprocess.Popen[bytes]] = None
        control = None
        peak_memory_bytes: Optional[int] = None
        started = time.monotonic()
        last_heartbeat = started
        try:
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            python_path = env.get("PYTHONPATH")
            env["PYTHONPATH"] = str(self.project_root) + (
                os.pathsep + python_path if python_path else ""
            )
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            with log_path.open("ab", buffering=0) as log:
                process = subprocess.Popen(
                    self.build_command(task_id, run_id),
                    cwd=self.project_root,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
                with self._lock:
                    control = self._register_process(task_id, process)
                self.run_store.start(run_id, process.pid, f"runs/{log_path.name}")
                peak_memory_bytes = process_working_set_bytes(process.pid)
                self._set_stage(
                    task_id,
                    run_id,
                    TaskStage.STARTING,
                    "Hermes started",
                )

                while process.poll() is None:
                    if time.monotonic() - started >= self.timeout_seconds:
                        control.cancel()
                        message = f"Hermes exceeded {self.timeout_seconds}s timeout"
                        try:
                            self.task_store.transition(
                                task_id,
                                expected_statuses={TaskStatus.PROCESSING},
                                expected_active_run_id=run_id,
                                status=TaskStatus.FAILED,
                                active_run_id=None,
                                last_error=message,
                                last_error_code="process_timeout",
                            )
                        except StateConflict:
                            pass
                        self.run_store.finish(
                            run_id,
                            RunStatus.TIMED_OUT,
                            exit_code=process.poll(),
                            error_code="process_timeout",
                            error_message=message,
                        )
                        self.run_store.update(
                            run_id,
                            retryable=self.is_retryable_error("process_timeout", message),
                        )
                        return
                    observed_memory = process_working_set_bytes(process.pid)
                    if observed_memory is not None:
                        peak_memory_bytes = max(peak_memory_bytes or 0, observed_memory)
                    self._observe_task(run_id, task_id)
                    if time.monotonic() - last_heartbeat >= self.heartbeat_seconds:
                        self.run_store.heartbeat(run_id)
                        last_heartbeat = time.monotonic()
                    time.sleep(self.poll_seconds)

            exit_code = process.returncode
            task = self.task_store.get(task_id)
            self._observe_task(run_id, task_id)
            if task.status == TaskStatus.CANCELLED:
                self.run_store.finish(
                    run_id,
                    RunStatus.CANCELLED,
                    exit_code=exit_code,
                )
            elif task.status == TaskStatus.FAILED:
                error_code = task.last_error_code or "pipeline_failed"
                self.run_store.finish(
                    run_id,
                    RunStatus.FAILED,
                    exit_code=exit_code,
                    error_code=error_code,
                    error_message=task.last_error or task.stage_message,
                )
                self.run_store.update(
                    run_id,
                    retryable=self.is_retryable_error(error_code, task.last_error),
                )
            elif exit_code != 0:
                message = f"Hermes exited with code {exit_code}; see {log_path}"
                try:
                    self.task_store.transition(
                        task_id,
                        expected_statuses={TaskStatus.PROCESSING},
                        expected_active_run_id=run_id,
                        status=TaskStatus.FAILED,
                        active_run_id=None,
                        last_error=message,
                        last_error_code="process_exit",
                    )
                except StateConflict:
                    pass
                self.run_store.finish(
                    run_id,
                    RunStatus.FAILED,
                    exit_code=exit_code,
                    error_code="process_exit",
                    error_message=message,
                )
                self.run_store.update(
                    run_id,
                    retryable=self.is_retryable_error("process_exit", message),
                )
            elif task.status != TaskStatus.COMPLETED:
                message = "Hermes exited without finalizing the task"
                try:
                    self.task_store.transition(
                        task_id,
                        expected_statuses={TaskStatus.PROCESSING},
                        expected_active_run_id=run_id,
                        status=TaskStatus.FAILED,
                        active_run_id=None,
                        last_error=message,
                        last_error_code="not_finalized",
                    )
                except StateConflict:
                    pass
                self.run_store.finish(
                    run_id,
                    RunStatus.FAILED,
                    exit_code=exit_code,
                    error_code="not_finalized",
                    error_message=message,
                )
                self.run_store.update(
                    run_id,
                    retryable=self.is_retryable_error("not_finalized", message),
                )
            else:
                self.run_store.finish(
                    run_id,
                    RunStatus.COMPLETED,
                    exit_code=exit_code,
                )
        except FileNotFoundError:
            self._fail_start(
                task_id,
                run_id,
                "Hermes is not installed or is not on PATH",
                "not_installed",
            )
        except Exception as error:
            self._fail_start(task_id, run_id, str(error), "runner_error")
        finally:
            if peak_memory_bytes is not None:
                try:
                    self.run_store.update(run_id, peak_memory_bytes=peak_memory_bytes)
                except KeyError:
                    pass
            if control is not None:
                self._clear_control(task_id, control)


__all__ = ["HermesRunner"]
