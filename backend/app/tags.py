"""Tag models and file-backed tag store."""

# pylint: disable=import-error,too-few-public-methods

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
    """Styling metadata for a tag dimension."""

    label: str
    label_variant: str = Field(
        default="secondary",
        description=(
            "Primer Label variant, e.g. secondary/accent/success/attention/danger/done"
        ),
    )


class TagItem(BaseModel):
    """Stored tag metadata."""

    id: str
    dimension: TagDimension
    value: str
    aliases: List[str] = Field(default_factory=list)
    created_at: datetime
    ref_count: int = Field(
        default=0,
        description="How many times this tag is referenced in tasks/problems",
    )


class TagItemView(TagItem):
    """Tag data with usage count for UI display."""

    ref_count: int = Field(
        default=0,
        description="How many times this tag is referenced in tasks/problems",
    )


class TagCreateRequest(BaseModel):
    """Request payload for creating a tag."""

    dimension: TagDimension
    value: str
    aliases: List[str] = Field(default_factory=list)


class TagsResponse(BaseModel):
    """List response for tags."""

    items: List[TagItemView]


class TagDimensionsResponse(BaseModel):
    """Response payload for tag dimension styles."""

    dimensions: dict[str, TagDimensionStyle]


class TagDimensionsUpdateRequest(BaseModel):
    """Request payload for updating tag dimension styles."""

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
        """Load or initialize tag dimension styles."""
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
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
            # Ensure defaults exist.
            defaults = self._default_dimensions()
            for k, v in defaults.items():
                parsed.setdefault(k, v)
            if parsed != dims:
                self._write_dimensions(parsed)
            return parsed

    def save_dimensions(
        self,
        dimensions: dict[str, TagDimensionStyle],
    ) -> dict[str, TagDimensionStyle]:
        """Persist updated tag dimension styles."""
        with self._lock:
            defaults = self._default_dimensions()
            merged = dict(defaults)
            merged.update({str(k): v for k, v in (dimensions or {}).items()})
            self._write_dimensions(merged)
            return merged

    def list(
        self,
        dimension: TagDimension | None = None,
        limit: int = 2000,
    ) -> List[TagItem]:
        """List tags by dimension with a hard cap."""
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
        """Search tags by value or alias."""
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

        filtered = [
            t
            for t in items
            if q in t.value.casefold()
            or any(q in str(a).casefold() for a in (t.aliases or []))
        ]
        filtered.sort(key=score)
        return filtered[: max(1, int(limit))]

    def ensure(self, dimension: TagDimension, values: Iterable[str]) -> List[TagItem]:
        """Ensure tags exist for the provided values."""
        created: List[TagItem] = []
        for value in values:
            value = (value or "").strip()
            if not value:
                continue
            item, did_create = self.upsert(dimension, value)
            if did_create:
                created.append(item)
        return created

    def upsert(
        self,
        dimension: TagDimension,
        value: str,
        aliases: Optional[List[str]] = None,
    ) -> tuple[TagItem, bool]:
        """Create or update a tag entry and return (tag, created)."""
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
                            state.items = [
                                updated if t.id == item.id else t for t in state.items
                            ]
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

    def delete(self, tag_id: str) -> bool:
        """Delete a tag by ID. Returns True if deleted, False if not found."""
        with self._lock:
            state = self._load_state_unlocked()
            original_count = len(state.items)
            state.items = [t for t in state.items if t.id != tag_id]
            if len(state.items) < original_count:
                self._write_state_unlocked(state)
                return True
            return False

    def update_value(self, tag_id: str, new_value: str) -> TagItem | None:
        """Update a tag's value by ID. Returns the updated tag or None if not found."""
        new_value = (new_value or "").strip()
        if not new_value:
            return None
        
        with self._lock:
            state = self._load_state_unlocked()
            for item in state.items:
                if item.id == tag_id:
                    # Check if the new value already exists for this dimension
                    key = self._key(item.dimension, new_value)
                    for existing in state.items:
                        if self._key(existing.dimension, existing.value) == key and existing.id != tag_id:
                            raise ValueError(f"标签 '{new_value}' 已存在于该维度")
                    
                    # Update the value
                    updated = item.model_copy(update={"value": new_value})
                    state.items = [
                        updated if t.id == tag_id else t for t in state.items
                    ]
                    self._write_state_unlocked(state)
                    return updated
            return None

    def update_ref_count(self, tag_id: str, delta: int) -> bool:
        """Update a tag's reference count by delta. Returns True if updated, False if not found."""
        with self._lock:
            state = self._load_state_unlocked()
            for item in state.items:
                if item.id == tag_id:
                    new_count = item.ref_count + delta
                    if new_count < 0:
                        # Prevent negative counts, but log a warning
                        logger = __import__("logging").getLogger(__name__)
                        logger.warning(
                            f"Tag {tag_id} would have negative ref_count: {item.ref_count} + {delta}"
                        )
                        new_count = 0
                    updated = item.model_copy(update={"ref_count": new_count})
                    state.items = [
                        updated if t.id == tag_id else t for t in state.items
                    ]
                    self._write_state_unlocked(state)
                    return True
            return False

    def update_ref_count_by_value(
        self,
        dimension: TagDimension,
        value: str,
        delta: int,
    ) -> bool:
        """Update a tag's reference count by dimension and value. Returns True if updated."""
        value = (value or "").strip()
        if not value:
            return False
        key = self._key(dimension, value)
        with self._lock:
            state = self._load_state_unlocked()
            for item in state.items:
                if self._key(item.dimension, item.value) == key:
                    new_count = item.ref_count + delta
                    if new_count < 0:
                        logger = __import__("logging").getLogger(__name__)
                        logger.warning(
                            f"Tag {dimension.value}::{value} would have negative ref_count: {item.ref_count} + {delta}"
                        )
                        new_count = 0
                    updated = item.model_copy(update={"ref_count": new_count})
                    state.items = [
                        updated if t.id == item.id else t for t in state.items
                    ]
                    self._write_state_unlocked(state)
                    return True
            return False

    def recalculate_all_counts(self) -> dict[str, int]:
        """Recalculate all tag reference counts from tasks. Returns stats."""
        from pathlib import Path
        from app.repository import FileTaskRepository

        # Load all tasks from storage
        base_dir = Path(__file__).resolve().parents[1] / "storage" / "tasks"
        if not base_dir.exists():
            return {"total_tags": 0, "non_zero_counts": 0}
        
        repo = FileTaskRepository(base_dir=base_dir)
        all_tasks = list(repo.list_all().values())
        logger = __import__("logging").getLogger(__name__)

        # Build a map of tag key -> set of problem_ids (to avoid double-counting)
        from app.tags import TagDimension
        
        tag_to_problems: dict[str, set[str]] = {}
        
        def _add_tag(dimension: TagDimension, value: str, problem_id: str) -> None:
            value = (value or "").strip()
            if not value or not problem_id:
                return
            key = self._key(dimension, value)
            if key not in tag_to_problems:
                tag_to_problems[key] = set()
            tag_to_problems[key].add(problem_id)

        for task in all_tasks:
            task_id = task.id
            
            # Count tags from task.payload (manual tags) - these apply to ALL problems in the task
            payload = getattr(task, "payload", None)
            all_problem_ids = [p.problem_id for p in getattr(task, "problems", []) or []]
            
            if payload and all_problem_ids:
                for val in getattr(payload, "knowledge_tags", []) or []:
                    for pid in all_problem_ids:
                        _add_tag(TagDimension.KNOWLEDGE, val, pid)
                for val in getattr(payload, "error_tags", []) or []:
                    for pid in all_problem_ids:
                        _add_tag(TagDimension.ERROR, val, pid)
                for val in getattr(payload, "user_tags", []) or []:
                    for pid in all_problem_ids:
                        _add_tag(TagDimension.CUSTOM, val, pid)
                source_val = getattr(payload, "source", None)
                if source_val:
                    for pid in all_problem_ids:
                        _add_tag(TagDimension.META, source_val, pid)
            
            # Count tags from problems (manual tags on individual problems)
            for problem in getattr(task, "problems", []) or []:
                for val in getattr(problem, "knowledge_tags", []) or []:
                    _add_tag(TagDimension.KNOWLEDGE, val, problem.problem_id)
                for val in getattr(problem, "error_tags", []) or []:
                    _add_tag(TagDimension.ERROR, val, problem.problem_id)
                for val in getattr(problem, "user_tags", []) or []:
                    _add_tag(TagDimension.CUSTOM, val, problem.problem_id)
                source_val = getattr(problem, "source", None)
                if source_val:
                    _add_tag(TagDimension.META, source_val, problem.problem_id)
            
            # Count tags from tagging results (AI-generated tags) - one per problem
            for tag_result in getattr(task, "tags", []) or []:
                problem_id = getattr(tag_result, "problem_id", None)
                if not problem_id:
                    continue
                for val in getattr(tag_result, "knowledge_points", []) or []:
                    _add_tag(TagDimension.KNOWLEDGE, val, problem_id)
        
        # Update all tags with new counts (count = number of unique problems)
        with self._lock:
            state = self._load_state_unlocked()
            for item in state.items:
                key = self._key(item.dimension, item.value)
                item.ref_count = len(tag_to_problems.get(key, set()))
            self._write_state_unlocked(state)
            
            stats = {"total_tags": len(state.items), "non_zero_counts": 0}
            for item in state.items:
                if item.ref_count > 0:
                    stats["non_zero_counts"] += 1
            return stats

    @staticmethod
    def _key(dimension: TagDimension, value: str) -> str:
        return f"{dimension.value}::{value.casefold().strip()}"

    @staticmethod
    def _default_dimensions() -> dict[str, TagDimensionStyle]:
        return {
            TagDimension.KNOWLEDGE.value: TagDimensionStyle(
                label="知识体系",
                label_variant="accent",
            ),
            TagDimension.ERROR.value: TagDimensionStyle(
                label="错题归因",
                label_variant="danger",
            ),
            TagDimension.META.value: TagDimensionStyle(
                label="题目属性",
                label_variant="success",
            ),
            TagDimension.CUSTOM.value: TagDimensionStyle(
                label="自定义",
                label_variant="secondary",
            ),
        }

    def _write_dimensions(self, dimensions: dict[str, TagDimensionStyle]) -> None:
        payload = {
            "dimensions": {k: v.model_dump(mode="json") for k, v in dimensions.items()}
        }
        self.dims_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
        for item in items or []:
            try:
                parsed.append(TagItem.model_validate(item))
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        return _TagState(items=parsed)

    def _write_state_unlocked(self, state: _TagState) -> None:
        payload = {"items": [item.model_dump(mode="json") for item in state.items]}
        tmp = self.tags_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.tags_path)


# Default singleton used by the API and the agent prompt context.
tag_store = TagStore()
