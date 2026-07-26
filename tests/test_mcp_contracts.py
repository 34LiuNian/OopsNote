from __future__ import annotations

from oopsnote.mcp.contracts import (
    TOOL_CONTRACT,
    build_tool_contract,
    canonicalize_tool_schema,
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
        "finalize_task",
        "fail_task",
    ):
        assert "run_id" in tools[name]["parameters"]["required"]
