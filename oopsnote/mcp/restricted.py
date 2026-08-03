"""Restricted MCP surface exposed to managed AI workers."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from oopsnote.core import TagDimension
from oopsnote.mcp import server
from oopsnote.mcp import ocr
from oopsnote.mcp.tool_registry import AI_TOOL_NAMES, MANAGED_TOOL_DEFINITIONS


def _managed_subject(task, subject: Optional[str]) -> str:
    requested = (subject or "").strip()
    if task.subject not in {"", "auto"}:
        if requested and requested != task.subject:
            raise ValueError(
                f"subject {requested} does not match managed task subject {task.subject}"
            )
        return task.subject
    if not requested:
        raise ValueError("subject is required for an auto-subject managed task")
    return requested


def managed_list_tags(
    dimension: Literal["knowledge", "error", "meta", "custom"],
    task_id: str,
    run_id: str,
    subject: Optional[str] = None,
    scope: Optional[str] = "core",
    branch_ids: Optional[
        Annotated[list[str], Field(min_length=1, max_length=6)]
    ] = None,
):
    """List tags for one active run and remember its selected knowledge branches."""

    task = server._require_active_run(task_id, run_id)
    effective_subject = _managed_subject(task, subject)
    result = server.list_tags(
        dimension=dimension,
        subject=effective_subject,
        scope=scope,
        branch_ids=branch_ids,
    )
    if dimension == TagDimension.KNOWLEDGE.value and result.get("mode") == "leaves":
        metadata = dict(task.metadata)
        metadata["_managed_tag_selection"] = {
            "run_id": run_id,
            "subject": effective_subject,
            "scope": scope,
            "branch_ids": result["branch_ids"],
        }
        server.TASK_STORE.transition(
            task_id,
            expected_statuses={server.TaskStatus.PROCESSING},
            expected_active_run_id=run_id,
            metadata=metadata,
        )
    elif dimension == TagDimension.ERROR.value and result.get("mode") == "values":
        metadata = dict(task.metadata)
        metadata["_managed_error_candidates"] = {
            "run_id": run_id,
            "subject": effective_subject,
            "scope": scope,
            "values": list(result["items"]),
        }
        server.TASK_STORE.transition(
            task_id,
            expected_statuses={server.TaskStatus.PROCESSING},
            expected_active_run_id=run_id,
            metadata=metadata,
        )
    return result


def _existing_error_equivalent(value: str, subject: str) -> Optional[str]:
    normalized = value.strip().casefold()
    for item in server.TAG_STORE.search(
        dimension=TagDimension.ERROR,
        subject=subject,
        scope="core",
        limit=None,
    ):
        if normalized == item.value.casefold() or any(
            normalized == alias.casefold() for alias in item.aliases
        ):
            return item.value
    return None


def managed_create_tag(
    dimension: Literal["error"],
    value: str,
    task_id: str,
    run_id: str,
    aliases: Optional[list[str]] = None,
    subject: Optional[str] = None,
):
    """Create only an error tag for one active managed run."""

    task = server._require_active_run(task_id, run_id)
    if dimension != TagDimension.ERROR.value:
        raise ValueError("managed AI may create only error tags")
    effective_subject = _managed_subject(task, subject)
    candidates = task.metadata.get("_managed_error_candidates")
    if (
        not isinstance(candidates, dict)
        or candidates.get("run_id") != run_id
        or candidates.get("subject") != effective_subject
    ):
        raise ValueError("list existing error tags before creating a new error tag")
    for proposed in [value, *(aliases or [])]:
        equivalent = _existing_error_equivalent(proposed, effective_subject)
        if equivalent:
            raise ValueError(
                f"error tag {proposed.strip()} matches existing candidate {equivalent}; use it instead"
            )
    return server.create_tag(
        dimension=dimension,
        value=value,
        aliases=aliases,
        subject=effective_subject,
    )


def managed_ocr_image(task_id: str, run_id: str):
    """Run OCR and persist provider failures before returning a tool error."""

    try:
        result = ocr.ocr_image(task_id, run_id)
    except ocr.OcrProviderError as error:
        server._fail_active_task(
            task_id,
            str(error),
            run_id=run_id,
            error_code=error.code,
        )
        raise
    if result.get("review_reason") == "unreadable":
        server._fail_active_task(
            task_id,
            "OCR could not read a complete question",
            run_id=run_id,
            error_code="ocr_unreadable",
            review_reason="unreadable",
        )
    return result


def create_restricted_mcp(**kwargs) -> FastMCP:
    """Create a server containing only the managed pipeline's allowed tools."""
    instance = FastMCP("OopsNote Managed Pipeline", log_level="WARNING", **kwargs)
    overrides = {
        "ocr_image": managed_ocr_image,
        "list_tags": managed_list_tags,
        "create_tag": managed_create_tag,
    }
    for definition in MANAGED_TOOL_DEFINITIONS:
        tool_name = definition.remote_name
        function = overrides.get(tool_name) or getattr(server, tool_name)
        instance.tool(
            name=tool_name,
            description=definition.description,
        )(function)
    return instance


mcp = create_restricted_mcp()


def main() -> None:
    """Run the managed-worker tool subset over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


__all__ = [
    "create_restricted_mcp",
    "managed_create_tag",
    "managed_ocr_image",
    "managed_list_tags",
    "AI_TOOL_NAMES",
]
