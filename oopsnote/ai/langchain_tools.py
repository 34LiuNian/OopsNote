"""Canonical MCP-contract tools for the LangChain execution adapter."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from collections.abc import Collection
from typing import Any, Mapping, Protocol

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


def langchain_tool_schemas(
    names: Collection[str] | None = None,
    *,
    constants: Mapping[str, Mapping[str, Any]] | None = None,
    required_arguments: Mapping[str, Collection[str]] | None = None,
    parameter_overrides: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Derive provider schemas and state-scoped restrictions from the MCP contract.

    The contract remains the only source for tool names and parameter shapes.
    A runner may narrow a currently legal call using authoritative task/run state,
    but it cannot add a provider-only tool or parameter.
    """
    allowed = set(names) if names is not None else None
    constants = constants or {}
    required_arguments = required_arguments or {}
    parameter_overrides = parameter_overrides or {}
    schemas: list[dict[str, Any]] = []
    for tool in load_tool_contract()["tools"]:
        name = tool["name"]
        if allowed is not None and name not in allowed:
            continue
        parameters = deepcopy(tool["parameters"])
        properties = parameters["properties"]
        required = list(parameters.get("required") or [])
        for argument, value in constants.get(name, {}).items():
            if argument not in properties:
                raise ValueError(f"{name} has no canonical parameter {argument}")
            properties[argument] = {**properties[argument], "const": value}
            if argument not in required:
                required.append(argument)
        for argument in required_arguments.get(name, ()):
            if argument not in properties:
                raise ValueError(f"{name} has no canonical parameter {argument}")
            if argument not in required:
                required.append(argument)
        for argument, override in parameter_overrides.get(name, {}).items():
            if argument not in properties:
                raise ValueError(f"{name} has no canonical parameter {argument}")
            properties[argument] = {**properties[argument], **deepcopy(override)}
        parameters["required"] = required
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool["description"],
                "parameters": parameters,
            },
        })
    return schemas


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

    async def call(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        allowed_parameters: Mapping[str, dict[str, Any]] | None = None,
        fixed_arguments: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> Any:
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
        if fixed_arguments is not None:
            arguments.update(fixed_arguments.get(name, {}))
        if allowed_parameters is not None:
            parameters = allowed_parameters.get(name)
            if parameters is None:
                raise ValueError(f"{name} is not legal in the current pipeline transition")
            try:
                from jsonschema import Draft202012Validator
            except ImportError as error:
                raise RuntimeError("jsonschema is required for managed tool validation") from error
            validation_errors = list(Draft202012Validator(parameters).iter_errors(arguments))
            if validation_errors:
                message = validation_errors[0].message
                raise ValueError(f"{name} violates the current pipeline transition: {message}")
        # The MCP server remains the authoritative validation boundary.
        return await self.client.call(tool["remoteName"], arguments)

    async def call_many(
        self,
        calls: list[dict[str, Any]],
        *,
        allowed_parameters: Mapping[str, dict[str, Any]] | None = None,
        fixed_arguments: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> list[Any]:
        """Run independent calls concurrently while preserving write barriers."""
        results: list[Any] = [None] * len(calls)
        pending: list[tuple[int, dict[str, Any]]] = []

        async def flush() -> None:
            if not pending:
                return
            batch = list(pending)
            pending.clear()
            values = await asyncio.gather(
                *(
                    self.call(
                        call["name"],
                        dict(call.get("args") or {}),
                        allowed_parameters=allowed_parameters,
                        fixed_arguments=fixed_arguments,
                    )
                    for _, call in batch
                ),
                return_exceptions=True,
            )
            for (index, _), value in zip(batch, values):
                results[index] = value

        for index, call in enumerate(calls):
            tool = self._tools.get(call.get("name"))
            if tool is not None and tool.get("executionMode") == "parallel":
                pending.append((index, call))
                continue
            await flush()
            try:
                results[index] = await self.call(
                    call["name"],
                    dict(call.get("args") or {}),
                    allowed_parameters=allowed_parameters,
                    fixed_arguments=fixed_arguments,
                )
            except Exception as error:
                results[index] = error
        await flush()
        return results


__all__ = ["ContractBoundToolDispatcher", "McpHttpToolClient", "RestrictedMcpToolClient", "langchain_tool_schemas"]
