"""Canonical MCP-contract tools for the LangChain execution adapter."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from oopsnote.mcp.contracts import load_tool_contract


class RestrictedMcpToolClient(Protocol):
    async def call(self, remote_name: str, arguments: dict[str, Any]) -> Any: ...


class McpHttpToolClient:
    """Stateless authenticated calls to OopsNote's loopback MCP boundary."""

    def __init__(self, url: str, bearer_token: str) -> None:
        self.url = url
        self.headers = {"Authorization": f"Bearer {bearer_token}"}

    async def call(self, remote_name: str, arguments: dict[str, Any]) -> Any:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(self.url, headers=self.headers) as streams:
            read_stream, write_stream, _ = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(remote_name, arguments)
        if getattr(result, "isError", False):
            raise RuntimeError(str(getattr(result, "content", "MCP tool failed")))
        return result.model_dump(mode="json")


def langchain_tool_schemas() -> list[dict[str, Any]]:
    """Derive provider function schemas directly from the canonical contract."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": deepcopy(tool["parameters"]),
            },
        }
        for tool in load_tool_contract()["tools"]
    ]


class ContractBoundToolDispatcher:
    def __init__(
        self,
        client: RestrictedMcpToolClient,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self.client = client
        self._tools = {tool["name"]: tool for tool in load_tool_contract()["tools"]}
        self._task_id = task_id
        self._run_id = run_id

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            tool = self._tools[name]
        except KeyError as error:
            raise ValueError(f"tool is not in the restricted contract: {name}") from error
        arguments = dict(arguments)
        for field, expected in (("task_id", self._task_id), ("run_id", self._run_id)):
            if expected is None:
                continue
            actual = arguments.get(field)
            if actual is not None and actual != expected:
                raise ValueError(f"{name} may only use the active {field}")
            arguments[field] = expected
        # The MCP server remains the authoritative validation boundary.
        return await self.client.call(tool["remoteName"], arguments)


__all__ = ["ContractBoundToolDispatcher", "McpHttpToolClient", "RestrictedMcpToolClient", "langchain_tool_schemas"]
