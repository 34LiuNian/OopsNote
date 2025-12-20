from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class TagDimension(str, Enum):
    KNOWLEDGE = "knowledge"
    ERROR = "error"
    META = "meta"
    CUSTOM = "custom"


class TagDimensionStyle(BaseModel):
    label: str
    label_variant: str = Field(
        default="secondary",
        description="Primer Label variant, e.g. secondary/accent/success/attention/danger/done",
    )


class TagItem(BaseModel):
    id: str
    dimension: TagDimension
    value: str
    aliases: List[str] = Field(default_factory=list)
    created_at: datetime


class TagItemView(TagItem):
    ref_count: int = Field(default=0, description="How many times this tag is referenced in tasks/problems")


class TagCreateRequest(BaseModel):
    dimension: TagDimension
    value: str
    aliases: List[str] = Field(default_factory=list)


class TagsResponse(BaseModel):
    items: List[TagItemView]


class TagDimensionsResponse(BaseModel):
    dimensions: dict[str, TagDimensionStyle]


class TagDimensionsUpdateRequest(BaseModel):
    dimensions: dict[str, TagDimensionStyle]


@dataclass
class _TagState:
    items: List[TagItem]


class TagStore:
    """File-backed tag registry.

    This is intentionally lightweight: enough for UI-driven tag picking and
    prompting agents with existing tags.
    """

    def __init__(
        self,
        tags_path: Path | None = None,
        dims_path: Path | None = None,
    ) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.tags_path = tags_path or (base / "tags.json")
        self.dims_path = dims_path or (base / "tag_dimensions.json")
        self._lock = threading.Lock()

    def load_dimensions(self) -> dict[str, TagDimensionStyle]:
        with self._lock:
            if not self.dims_path.exists():
                styles = self._default_dimensions()
                self._write_dimensions(styles)
                return styles
            raw = json.loads(self.dims_path.read_text(encoding="utf-8"))
            dims = raw.get("dimensions", {}) if isinstance(raw, dict) else {}
            parsed: dict[str, TagDimensionStyle] = {}
            for key, value in (dims or {}).items():
                try:
                    parsed[str(key)] = TagDimensionStyle.model_validate(value)
                except Exception:
                    continue
            # Ensure defaults exist.
            defaults = self._default_dimensions()
            for k, v in defaults.items():
                parsed.setdefault(k, v)
            if parsed != dims:
                self._write_dimensions(parsed)
            return parsed

    def save_dimensions(self, dimensions: dict[str, TagDimensionStyle]) -> dict[str, TagDimensionStyle]:
        with self._lock:
            defaults = self._default_dimensions()
            merged = dict(defaults)
            merged.update({str(k): v for k, v in (dimensions or {}).items()})
            self._write_dimensions(merged)
            return merged

    def list(self, dimension: TagDimension | None = None, limit: int = 2000) -> List[TagItem]:
        state = self._load_state()
        items = state.items
        if dimension is not None:
            items = [t for t in items if t.dimension == dimension]
        items.sort(key=lambda t: t.value)
        return items[: max(1, int(limit))]

    def search(
        self,
        dimension: TagDimension | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> List[TagItem]:
        query = (query or "").strip()
        if not query:
            return self.list(dimension=dimension, limit=limit)

        q = query.casefold()
        items = self._load_state().items
        if dimension is not None:
            items = [t for t in items if t.dimension == dimension]

        def score(item: TagItem) -> tuple[int, int, str]:
            value = item.value.casefold()
            alias_hit = any(q in str(a).casefold() for a in (item.aliases or []))
            if value.startswith(q):
                return (0, 0, item.value)
            if q in value:
                return (1, 0, item.value)
            if alias_hit:
                return (2, 0, item.value)
            return (3, 0, item.value)

        filtered = [t for t in items if q in t.value.casefold() or any(q in str(a).casefold() for a in (t.aliases or []))]
        filtered.sort(key=score)
        return filtered[: max(1, int(limit))]

    def ensure(self, dimension: TagDimension, values: Iterable[str]) -> List[TagItem]:
        created: List[TagItem] = []
        for value in values:
            value = (value or "").strip()
            if not value:
                continue
            item, did_create = self.upsert(dimension, value)
            if did_create:
                created.append(item)
        return created

    def upsert(self, dimension: TagDimension, value: str, aliases: Optional[List[str]] = None) -> tuple[TagItem, bool]:
        value = (value or "").strip()
        if not value:
            raise ValueError("tag value is required")
        aliases = [str(a).strip() for a in (aliases or []) if str(a).strip()]

        with self._lock:
            state = self._load_state_unlocked()
            key = self._key(dimension, value)
            for item in state.items:
                if self._key(item.dimension, item.value) == key:
                    # Merge aliases best-effort.
                    if aliases:
                        merged = list(dict.fromkeys([*(item.aliases or []), *aliases]))
                        if merged != (item.aliases or []):
                            updated = item.model_copy(update={"aliases": merged})
                            state.items = [updated if t.id == item.id else t for t in state.items]
                            self._write_state_unlocked(state)
                            return updated, False
                    return item, False

            now = datetime.now(timezone.utc)
            created = TagItem(
                id=uuid4().hex,
                dimension=dimension,
                value=value,
                aliases=aliases,
                created_at=now,
            )
            state.items.append(created)
            self._write_state_unlocked(state)
            return created, True

    @staticmethod
    def _key(dimension: TagDimension, value: str) -> str:
        return f"{dimension.value}::{value.casefold().strip()}"

    @staticmethod
    def _default_dimensions() -> dict[str, TagDimensionStyle]:
        return {
            TagDimension.KNOWLEDGE.value: TagDimensionStyle(label="知识体系", label_variant="accent"),
            TagDimension.ERROR.value: TagDimensionStyle(label="错题归因", label_variant="danger"),
            TagDimension.META.value: TagDimensionStyle(label="题目属性", label_variant="success"),
            TagDimension.CUSTOM.value: TagDimensionStyle(label="自定义", label_variant="secondary"),
        }

    def _write_dimensions(self, dimensions: dict[str, TagDimensionStyle]) -> None:
        payload = {"dimensions": {k: v.model_dump(mode="json") for k, v in dimensions.items()}}
        self.dims_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_state(self) -> _TagState:
        with self._lock:
            return self._load_state_unlocked()

    def _load_state_unlocked(self) -> _TagState:
        if not self.tags_path.exists():
            state = _TagState(items=[])
            self._write_state_unlocked(state)
            return state
        raw = json.loads(self.tags_path.read_text(encoding="utf-8"))
        items = raw.get("items", []) if isinstance(raw, dict) else []
        parsed: List[TagItem] = []
        for item in (items or []):
            try:
                parsed.append(TagItem.model_validate(item))
            except Exception:
                continue
        return _TagState(items=parsed)

    def _write_state_unlocked(self, state: _TagState) -> None:
        payload = {"items": [item.model_dump(mode="json") for item in state.items]}
        tmp = self.tags_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.tags_path)


# Default singleton used by the API and the agent prompt context.
tag_store = TagStore()
