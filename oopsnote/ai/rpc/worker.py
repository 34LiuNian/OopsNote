"""Mutable state owned by one serial JSONL RPC worker."""

from __future__ import annotations

import queue
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass(eq=False)
class RpcWorkerState:
    """One reusable child process and its isolated transport queues."""

    worker_id: str
    process: Optional[subprocess.Popen[str]] = None
    stdout: queue.Queue[Optional[str]] = field(default_factory=queue.Queue)
    stderr: queue.Queue[Optional[str]] = field(default_factory=queue.Queue)
    write_lock: threading.Lock = field(default_factory=threading.Lock)

    def reset_streams(self) -> None:
        self.stdout = queue.Queue()
        self.stderr = queue.Queue()
