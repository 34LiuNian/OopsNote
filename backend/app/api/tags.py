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

router = APIRouter()


@router.get("/tags", response_model=TagsResponse)
def list_tags(
    request: Request,
    dimension: TagDimension | None = None,
    query: str | None = None,
    limit: int = 50,
) -> TagsResponse:
    from ..tags import TagItemView

    q = (query or "").strip()
    lim = max(1, int(limit))

    # Tags now have persistent ref_count stored in TagItem
    # No need to recalculate on every request
    if not q:
        base = tag_store.list(dimension=dimension, limit=5000)
        base.sort(key=lambda t: (-t.ref_count, t.value))
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
                -t.ref_count,
                str(getattr(t, "value", "")),
            )
        )
        items = candidates[:lim]

    return TagsResponse(
        items=[TagItemView(**t.model_dump(mode="json")) for t in items]
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


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: str) -> dict:
    """Delete a tag by ID."""
    success = tag_store.delete(tag_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="标签不存在或已被删除")
    return {"ok": True, "tag_id": tag_id}


@router.put("/tags/{tag_id}", response_model=TagsResponse)
def update_tag(tag_id: str, payload: dict) -> TagsResponse:
    """Update a tag's value by ID."""
    from fastapi import HTTPException
    
    value = payload.get("value", "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="标签内容不能为空")
    
    item = tag_store.update_value(tag_id, value)
    if item is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    
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
