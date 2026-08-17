"""Names and descriptions for the restricted managed-worker tool surface."""

from __future__ import annotations

from typing import NamedTuple


class ManagedToolDefinition(NamedTuple):
    name: str
    remote_name: str
    description: str
    execution_mode: str


MANAGED_TOOL_DEFINITIONS = (
    ManagedToolDefinition(
        "ocr_image", "ocr_image", "Extract one OopsNote task image into strict OCR JSON.", "barrier"
    ),
    ManagedToolDefinition(
        "mcp__oopsnote_pipeline_get_task",
        "get_task",
        "Get one managed OopsNote task by id.",
        "parallel",
    ),
    ManagedToolDefinition(
        "mcp__oopsnote_pipeline_get_asset_path",
        "get_asset_path",
        "Resolve the image asset bound to the active managed run.",
        "parallel",
    ),
    # The restricted wrapper persists the selected tag candidates in task
    # metadata, so these reads are write barriers for the managed pipeline.
    ManagedToolDefinition(
        "mcp__oopsnote_pipeline_list_tags",
        "list_tags",
        "List tag branches, selected branch leaves, or non-knowledge tag values.",
        "barrier",
    ),
    ManagedToolDefinition(
        "mcp__oopsnote_pipeline_create_tag",
        "create_tag",
        "Create or merge one error tag for the active managed run.",
        "barrier",
    ),
    ManagedToolDefinition(
        "mcp__oopsnote_pipeline_report_task_stage",
        "report_task_stage",
        "Report progress for the active managed OopsNote run.",
        "barrier",
    ),
    ManagedToolDefinition(
        "mcp__oopsnote_pipeline_submit_solution_candidate",
        "submit_solution_candidate",
        "Store one solver candidate for an independent verification session.",
        "barrier",
    ),
    ManagedToolDefinition(
        "mcp__oopsnote_pipeline_finalize_task",
        "finalize_task",
        "Validate and atomically finalize the active OopsNote task.",
        "barrier",
    ),
    ManagedToolDefinition(
        "mcp__oopsnote_pipeline_fail_task",
        "fail_task",
        "Fail the active OopsNote task with an explicit reason.",
        "barrier",
    ),
    ManagedToolDefinition(
        "submit_tikz_revision",
        "submit_tikz_revision",
        "Validate and persist one body-only TikZ revision for the active diagram run.",
        "barrier",
    ),
    ManagedToolDefinition(
        "accept_tikz_candidate",
        "accept_tikz_candidate",
        "Accept the active rendered TikZ candidate when no hard semantic error remains.",
        "barrier",
    ),
    ManagedToolDefinition(
        "keep_source_image",
        "keep_source_image",
        "Keep a normalized crop of the printed source diagram for an automatic diagram run.",
        "barrier",
    ),
    ManagedToolDefinition(
        "request_diagram_review",
        "request_diagram_review",
        "Finish the active diagram run for human review after its candidate limit is reached.",
        "barrier",
    ),
)

AI_TOOL_NAMES = tuple(item.remote_name for item in MANAGED_TOOL_DEFINITIONS)


__all__ = ["AI_TOOL_NAMES", "MANAGED_TOOL_DEFINITIONS", "ManagedToolDefinition"]
