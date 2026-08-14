"""Mutable state owned by one serial JSONL RPC worker."""

from __future__ import annotations

import queue
import subprocess
import threading
from dataclasses import dataclass, field


@dataclass(eq=False)
class RpcWorkerState:
    """One reusable child process and its isolated transport queues."""

    worker_id: str
    process: subprocess.Popen[str] | None = None
    stdout: queue.Queue[str | None] = field(default_factory=queue.Queue)
    stderr: queue.Queue[str | None] = field(default_factory=queue.Queue)
    write_lock: threading.Lock = field(default_factory=threading.Lock)

    def reset_streams(self) -> None:
        self.stdout = queue.Queue()
        self.stderr = queue.Queue()
