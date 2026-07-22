"""Temporary Hermes compatibility backend."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from oopsnote.ai.managed import ManagedAiRunner
from oopsnote.core import RunStatus, TaskStage, TaskStatus


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
                    self._processes[task_id] = process
                self.run_store.start(run_id, process.pid, f"runs/{log_path.name}")
                self.task_store.update(
                    task_id,
                    stage=TaskStage.STARTING,
                    stage_message="Hermes started",
                )

                while process.poll() is None:
                    if time.monotonic() - started >= self.timeout_seconds:
                        self._terminate(process)
                        message = f"Hermes exceeded {self.timeout_seconds}s timeout"
                        self.task_store.mark_status(
                            task_id,
                            TaskStatus.FAILED,
                            message,
                        )
                        self.run_store.finish(
                            run_id,
                            RunStatus.TIMED_OUT,
                            exit_code=process.poll(),
                            error_code="process_timeout",
                            error_message=message,
                        )
                        return
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
                self.run_store.finish(
                    run_id,
                    RunStatus.FAILED,
                    exit_code=exit_code,
                    error_code="pipeline_failed",
                    error_message=task.last_error or task.stage_message,
                )
            elif exit_code != 0:
                message = f"Hermes exited with code {exit_code}; see {log_path}"
                self.task_store.mark_status(task_id, TaskStatus.FAILED, message)
                self.run_store.finish(
                    run_id,
                    RunStatus.FAILED,
                    exit_code=exit_code,
                    error_code="process_exit",
                    error_message=message,
                )
            elif task.status != TaskStatus.COMPLETED:
                message = "Hermes exited without finalizing the task"
                self.task_store.mark_status(task_id, TaskStatus.FAILED, message)
                self.run_store.finish(
                    run_id,
                    RunStatus.FAILED,
                    exit_code=exit_code,
                    error_code="not_finalized",
                    error_message=message,
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
            with self._lock:
                if self._processes.get(task_id) is process:
                    self._processes.pop(task_id, None)


__all__ = ["HermesRunner"]
