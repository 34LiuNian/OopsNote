from __future__ import annotations

import pytest

from oopsnote.mcp.contracts import (
    TOOL_CONTRACT,
    build_tool_contract,
    canonicalize_tool_schema,
    load_tool_contract,
)
from oopsnote.mcp.restricted import create_restricted_mcp


def test_canonical_contract_matches_fastmcp_input_surface():
    runtime = {
        tool.name: tool.parameters
        for tool in create_restricted_mcp()._tool_manager.list_tools()
    }
    canonical = {
        tool["remoteName"]: tool["parameters"]
        for tool in TOOL_CONTRACT["tools"]
    }

    assert runtime.keys() == canonical.keys()
    assert {
        name: canonicalize_tool_schema(schema)
        for name, schema in runtime.items()
    } == canonical
    assert build_tool_contract() == TOOL_CONTRACT


def test_every_task_data_tool_requires_active_run_binding():
    tools = {tool["remoteName"]: tool for tool in TOOL_CONTRACT["tools"]}
    for name in (
        "ocr_image",
        "get_task",
        "get_asset_path",
        "list_tags",
        "create_tag",
        "report_task_stage",
        "submit_solution_candidate",
        "finalize_task",
        "fail_task",
    ):
        assert "run_id" in tools[name]["parameters"]["required"]


def test_contract_marks_only_read_only_tools_as_parallel_safe():
    tools = {tool["remoteName"]: tool["executionMode"] for tool in TOOL_CONTRACT["tools"]}

    assert {name for name, mode in tools.items() if mode == "parallel"} == {
        "get_task",
        "get_asset_path",
        "list_tags",
    }


def test_contract_loader_rejects_a_registry_mismatch(tmp_path, monkeypatch):
    from oopsnote.mcp import contracts

    stale = tmp_path / "tool_contracts.json"
    stale.write_text('{"version": 1, "tools": []}', encoding="utf-8")
    monkeypatch.setattr(contracts, "CONTRACT_PATH", stale)

    with pytest.raises(ValueError, match="does not match the Python registry"):
        load_tool_contract()
