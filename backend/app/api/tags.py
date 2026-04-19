"""标签管理相关 API 端点。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from pydantic import BaseModel

from ..auth.deps import require_admin, require_user
from ..tags import (
    TagCreateRequest,
    TagDimension,
    TagDimensionsResponse,
    TagDimensionsUpdateRequest,
    TagsResponse,
    tag_store,
)

router = APIRouter(dependencies=[Depends(require_user)])


@router.get("/tags", response_model=TagsResponse)
def list_tags(
    dimension: TagDimension | None = None,
    query: str | None = None,
    subject: str | None = None,
    chapter: str | None = None,
    limit: int = 50,
) -> TagsResponse:
    from ..tags import TagItemView

    q = (query or "").strip()
    lim = max(1, int(limit))

    # 标签的引用计数 ref_count 已持久化在 TagItem 中
    # 无需在每次请求时重新计算
    if not q:
        base = tag_store.list(
            dimension=dimension,
            subject=subject,
            chapter=chapter,
            limit=5000,
        )
        base.sort(key=lambda t: (-t.ref_count, t.value))
        items = base[:lim]
    else:
        candidates = tag_store.search(
            dimension=dimension,
            query=q,
            subject=subject,
            chapter=chapter,
            limit=5000,
        )
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

    return TagsResponse(items=[TagItemView(**t.model_dump(mode="json")) for t in items])


@router.post(
    "/tags",
    response_model=TagsResponse,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_tag(payload: TagCreateRequest) -> TagsResponse:
    """创建新标签。"""
    item, _created = tag_store.upsert(
        payload.dimension,
        payload.value,
        aliases=payload.aliases,
        subject=payload.subject,
        chapter=payload.chapter,
    )
    from ..tags import TagItemView

    return TagsResponse(
        items=[TagItemView(**item.model_dump(mode="json"))]
    )


@router.delete("/tags/{tag_id}", dependencies=[Depends(require_admin)])
def delete_tag(tag_id: str) -> dict:
    """按 ID 删除标签。"""
    tag = tag_store.get_by_id(tag_id)
    if tag is not None and tag.source == "builtin":
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="内置标签不可删除")

    success = tag_store.delete(tag_id)
    if not success:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="标签不存在或已被删除")
    return {"ok": True, "tag_id": tag_id}


@router.put(
    "/tags/{tag_id}",
    response_model=TagsResponse,
    dependencies=[Depends(require_admin)],
)
def update_tag(tag_id: str, payload: dict) -> TagsResponse:
    """按 ID 更新标签值。"""
    from fastapi import HTTPException

    value = payload.get("value", "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="标签内容不能为空")

    current = tag_store.get_by_id(tag_id)
    if current is not None and current.source == "builtin":
        raise HTTPException(status_code=400, detail="内置标签不可直接改名")

    item = tag_store.update_value(tag_id, value)
    if item is None:
        raise HTTPException(status_code=404, detail="标签不存在")

    from ..tags import TagItemView

    return TagsResponse(
        items=[TagItemView(**item.model_dump(mode="json"))]
    )


class TagMergeRequest(BaseModel):
    """合并标签请求体。"""
    target_id: str


class TagMergeResponse(BaseModel):
    """标签合并结果响应体。"""
    ok: bool
    tasks_modified: int
    fields_modified: int


@router.post(
    "/tags/{source_id}/merge",
    response_model=TagMergeResponse,
    dependencies=[Depends(require_admin)],
)
def merge_tag(source_id: str, payload: TagMergeRequest) -> TagMergeResponse:
    """将源标签合并到目标标签，并替换所有引用。"""
    from fastapi import HTTPException

    source = tag_store.get_by_id(source_id)
    target = tag_store.get_by_id(payload.target_id)
    if source is not None and source.source == "builtin":
        raise HTTPException(status_code=400, detail="内置标签不可作为合并来源")
    if target is not None and target.source == "builtin":
        raise HTTPException(status_code=400, detail="内置标签不可作为合并目标")

    try:
        stats = tag_store.merge_into(source_id, payload.target_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return TagMergeResponse(
        ok=True,
        tasks_modified=stats["tasks_modified"],
        fields_modified=stats["fields_modified"],
    )


@router.get(
    "/settings/tag-dimensions",
    response_model=TagDimensionsResponse,
    dependencies=[Depends(require_admin)],
)
def get_tag_dimensions() -> TagDimensionsResponse:
    return TagDimensionsResponse(dimensions=tag_store.load_dimensions())


@router.put(
    "/settings/tag-dimensions",
    response_model=TagDimensionsResponse,
    dependencies=[Depends(require_admin)],
)
def update_tag_dimensions(payload: TagDimensionsUpdateRequest) -> TagDimensionsResponse:
    saved = tag_store.save_dimensions(payload.dimensions)
    return TagDimensionsResponse(dimensions=saved)
