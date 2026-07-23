"""Problem search, tag, settings, and synchronization routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from oopsnote.api.schemas import TagInput, TagRenameInput
from oopsnote.core import Problem, Searcher, SearchQuery, TagDimension
from oopsnote.obsidian.syncer import ObsidianSyncer

router = APIRouter()


def _api():
    from oopsnote.api import main

    return main


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid ISO datetime")


@router.get("/problems")
def list_problems(
    subject: Optional[str] = None,
    source: Optional[list[str]] = Query(default=None),
    knowledge_tag: Optional[list[str]] = Query(default=None),
    error_tag: Optional[list[str]] = Query(default=None),
    user_tag: Optional[list[str]] = Query(default=None),
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    after = _parse_iso(created_after)
    before = _parse_iso(created_before)
    items: list[dict[str, Any]] = []
    for task in api.TASK_STORE.list_all():
        problem = task.problem
        if not problem:
            continue
        item = api._problem_summary(task, problem)
        if subject and item["subject"] != subject:
            continue
        if source and item["source"] not in source:
            continue
        if knowledge_tag and not set(knowledge_tag).issubset(
            item["knowledge_tags"]
        ):
            continue
        if error_tag and not set(error_tag).issubset(item["error_tags"]):
            continue
        if user_tag and not set(user_tag).issubset(item["user_tags"]):
            continue
        created = problem.created_at
        if after and created < after:
            continue
        if before and created > before:
            continue
        items.append(item)
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"items": items}


@router.get("/search")
def search(
    tags: Optional[str] = Query(default=None),
    subject: Optional[str] = None,
    since: Optional[str] = None,
    error_type: Optional[str] = None,
    regex: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, list[Problem]]:
    api = _api()
    query = SearchQuery(
        tags=[tag.strip() for tag in tags.split(",") if tag.strip()]
        if tags
        else [],
        subject=subject,
        since=since,
        error_type=error_type,
        regex=regex,
        limit=limit,
    )
    return {"results": Searcher(api.TASK_STORE.list_all()).search(query)}


@router.get("/tags")
def list_tags(
    dimension: Optional[TagDimension] = None,
    query: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    return {
        "items": [
            item.model_dump(mode="json")
            for item in api.TAG_STORE.search(dimension, query, limit)
        ]
    }


@router.post("/tags")
def create_tag(payload: TagInput) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    api.TAG_STORE.upsert(
        payload.dimension,
        payload.value,
        payload.aliases,
        payload.subject,
    )
    return list_tags(dimension=payload.dimension, query=payload.value)


@router.get("/tags/dimensions")
@router.get("/settings/tag-dimensions")
def get_tag_dimensions() -> dict[str, Any]:
    return {"dimensions": _api().TAG_DIMENSIONS}


@router.put("/settings/tag-dimensions")
def update_tag_dimensions(payload: dict[str, Any]) -> dict[str, Any]:
    api = _api()
    dimensions = payload.get("dimensions")
    if isinstance(dimensions, dict):
        for key, value in dimensions.items():
            if key in api.TAG_DIMENSIONS and isinstance(value, dict):
                api.TAG_DIMENSIONS[key] = value
    return {"dimensions": api.TAG_DIMENSIONS}


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: str) -> dict[str, Any]:
    api = _api()
    if not api.TAG_STORE.delete(tag_id):
        raise HTTPException(status_code=404, detail="User tag not found")
    return {"ok": True, "tag_id": tag_id}


@router.put("/tags/{tag_id}")
def rename_tag(
    tag_id: str,
    payload: TagRenameInput,
) -> dict[str, list[dict[str, Any]]]:
    api = _api()
    existing = api.TAG_STORE.get_by_id(tag_id)
    if not existing or existing.source != "user":
        raise HTTPException(status_code=404, detail="User tag not found")
    value = payload.value.strip()
    if not value:
        raise HTTPException(status_code=422, detail="Tag value is required")
    if value != existing.value:
        api.TAG_STORE.delete(tag_id)
        api.TAG_STORE.upsert(
            existing.dimension,
            value,
            existing.aliases,
            existing.subject,
        )
    return list_tags(dimension=existing.dimension, query=value)


@router.post("/tags/{source_id}/merge")
def merge_tags(source_id: str, payload: dict[str, str]) -> dict[str, Any]:
    api = _api()
    source = api.TAG_STORE.get_by_id(source_id)
    target = api.TAG_STORE.get_by_id(payload.get("target_id", ""))
    if (
        not source
        or source.source != "user"
        or not target
        or source.dimension != target.dimension
    ):
        raise HTTPException(
            status_code=404,
            detail="Compatible source and target tags are required",
        )
    api.TAG_STORE.delete(source_id)
    api.TAG_STORE.upsert(
        target.dimension,
        target.value,
        [*target.aliases, source.value, *source.aliases],
        target.subject,
    )
    return {"ok": True, "tasks_modified": 0, "fields_modified": 0}


@router.post("/sync")
def sync(subject: Optional[str] = None) -> dict[str, str]:
    api = _api()
    syncer = ObsidianSyncer(task_store=api.TASK_STORE, tag_store=api.TAG_STORE)
    report = syncer.sync_for_subject(subject) if subject else syncer.sync()
    return {"message": str(report)}


__all__ = ["router"]
