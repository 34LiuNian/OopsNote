"""Application-owned local HTTP transport for managed-worker MCP calls."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import uvicorn

from oopsnote.core import WorkspaceId, WorkspaceStores
from oopsnote.mcp.context import McpCapability, McpStores, activate_capability, reset_capability
from oopsnote.mcp.restricted import create_restricted_mcp


class _CapabilityAuthApp:
    def __init__(self, app: Any, runtime: SharedMcpHttpRuntime) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            headers = dict(scope.get("headers") or [])
            raw = headers.get(b"authorization", b"")
            prefix = b"Bearer "
            token = (
                raw[len(prefix) :].decode("ascii", errors="ignore")
                if raw.startswith(prefix)
                else ""
            )
            try:
                capability = self.runtime.capability_for_token(token)
            except KeyError:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                    }
                )
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
            context_token = activate_capability(capability) if capability is not None else None
            try:
                await self.app(scope, receive, send)
            finally:
                if context_token is not None:
                    reset_capability(context_token)
            return
        await self.app(scope, receive, send)


class SharedMcpHttpRuntime:
    """Run one loopback-only MCP server shared by all RPC workers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._url: str | None = None
        self._token: str | None = None
        self._tokens: dict[str, McpCapability | None] = {}
        self._workspace_tokens: dict[WorkspaceId, str] = {}

    def start(self) -> dict[str, str]:
        with self._lock:
            if self._url and self._token:
                return self.environment()

            token = secrets.token_urlsafe(32)
            mcp = create_restricted_mcp(stateless_http=True)
            self._tokens[token] = None
            app = _CapabilityAuthApp(mcp.streamable_http_app(), self)
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

    def environment_for(
        self,
        workspace_id: WorkspaceId,
        stores: WorkspaceStores,
        *,
        ttl_seconds: int = 3_600,
    ) -> dict[str, str]:
        """Return a loopback token scoped to one workspace's physical stores."""
        workspace = WorkspaceId.parse(workspace_id)
        with self._lock:
            if not self._url or not self._token:
                raise RuntimeError("Shared OopsNote MCP HTTP server is not running")
            token = self._workspace_tokens.get(workspace)
            if token is not None:
                capability = self._tokens.get(token)
                if capability is None or not capability.is_valid():
                    self._tokens.pop(token, None)
                    self._workspace_tokens.pop(workspace, None)
                    token = None
            if token is None:
                token = secrets.token_urlsafe(32)
                self._workspace_tokens[workspace] = token
                self._tokens[token] = McpCapability(
                    workspace_id=workspace,
                    stores=McpStores(
                        task_store=stores.task_store,
                        tag_store=stores.tag_store,
                        asset_store=stores.asset_store,
                        run_store=stores.run_store,
                    ),
                    expires_at=datetime.now(UTC) + timedelta(seconds=max(60, ttl_seconds)),
                )
            return {"OOPSNOTE_MCP_URL": self._url, "OOPSNOTE_MCP_TOKEN": token}

    def capability_for_token(self, token: str) -> McpCapability | None:
        with self._lock:
            if token not in self._tokens:
                raise KeyError(token)
            capability = self._tokens[token]
            if capability is not None and not capability.is_valid():
                self._tokens.pop(token, None)
                self._workspace_tokens.pop(capability.workspace_id, None)
                raise KeyError(token)
            return capability

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
            self._tokens.clear()
            self._workspace_tokens.clear()
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
        if listener is not None:
            with contextlib.suppress(OSError):
                listener.close()


__all__ = ["SharedMcpHttpRuntime"]
