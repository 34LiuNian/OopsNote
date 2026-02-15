from __future__ import annotations

from fastapi import APIRouter, Request

from ..tags import (
    TagCreateRequest,
    TagDimension,
    TagDimensionsResponse,
    TagDimensionsUpdateRequest,
    TagsResponse,
    tag_store,
)
from .deps import get_backend_state

router = APIRouter()


def _tasks_service(request: Request):
    """Resolve task service from app state for read-only tag reference counting."""
    try:
        state = get_backend_state(request)
    except Exception:
        return None
    return getattr(state, "tasks", None)


@router.get("/tags", response_model=TagsResponse)
def list_tags(
    request: Request,
    dimension: TagDimension | None = None,
    query: str | None = None,
    limit: int = 50,
) -> TagsResponse:
    q = (query or "").strip()
    lim = max(1, int(limit))

    def _inc(counter: dict[str, int], value: str | None) -> None:
        if not value:
            return
        s = str(value).strip()
        if not s:
            return
        key = s.casefold()
        counter[key] = counter.get(key, 0) + 1

    def _inc_many(counter: dict[str, int], values) -> None:
        if not values:
            return
        for v in values:
            _inc(counter, v)

    ref_counts: dict[str, int] = {}
    try:
        tasks_service = _tasks_service(request)
        tasks = tasks_service.iter_tasks() if tasks_service is not None else []

        for task in tasks:
            payload = getattr(task, "payload", None)
            if payload is not None:
                if dimension in (None, TagDimension.KNOWLEDGE):
                    _inc_many(ref_counts, getattr(payload, "knowledge_tags", None))
                if dimension in (None, TagDimension.ERROR):
                    _inc_many(ref_counts, getattr(payload, "error_tags", None))
                if dimension in (None, TagDimension.CUSTOM):
                    _inc_many(ref_counts, getattr(payload, "user_tags", None))
                if dimension in (None, TagDimension.META):
                    _inc(ref_counts, getattr(payload, "source", None))

            for p in getattr(task, "problems", []) or []:
                if dimension in (None, TagDimension.KNOWLEDGE):
                    _inc_many(ref_counts, getattr(p, "knowledge_tags", None))
                if dimension in (None, TagDimension.ERROR):
                    _inc_many(ref_counts, getattr(p, "error_tags", None))
                if dimension in (None, TagDimension.CUSTOM):
                    _inc_many(ref_counts, getattr(p, "user_tags", None))
                if dimension in (None, TagDimension.META):
                    _inc(ref_counts, getattr(p, "source", None))
    except Exception:
        ref_counts = {}

    if not q:
        base = tag_store.list(dimension=dimension, limit=5000)
        base.sort(
            key=lambda t: (-ref_counts.get(t.value.casefold().strip(), 0), t.value)
        )
        items = base[:lim]
    else:
        candidates = tag_store.search(dimension=dimension, query=q, limit=5000)
        qkey = q.casefold()

        def _tier(t) -> int:
            val = str(getattr(t, "value", "")).casefold()
            if val.startswith(qkey):
                return 0
            if qkey in val:
                return 1
            aliases = getattr(t, "aliases", []) or []
            if any(qkey in str(a).casefold() for a in aliases):
                return 2
            return 3

        candidates.sort(
            key=lambda t: (
                _tier(t),
                -ref_counts.get(str(getattr(t, "value", "")).casefold().strip(), 0),
                str(getattr(t, "value", "")),
            )
        )
        items = candidates[:lim]

    from ..tags import TagItemView

    return TagsResponse(
        items=[
            TagItemView(
                **t.model_dump(mode="json"),
                ref_count=ref_counts.get(t.value.casefold().strip(), 0),
            )
            for t in items
        ]
    )


@router.post("/tags", response_model=TagsResponse, status_code=201)
def create_tag(payload: TagCreateRequest) -> TagsResponse:
    item, _created = tag_store.upsert(
        payload.dimension, payload.value, aliases=payload.aliases
    )
    from ..tags import TagItemView

    return TagsResponse(
        items=[TagItemView(**item.model_dump(mode="json"), ref_count=0)]
    )


@router.get("/settings/tag-dimensions", response_model=TagDimensionsResponse)
def get_tag_dimensions() -> TagDimensionsResponse:
    return TagDimensionsResponse(dimensions=tag_store.load_dimensions())


@router.put("/settings/tag-dimensions", response_model=TagDimensionsResponse)
def update_tag_dimensions(payload: TagDimensionsUpdateRequest) -> TagDimensionsResponse:
    saved = tag_store.save_dimensions(payload.dimensions)
    return TagDimensionsResponse(dimensions=saved)
