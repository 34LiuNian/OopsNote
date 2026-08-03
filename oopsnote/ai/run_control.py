"""Backend-neutral control of one active managed run.

The managed lifecycle owns terminal state.  Controls only expose whether the
underlying execution is still live and how to request its cancellation.
"""

from __future__ import annotations

import asyncio
import subprocess
import threading
from abc import ABC, abstractmethod
from typing import Any, Optional


class ActiveRunControl(ABC):
    @abstractmethod
    def cancel(self) -> None:
        """Request cancellation without writing task or run state."""

    @abstractmethod
    def is_active(self) -> bool:
        """Return whether the underlying execution still exists."""

    @property
    def exit_code(self) -> Optional[int]:
        return None


class ProcessRunControl(ActiveRunControl):
    def __init__(self, process: subprocess.Popen[Any]) -> None:
        self.process = process

    def cancel(self) -> None:
        if self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def is_active(self) -> bool:
        return self.process.poll() is None

    @property
    def exit_code(self) -> Optional[int]:
        return self.process.poll()


class AsyncioTaskRunControl(ActiveRunControl):
    """Thread-safe cancellation adapter for a task owned by an event loop."""

    def __init__(self, task: asyncio.Task[Any], loop: asyncio.AbstractEventLoop) -> None:
        self._task = task
        self._loop = loop
        self._cancelled = threading.Event()
        self._done = threading.Event()
        self._owner_thread_id = threading.get_ident()
        task.add_done_callback(lambda _: self._done.set())

    def cancel(self) -> None:
        self._cancelled.set()
        if self._task.done():
            return
        if self._loop.is_running() and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._task.cancel)
            if threading.get_ident() != self._owner_thread_id:
                self._done.wait(timeout=5)

    def is_active(self) -> bool:
        return not self._task.done()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()


__all__ = ["ActiveRunControl", "AsyncioTaskRunControl", "ProcessRunControl"]
