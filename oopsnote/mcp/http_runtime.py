"""Application-owned local HTTP transport for managed-worker MCP calls."""

from __future__ import annotations

import asyncio
import secrets
import socket
import threading
import time
from typing import Any, Optional

import uvicorn

from oopsnote.mcp.restricted import create_restricted_mcp


class _BearerAuthApp:
    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.expected = f"Bearer {token}".encode("ascii")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            headers = dict(scope.get("headers") or [])
            if headers.get(b"authorization") != self.expected:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                    }
                )
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await self.app(scope, receive, send)


class SharedMcpHttpRuntime:
    """Run one loopback-only MCP server shared by all RPC workers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._socket: Optional[socket.socket] = None
        self._url: Optional[str] = None
        self._token: Optional[str] = None

    def start(self) -> dict[str, str]:
        with self._lock:
            if self._url and self._token:
                return self.environment()

            token = secrets.token_urlsafe(32)
            mcp = create_restricted_mcp(stateless_http=True)
            app = _BearerAuthApp(mcp.streamable_http_app(), token)
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            listener.setblocking(False)
            port = listener.getsockname()[1]
            config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=port,
                log_level="warning",
                lifespan="on",
            )
            server = uvicorn.Server(config)
            thread = threading.Thread(
                target=lambda: asyncio.run(server.serve(sockets=[listener])),
                name="oopsnote-mcp-http",
                daemon=True,
            )
            self._server = server
            self._thread = thread
            self._socket = listener
            self._url = f"http://127.0.0.1:{port}/mcp"
            self._token = token
            thread.start()

        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not server.started:
            self.shutdown()
            raise RuntimeError("Shared OopsNote MCP HTTP server did not start")
        return self.environment()

    def environment(self) -> dict[str, str]:
        if not self._url or not self._token:
            raise RuntimeError("Shared OopsNote MCP HTTP server is not running")
        return {
            "OOPSNOTE_MCP_URL": self._url,
            "OOPSNOTE_MCP_TOKEN": self._token,
        }

    def shutdown(self) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            listener = self._socket
            self._server = None
            self._thread = None
            self._socket = None
            self._url = None
            self._token = None
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        if listener is not None:
            try:
                listener.close()
            except OSError:
                pass


__all__ = ["SharedMcpHttpRuntime"]
