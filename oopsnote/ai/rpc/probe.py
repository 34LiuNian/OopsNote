"""Small, model-free startup probe for JSONL RPC runtimes."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RpcSessionProbeResult:
    success: bool
    events: tuple[dict[str, object], ...]
    stderr: tuple[str, ...]

    @property
    def failure_detail(self) -> str:
        if self.stderr:
            return self.stderr[-1]
        if self.events:
            return json.dumps(self.events[-1], ensure_ascii=False)
        return "no response"


def _read_lines(
    stream: object,
    output: queue.Queue[str | None],
) -> None:
    try:
        readline = stream.readline
        for line in iter(readline, ""):
            output.put(line.rstrip("\r\n"))
    finally:
        output.put(None)


def _close_stream(stream: object | None) -> None:
    if stream is None:
        return
    close = getattr(stream, "close", None)
    if close is not None:
        close()


def _stop_process(process: subprocess.Popen[str]) -> None:
    # Closing stdin is part of the probe lifecycle: a runtime waiting for its
    # next request must not keep the probe alive after the result is known.
    _close_stream(process.stdin)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    # Popen does not close pipes when wait() returns.  Close every owned pipe
    # here so repeated startup probes do not leak descriptors or trigger
    # ResourceWarning during diagnostics and tests.
    _close_stream(process.stdout)
    _close_stream(process.stderr)


def probe_new_session(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: float = 30,
) -> RpcSessionProbeResult:
    """Keep stdin open until a clean-session response arrives, then stop the probe."""

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(environment),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    stdout: queue.Queue[str | None] = queue.Queue()
    stderr: queue.Queue[str | None] = queue.Queue()
    stdout_reader = threading.Thread(
        target=_read_lines,
        args=(process.stdout, stdout),
        daemon=True,
    )
    stderr_reader = threading.Thread(
        target=_read_lines,
        args=(process.stderr, stderr),
        daemon=True,
    )
    stdout_reader.start()
    stderr_reader.start()

    command_id = "setup-probe"
    events: list[dict[str, object]] = []
    success = False
    deadline = time.monotonic() + timeout_seconds
    try:
        process.stdin.write(json.dumps({"id": command_id, "type": "new_session"}) + "\n")
        process.stdin.flush()
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                line = stdout.get(timeout=min(0.25, remaining))
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            if line is None:
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            events.append(event)
            if event.get("type") == "response" and event.get("id") == command_id:
                data = event.get("data")
                success = event.get("success") is True and not (
                    isinstance(data, dict) and data.get("cancelled")
                )
                break
    finally:
        _stop_process(process)
        stdout_reader.join(timeout=1)
        stderr_reader.join(timeout=1)

    errors: list[str] = []
    while True:
        try:
            line = stderr.get_nowait()
        except queue.Empty:
            break
        if line:
            errors.append(line)
    return RpcSessionProbeResult(success, tuple(events), tuple(errors))
