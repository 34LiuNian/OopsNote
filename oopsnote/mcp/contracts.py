"""Canonical managed-worker tool contract shared by setup and runtime adapters."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from oopsnote.mcp.tool_registry import AI_TOOL_NAMES, MANAGED_TOOL_DEFINITIONS


CONTRACT_PATH = Path(__file__).with_name("tool_contracts.json")


def load_tool_contract() -> dict[str, Any]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != 1 or not isinstance(payload.get("tools"), list):
        raise ValueError("Unsupported managed MCP tool contract")
    names: set[str] = set()
    remote_names: set[str] = set()
    for tool in payload["tools"]:
        name = tool.get("name")
        remote_name = tool.get("remoteName")
        parameters = tool.get("parameters")
        if not name or name in names or not remote_name or remote_name in remote_names:
            raise ValueError("Managed MCP tool names must be present and unique")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise ValueError(f"Managed MCP tool {name} has no object schema")
        if parameters.get("additionalProperties") is not False:
            raise ValueError(f"Managed MCP tool {name} must reject additional properties")
        names.add(name)
        remote_names.add(remote_name)
    expected = [(item.name, item.remote_name) for item in MANAGED_TOOL_DEFINITIONS]
    actual = [(item["name"], item["remoteName"]) for item in payload["tools"]]
    if actual != expected:
        raise ValueError("Managed MCP tool contract does not match the Python registry")
    return payload


def canonicalize_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove presentation-only schema metadata and close the root object."""

    normalized = deepcopy(schema)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("title", None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(normalized)
    normalized["additionalProperties"] = False
    return normalized


def build_tool_contract() -> dict[str, Any]:
    """Derive the transport-neutral contract from the live Python tool signatures."""

    from oopsnote.mcp.restricted import create_restricted_mcp

    runtime = {
        tool.name: tool.parameters
        for tool in create_restricted_mcp()._tool_manager.list_tools()
    }
    return {
        "version": 1,
        "tools": [
            {
                "name": definition.name,
                "remoteName": definition.remote_name,
                "description": definition.description,
                "parameters": canonicalize_tool_schema(runtime[definition.remote_name]),
            }
            for definition in MANAGED_TOOL_DEFINITIONS
        ],
    }


def sync_tool_contract() -> bool:
    """Write the generated contract when Python tool signatures changed."""

    rendered = json.dumps(build_tool_contract(), ensure_ascii=False, indent=2) + "\n"
    if CONTRACT_PATH.exists() and CONTRACT_PATH.read_text(encoding="utf-8") == rendered:
        return False
    CONTRACT_PATH.write_text(rendered, encoding="utf-8")
    return True


TOOL_CONTRACT = load_tool_contract()


__all__ = [
    "AI_TOOL_NAMES",
    "CONTRACT_PATH",
    "TOOL_CONTRACT",
    "build_tool_contract",
    "canonicalize_tool_schema",
    "load_tool_contract",
    "sync_tool_contract",
]
