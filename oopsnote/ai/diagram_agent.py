"""Transport-neutral contracts for the bounded TikZ reconstruction tool loop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from oopsnote.core import DiagramRunMode, DiagramRunStep, DiagramTransport

SUBMIT_TIKZ_REVISION = "submit_tikz_revision"
ACCEPT_TIKZ_CANDIDATE = "accept_tikz_candidate"
KEEP_SOURCE_IMAGE = "keep_source_image"
REQUEST_DIAGRAM_REVIEW = "request_diagram_review"
DIAGRAM_TOOL_NAMES = frozenset(
    {
        SUBMIT_TIKZ_REVISION,
        ACCEPT_TIKZ_CANDIDATE,
        KEEP_SOURCE_IMAGE,
        REQUEST_DIAGRAM_REVIEW,
    }
)


def run_candidates(run: Any, item: Any) -> list[Any]:
    return [candidate for candidate in item.candidates if candidate.run_id == run.id]


def active_candidate(run: Any, item: Any) -> Any | None:
    if not run.diagram_candidate_id:
        return None
    return next(
        (candidate for candidate in item.candidates if candidate.id == run.diagram_candidate_id),
        None,
    )


def legal_diagram_tools(run: Any, item: Any) -> frozenset[str]:
    """Derive the only legal model actions from durable diagram state."""

    if run.diagram_step == DiagramRunStep.RENDER:
        return frozenset()
    candidates = run_candidates(run, item)
    at_limit = len(candidates) >= int(run.diagram_max_candidates or 0)
    candidate = active_candidate(run, item)
    allow_keep = run.diagram_mode == DiagramRunMode.AUTO
    names: set[str] = set()
    if run.diagram_step == DiagramRunStep.REVIEW:
        if candidate is None or not candidate.png_path:
            raise ValueError("diagram review requires a rendered active candidate")
        names.add(ACCEPT_TIKZ_CANDIDATE)
        names.add(REQUEST_DIAGRAM_REVIEW if at_limit else SUBMIT_TIKZ_REVISION)
    elif run.diagram_step == DiagramRunStep.GENERATE:
        if at_limit:
            names.add(REQUEST_DIAGRAM_REVIEW)
        else:
            names.add(SUBMIT_TIKZ_REVISION)
    else:
        raise ValueError("diagram run has no legal agent stage")
    if allow_keep:
        names.add(KEEP_SOURCE_IMAGE)
    return frozenset(names)


@dataclass(frozen=True, slots=True)
class EncodedDiagramToolResult:
    tool_content: str | list[dict[str, Any]]
    followup_content: list[dict[str, Any]] | None = None


def encode_diagram_tool_result(
    payload: dict[str, Any],
    *,
    transport: DiagramTransport,
    image_content: dict[str, Any] | None = None,
    followup_text: str | None = None,
) -> EncodedDiagramToolResult:
    """Encode one semantic tool result without changing the diagram workflow."""

    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    if image_content is None:
        return EncodedDiagramToolResult(tool_content=text)
    if transport == DiagramTransport.NATIVE_TOOL_IMAGE:
        return EncodedDiagramToolResult(
            tool_content=[{"type": "text", "text": text}, image_content],
        )
    if transport == DiagramTransport.MESSAGE_IMAGE_BRIDGE:
        if not followup_text:
            raise ValueError("message image bridge requires a follow-up prompt")
        return EncodedDiagramToolResult(
            tool_content=text,
            followup_content=[
                {
                    "type": "text",
                    "text": followup_text,
                },
                image_content,
            ],
        )
    raise ValueError(f"unsupported diagram transport: {transport}")


__all__ = [
    "ACCEPT_TIKZ_CANDIDATE",
    "DIAGRAM_TOOL_NAMES",
    "KEEP_SOURCE_IMAGE",
    "REQUEST_DIAGRAM_REVIEW",
    "SUBMIT_TIKZ_REVISION",
    "EncodedDiagramToolResult",
    "active_candidate",
    "encode_diagram_tool_result",
    "legal_diagram_tools",
    "run_candidates",
]
