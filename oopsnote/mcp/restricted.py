"""Restricted MCP surface exposed to managed AI workers."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from oopsnote.mcp import server
from oopsnote.mcp.ocr import ocr_image


AI_TOOL_NAMES = (
    "ocr_image",
    "get_task",
    "get_asset_path",
    "list_tags",
    "create_tag",
    "report_task_stage",
    "finalize_task",
    "fail_task",
)


def create_restricted_mcp(**kwargs) -> FastMCP:
    """Create a server containing only the managed pipeline's allowed tools."""
    instance = FastMCP("OopsNote Managed Pipeline", log_level="WARNING", **kwargs)
    for tool_name in AI_TOOL_NAMES:
        function = ocr_image if tool_name == "ocr_image" else getattr(server, tool_name)
        instance.tool()(function)
    return instance


mcp = create_restricted_mcp()


def main() -> None:
    """Run the managed-worker tool subset over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
