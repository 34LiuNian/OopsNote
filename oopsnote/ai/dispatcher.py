"""Bounded in-process dispatcher for persisted managed runs."""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Optional

from oopsnote.core import RunStatus, TaskRun, TaskStatus

if TYPE_CHECKING:
    from oopsnote.ai.managed import ManagedAiRunner


class ManagedTaskDispatcher:
    """Feed persisted runs to a fixed number of runner threads.

    The queue is an execution accelerator, not the source of truth. QUEUED run
    records can be loaded again after an application restart.
    """

    def __init__(self, runner: "ManagedAiRunner", workers: int) -> None:
        self.runner = runner
        self.workers = max(1, workers)
        self._queue: queue.Queue[Optional[tuple[str, str]]] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._started = False
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._scheduled: set[str] = set()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            for index in range(self.workers):
                thread = threading.Thread(
                    target=self._run,
                    name=f"{self.runner.backend_name}-dispatcher-{index + 1}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()

    def submit(self, task_id: str) -> TaskRun:
        run = self.runner.enqueue(task_id)
        self.schedule(task_id, run.id)
        return run

    def schedule(self, task_id: str, run_id: str) -> None:
        self.start()
        with self._lock:
            if run_id in self._scheduled:
                return
            self._scheduled.add(run_id)
        self._queue.put((task_id, run_id))

    def recover_queued(self) -> int:
        recovered = 0
        for run in sorted(self.runner.run_store.list_all(), key=lambda item: item.queued_at):
            if (
                run.status != RunStatus.QUEUED
                or run.backend != self.runner.backend_name
            ):
                continue
            try:
                task = self.runner.task_store.get(run.task_id)
            except KeyError:
                continue
            if task.status != TaskStatus.PROCESSING or task.active_run_id != run.id:
                continue
            self.schedule(run.task_id, run.id)
            recovered += 1
        return recovered

    def status(self) -> dict[str, int]:
        with self._lock:
            return {
                "workers": self.workers,
                "queued": self._queue.qsize(),
                "scheduled": len(self._scheduled),
            }

    def shutdown(self) -> None:
        with self._lock:
            if not self._started or self._stopping.is_set():
                return
            self._stopping.set()
        for _ in self._threads:
            self._queue.put(None)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                task_id, run_id = item
                try:
                    self.runner.run(task_id, run_id)
                except Exception as error:
                    # One malformed/deleted task must not permanently shrink the
                    # fixed dispatcher pool. Persist the failure when possible,
                    # then continue with the next queued run.
                    try:
                        self.runner.run_store.finish(
                            run_id,
                            RunStatus.FAILED,
                            error_code="dispatcher_error",
                            error_message=str(error),
                        )
                    except KeyError:
                        pass
                    try:
                        task = self.runner.task_store.get(task_id)
                        if task.active_run_id == run_id:
                            self.runner.task_store.transition(
                                task_id,
                                expected_statuses={TaskStatus.PROCESSING},
                                expected_active_run_id=run_id,
                                status=TaskStatus.FAILED,
                                active_run_id=None,
                                last_error=str(error),
                            )
                    except (KeyError, RuntimeError):
                        pass
            finally:
                if item is not None:
                    with self._lock:
                        self._scheduled.discard(item[1])
                self._queue.task_done()


__all__ = ["ManagedTaskDispatcher"]
