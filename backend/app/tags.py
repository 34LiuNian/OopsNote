"""Tag models and file-backed tag store."""

# pylint: disable=import-error,too-few-public-methods

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Literal, Optional
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, Field

from .config.subjects import SUBJECTS
from .default_tags_seed import load_builtin_tags


_SUBJECT_LABEL_TO_KEY = {label: key for key, label in SUBJECTS.items()}


class TagDimension(str, Enum):
    """Tag dimension enumeration and utilities."""

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
    dimension: TagDimension = Field(default=TagDimension.KNOWLEDGE)
    value: str
    aliases: List[str] = Field(default_factory=list)
    subject: str | None = Field(default=None)
    chapter: str | None = Field(default=None)
    ref_count: int = Field(
        default=0,
        description="How many times this tag is referenced in tasks/problems",
    )
    source: Literal["builtin", "user"] = Field(default="user")


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
    subject: str | None = Field(default=None)
    chapter: str | None = Field(default=None)


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
        builtin_path: Path | None = None,
    ) -> None:
        base = Path(__file__).resolve().parent.parent / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.user_tags_path = tags_path or (base / "tags_user.json")
        self.builtin_tags_path = builtin_path or (base / "tags_builtin.json")
        self.legacy_tags_path = base / "tags.json"
        self.dims_path = dims_path or (base / "tag_dimensions.json")
        self.conflicts_path = base / "tag_conflicts.json"
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
        subject: str | None = None,
        chapter: str | None = None,
        limit: int = 2000,
    ) -> List[TagItem]:
        """List tags by dimension with a hard cap."""
        state = self._load_state()
        items = state.items
        if dimension is not None:
            items = [t for t in items if t.dimension == dimension]
        if subject or chapter:
            subject_norm = self._norm(subject)
            chapter_norm = self._norm(chapter)
            items = [
                t
                for t in items
                if t.dimension == TagDimension.KNOWLEDGE
                and (not subject_norm or self._norm(t.subject) == subject_norm)
                and (not chapter_norm or self._norm(t.chapter) == chapter_norm)
            ]
        items.sort(key=lambda t: t.value)
        return items[: max(1, int(limit))]

    def search(
        self,
        dimension: TagDimension | None = None,
        query: str | None = None,
        subject: str | None = None,
        chapter: str | None = None,
        limit: int = 50,
    ) -> List[TagItem]:
        """Search tags by value or alias."""
        query = (query or "").strip()
        if not query:
            return self.list(
                dimension=dimension,
                subject=subject,
                chapter=chapter,
                limit=limit,
            )

        q = query.casefold()
        items = self._load_state().items
        if dimension is not None:
            items = [t for t in items if t.dimension == dimension]
        if subject or chapter:
            subject_norm = self._norm(subject)
            chapter_norm = self._norm(chapter)
            items = [
                t
                for t in items
                if t.dimension == TagDimension.KNOWLEDGE
                and (not subject_norm or self._norm(t.subject) == subject_norm)
                and (not chapter_norm or self._norm(t.chapter) == chapter_norm)
            ]

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
        *,
        subject: str | None = None,
        chapter: str | None = None,
    ) -> tuple[TagItem, bool]:
        """Create or update a tag entry and return (tag, created)."""
        value = (value or "").strip()
        if not value:
            raise ValueError("tag value is required")
        aliases = [str(a).strip() for a in (aliases or []) if str(a).strip()]
        knowledge_fields = self._build_knowledge_fields(
            value,
            aliases,
            subject=subject,
            chapter=chapter,
        ) if dimension == TagDimension.KNOWLEDGE else {}

        with self._lock:
            state = self._load_state_unlocked()
            user_state = self._load_user_state_unlocked()
            key = self._key(dimension, value)
            for item in state.items:
                if self._key(item.dimension, item.value) == key:
                    if item.source == "builtin":
                        return item, False
                    merged = list(dict.fromkeys([*(item.aliases or []), *aliases]))
                    updates: dict[str, object] = {}
                    if merged != (item.aliases or []):
                        updates["aliases"] = merged
                    if knowledge_fields:
                        for field_name, field_value in knowledge_fields.items():
                            current_value = getattr(item, field_name, None)
                            if current_value != field_value:
                                updates[field_name] = field_value
                    if updates:
                        updated = item.model_copy(update=updates)
                        user_state.items = [
                            updated if t.id == item.id else t for t in user_state.items
                        ]
                        self._write_user_state_unlocked(user_state)
                        return updated, False
                    return item, False

            created = TagItem(
                id=uuid4().hex,
                dimension=dimension,
                value=value,
                aliases=aliases,
                **knowledge_fields,
                source="user",
            )
            user_state.items.append(created)
            self._write_user_state_unlocked(user_state)
            return created, True

    def delete(self, tag_id: str) -> bool:
        """Delete a tag by ID. Returns True if deleted, False if not found."""
        with self._lock:
            user_state = self._load_user_state_unlocked()
            original_count = len(user_state.items)
            user_state.items = [t for t in user_state.items if t.id != tag_id]
            if len(user_state.items) < original_count:
                self._write_user_state_unlocked(user_state)
                return True
            return False

    def update_value(self, tag_id: str, new_value: str) -> TagItem | None:
        """Update a tag's value by ID. Returns the updated tag or None if not found."""
        new_value = (new_value or "").strip()
        if not new_value:
            return None

        with self._lock:
            state = self._load_state_unlocked()
            user_state = self._load_user_state_unlocked()
            for item in user_state.items:
                if item.id == tag_id:
                    # Check if the new value already exists for this dimension
                    key = self._key(item.dimension, new_value)
                    for existing in state.items:
                        if (
                            self._key(existing.dimension, existing.value) == key
                            and existing.id != tag_id
                        ):
                            raise ValueError(f"标签 '{new_value}' 已存在于该维度")

                    # Update the value
                    updated = item.model_copy(update={"value": new_value})
                    user_state.items = [
                        updated if t.id == tag_id else t for t in user_state.items
                    ]
                    self._write_user_state_unlocked(user_state)
                    return updated
            return None

    def update_ref_count(self, tag_id: str, delta: int) -> bool:
        """Update a tag's reference count by delta. Returns True if updated, False if not found."""
        with self._lock:
            user_state = self._load_user_state_unlocked()
            for item in user_state.items:
                if item.id == tag_id:
                    new_count = item.ref_count + delta
                    if new_count < 0:
                        # Prevent negative counts, but log a warning
                        logger = __import__("logging").getLogger(__name__)
                        logger.warning(f"Tag {tag_id} would have negative ref_count: {item.ref_count} + {delta}")
                        new_count = 0
                    updated = item.model_copy(update={"ref_count": new_count})
                    user_state.items = [
                        updated if t.id == tag_id else t for t in user_state.items
                    ]
                    self._write_user_state_unlocked(user_state)
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
            user_state = self._load_user_state_unlocked()
            for item in user_state.items:
                if self._key(item.dimension, item.value) == key:
                    new_count = item.ref_count + delta
                    if new_count < 0:
                        logger = __import__("logging").getLogger(__name__)
                        logger.warning(
                            "Tag %s::%s would have negative ref_count: %s + %s",
                            dimension.value,
                            value,
                            item.ref_count,
                            delta,
                        )
                        new_count = 0
                    updated = item.model_copy(update={"ref_count": new_count})
                    user_state.items = [
                        updated if t.id == item.id else t for t in user_state.items
                    ]
                    self._write_user_state_unlocked(user_state)
                    return True
            return False

    def get_by_id(self, tag_id: str) -> TagItem | None:
        """Return a single tag by ID or None."""
        state = self._load_state()
        for item in state.items:
            if item.id == tag_id:
                return item
        return None

    def merge_into(self, source_id: str, target_id: str) -> dict:
        """Merge *source* tag into *target* tag.

        1. Replace all occurrences of source.value with target.value in every
           task file (payload, problems, tagging results).
        2. Add source.value + source.aliases as aliases on target.
        3. Delete source tag.
        4. Recalculate ref_count for target.

        Returns a stats dict: ``{tasks_modified, fields_modified}``.
        """
        import logging

        log = logging.getLogger(__name__)

        source = self.get_by_id(source_id)
        target = self.get_by_id(target_id)
        if source is None:
            raise ValueError("源标签不存在")
        if target is None:
            raise ValueError("目标标签不存在")
        if source.id == target.id:
            raise ValueError("不能合并到自身")
        if source.dimension != target.dimension:
            raise ValueError("只能合并同一维度的标签")

        old_val = source.value
        new_val = target.value
        dim = source.dimension

        # ── 1. Rewrite all task files ────────────────────────────
        tasks_dir = Path(__file__).resolve().parents[1] / "storage" / "tasks"
        tasks_modified = 0
        fields_modified = 0

        def _replace_in_list(lst: list | None) -> tuple[list | None, int]:
            """Replace old_val with new_val in a string list, dedup."""
            if not lst or not isinstance(lst, list):
                return lst, 0
            c = 0
            result: list[str] = []
            for v in lst:
                if isinstance(v, str) and v.strip().casefold() == old_val.casefold():
                    if new_val not in result:
                        result.append(new_val)
                    c += 1
                else:
                    if v not in result:
                        result.append(v)
            return result, c

        def _field_names() -> list[str]:
            if dim == TagDimension.KNOWLEDGE:
                return ["knowledge_tags"]
            elif dim == TagDimension.ERROR:
                return ["error_tags"]
            elif dim == TagDimension.CUSTOM:
                return ["user_tags"]
            return []

        def _tagging_field_names() -> list[str]:
            if dim == TagDimension.KNOWLEDGE:
                return ["knowledge_points"]
            elif dim == TagDimension.ERROR:
                return ["error_hypothesis"]
            return []

        if tasks_dir.exists():
            fnames = _field_names()
            tfnames = _tagging_field_names()

            for path in sorted(tasks_dir.glob("*.json")):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                count = 0

                # payload level
                payload = raw.get("payload")
                if isinstance(payload, dict):
                    for fn in fnames:
                        if fn in payload:
                            payload[fn], c = _replace_in_list(payload[fn])
                            count += c
                    if dim == TagDimension.META:
                        src = payload.get("source")
                        if isinstance(src, str) and src.strip().casefold() == old_val.casefold():
                            payload["source"] = new_val
                            count += 1

                # problems level
                for prob in raw.get("problems", []) or []:
                    if not isinstance(prob, dict):
                        continue
                    for fn in fnames:
                        if fn in prob:
                            prob[fn], c = _replace_in_list(prob[fn])
                            count += c
                    if dim == TagDimension.META:
                        src = prob.get("source")
                        if isinstance(src, str) and src.strip().casefold() == old_val.casefold():
                            prob["source"] = new_val
                            count += 1

                # tagging results level
                for tag_result in raw.get("tags", []) or []:
                    if not isinstance(tag_result, dict):
                        continue
                    for fn in tfnames:
                        if fn in tag_result:
                            tag_result[fn], c = _replace_in_list(tag_result[fn])
                            count += c

                if count > 0:
                    tasks_modified += 1
                    fields_modified += count
                    tmp = path.with_suffix(".json.tmp")
                    tmp.write_text(
                        json.dumps(raw, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    tmp.replace(path)

        log.info(
            "Tag merge %s -> %s: tasks_modified=%d, fields_modified=%d",
            old_val, new_val, tasks_modified, fields_modified,
        )

        # ── 2. Transfer aliases and delete source ─────────────────
        merged_aliases = list(
            dict.fromkeys(
                [*(target.aliases or []), old_val, *(source.aliases or [])]
            )
        )
        merged_aliases = [a for a in merged_aliases if a.casefold() != new_val.casefold()]

        with self._lock:
            user_state = self._load_user_state_unlocked()
            user_state.items = [
                t.model_copy(update={"aliases": merged_aliases})
                if t.id == target_id
                else t
                for t in user_state.items
            ]
            user_state.items = [t for t in user_state.items if t.id != source_id]
            self._write_user_state_unlocked(user_state)

        # ── 3. Recalculate ref_count ──────────────────────────────
        self.recalculate_all_counts()

        return {
            "tasks_modified": tasks_modified,
            "fields_modified": fields_modified,
        }

    def recalculate_all_counts(self) -> dict[str, int]:
        """Recalculate all tag reference counts from tasks. Returns stats."""
        from app.repository import FileTaskRepository

        # Load all tasks from storage
        base_dir = Path(__file__).resolve().parents[1] / "storage" / "tasks"
        if not base_dir.exists():
            return {"total_tags": 0, "non_zero_counts": 0}

        repo = FileTaskRepository(base_dir=base_dir)
        all_tasks = list(repo.list_all().values())

        # Build a map of tag key -> set of problem_ids (to avoid
        # double-counting)
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
            # Count tags from task.payload (manual tags) - these apply to ALL
            # problems in the task
            payload = getattr(task, "payload", None)
            all_problem_ids = [
                p.problem_id for p in getattr(task, "problems", []) or []
            ]

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

            # Count tags from tagging results (AI-generated tags) - one per
            # problem
            for tag_result in getattr(task, "tags", []) or []:
                problem_id = getattr(tag_result, "problem_id", None)
                if not problem_id:
                    continue
                for val in getattr(tag_result, "knowledge_points", []) or []:
                    _add_tag(TagDimension.KNOWLEDGE, val, problem_id)

        # Update all tags with new counts (count = number of unique problems)
        with self._lock:
            user_state = self._load_user_state_unlocked()
            builtin_state = self._load_builtin_state_unlocked()

            user_updated: List[TagItem] = []
            for item in user_state.items:
                key = self._key(item.dimension, item.value)
                ref_count = len(tag_to_problems.get(key, set()))
                user_updated.append(item.model_copy(update={"ref_count": ref_count}))

            builtin_updated: List[TagItem] = []
            for item in builtin_state.items:
                key = self._key(item.dimension, item.value)
                ref_count = len(tag_to_problems.get(key, set()))
                builtin_updated.append(item.model_copy(update={"ref_count": ref_count}))

            self._write_user_state_unlocked(_TagState(items=user_updated))
            self._write_builtin_state_unlocked(_TagState(items=builtin_updated))

            visible_items = self._compose_state_unlocked(
                _TagState(items=user_updated),
                _TagState(items=builtin_updated),
            ).items
            stats = {"total_tags": len(visible_items), "non_zero_counts": 0}
            for item in visible_items:
                if item.ref_count > 0:
                    stats["non_zero_counts"] += 1
            return stats

    @staticmethod
    def _key(dimension: TagDimension, value: str) -> str:
        return f"{dimension.value}::{value.casefold().strip()}"

    @staticmethod
    def _norm(value: str | None) -> str:
        return str(value or "").strip().casefold()

    @staticmethod
    def _clean_path(path: str | None) -> str:
        parts = [str(part).strip() for part in str(path or "").split("/") if str(part).strip()]
        return "/".join(parts)

    @staticmethod
    def _legacy_builtin_id(dimension: TagDimension, value: str) -> str:
        return uuid5(NAMESPACE_URL, f"oopsnote:{dimension.value}:{value}").hex

    def _looks_like_legacy_builtin(self, item: TagItem) -> bool:
        if item.dimension != TagDimension.KNOWLEDGE:
            return False
        expected_id = self._legacy_builtin_id(item.dimension, item.value)
        return item.id == expected_id

    def _infer_knowledge_from_aliases(
        self,
        aliases: Iterable[str],
    ) -> tuple[str | None, str | None]:
        for alias in aliases:
            cleaned = self._clean_path(alias)
            if not cleaned:
                continue
            parts = cleaned.split("/")
            if not parts:
                continue
            subject_key = _SUBJECT_LABEL_TO_KEY.get(parts[0])
            if not subject_key:
                continue
            chapter = parts[1] if len(parts) >= 3 else None
            return subject_key, chapter
        return None, None

    def _build_knowledge_fields(
        self,
        value: str,
        aliases: Iterable[str],
        *,
        subject: str | None,
        chapter: str | None,
    ) -> dict[str, object]:
        subject_key = str(subject or "").strip() or None
        if subject_key not in SUBJECTS:
            subject_key = None
        chapter_text = str(chapter or "").strip() or None

        inferred_subject, inferred_chapter = self._infer_knowledge_from_aliases(aliases)
        subject_key = subject_key or inferred_subject
        chapter_text = chapter_text or inferred_chapter

        if subject_key and not chapter_text:
            subject_label = SUBJECTS[subject_key]
            value_text = str(value).strip()
            for alias in aliases:
                cleaned = self._clean_path(alias)
                if not cleaned.startswith(f"{subject_label}/"):
                    continue
                parts = [part for part in cleaned.split("/") if part]
                if len(parts) < 3:
                    continue
                if parts[-1] != value_text:
                    continue
                chapter_text = parts[-2]
                break

        return {
            "subject": subject_key,
            "chapter": chapter_text,
        }

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
        self._migrate_legacy_tags_unlocked()
        user_state = self._load_user_state_unlocked()
        builtin_state = self._load_builtin_state_unlocked()
        builtin_state = self._merge_builtin_defaults_unlocked(builtin_state)
        conflicts = self._collect_conflicts_unlocked(user_state, builtin_state)
        self._write_conflicts_unlocked(conflicts)
        return self._compose_state_unlocked(user_state, builtin_state)

    def _migrate_legacy_tags_unlocked(self) -> None:
        if self.user_tags_path.exists() or self.builtin_tags_path.exists():
            return
        if not self.legacy_tags_path.exists():
            return

        raw = json.loads(self.legacy_tags_path.read_text(encoding="utf-8"))
        items = raw.get("items", []) if isinstance(raw, dict) else []

        user_items: list[TagItem] = []
        builtin_items: list[TagItem] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                parsed = TagItem.model_validate(item)
            except Exception:  # pylint: disable=broad-exception-caught
                continue

            raw_source = str(item.get("source") or "").strip()
            is_builtin = raw_source == "builtin" or (
                not raw_source and self._looks_like_legacy_builtin(parsed)
            )
            if is_builtin:
                builtin_items.append(
                    parsed.model_copy(
                        update={
                            "source": "builtin",
                        }
                    )
                )
            else:
                user_items.append(
                    parsed.model_copy(update={"source": "user"})
                )

        self._write_user_state_unlocked(_TagState(items=user_items))
        if builtin_items:
            self._write_builtin_state_unlocked(_TagState(items=builtin_items))

    def _load_user_state_unlocked(self) -> _TagState:
        if not self.user_tags_path.exists():
            state = _TagState(items=[])
            self._write_user_state_unlocked(state)
            return state

        state, changed = self._read_state_file_unlocked(
            self.user_tags_path,
            expected_source="user",
        )
        if changed:
            self._write_user_state_unlocked(state)
        return state

    def _load_builtin_state_unlocked(self) -> _TagState:
        if not self.builtin_tags_path.exists():
            seeded = self._seed_builtin_state_from_bundle_unlocked()
            self._write_builtin_state_unlocked(seeded)
            return seeded

        state, changed = self._read_state_file_unlocked(
            self.builtin_tags_path,
            expected_source="builtin",
        )
        if changed:
            self._write_builtin_state_unlocked(state)
        return state

    def _seed_builtin_state_from_bundle_unlocked(self) -> _TagState:
        items: list[TagItem] = []
        for record in load_builtin_tags():
            payload = record.as_dict()
            payload["source"] = "builtin"
            if str(payload.get("dimension") or "").strip() != "knowledge":
                continue
            try:
                item = TagItem.model_validate(payload)
            except Exception:  # pylint: disable=broad-exception-caught
                continue
            items.append(item)
        return _TagState(items=items)

    def _read_state_file_unlocked(
        self,
        path: Path,
        *,
        expected_source: Literal["builtin", "user"],
    ) -> tuple[_TagState, bool]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = raw.get("items", []) if isinstance(raw, dict) else []
        parsed: list[TagItem] = []
        normalized_changed = False

        for item in items or []:
            if not isinstance(item, dict):
                continue
            try:
                current = TagItem.model_validate(item)
            except Exception:  # pylint: disable=broad-exception-caught
                normalized_changed = True
                continue

            updates: dict[str, object] = {}
            if expected_source == "builtin":
                if current.source != "builtin":
                    updates["source"] = "builtin"
            else:
                if current.source != "user":
                    updates["source"] = "user"

            if current.dimension == TagDimension.KNOWLEDGE:
                fields = self._build_knowledge_fields(
                    current.value,
                    current.aliases or [],
                    subject=current.subject,
                    chapter=current.chapter,
                )
                for field_name, field_value in fields.items():
                    if getattr(current, field_name, None) != field_value:
                        updates[field_name] = field_value

            if updates:
                current = current.model_copy(update=updates)
                normalized_changed = True
            parsed.append(current)

        return _TagState(items=parsed), normalized_changed

    def _merge_builtin_defaults_unlocked(self, builtin_state: _TagState) -> _TagState:
        changed = False
        index_by_key = {
            self._key(item.dimension, item.value): idx
            for idx, item in enumerate(builtin_state.items)
        }

        for record in load_builtin_tags():
            payload = record.as_dict()
            dimension = TagDimension(str(payload["dimension"]))
            key = self._key(dimension, str(payload["value"]))
            aliases = [str(a).strip() for a in (payload.get("aliases") or []) if str(a).strip()]
            knowledge_updates = self._build_knowledge_fields(
                str(payload.get("value") or ""),
                aliases,
                subject=str(payload.get("subject") or "").strip() or None,
                chapter=str(payload.get("chapter") or "").strip() or None,
            ) if dimension == TagDimension.KNOWLEDGE else {}

            existing_index = index_by_key.get(key)
            if existing_index is not None:
                existing = builtin_state.items[existing_index]
                merged_aliases = list(
                    dict.fromkeys([*(existing.aliases or []), *aliases])
                )
                updates: dict[str, object] = {}
                if merged_aliases != (existing.aliases or []):
                    updates["aliases"] = merged_aliases
                for field_name, field_value in knowledge_updates.items():
                    if field_value and getattr(existing, field_name, None) != field_value:
                        updates[field_name] = field_value
                if existing.source != "builtin":
                    updates["source"] = "builtin"
                if updates:
                    builtin_state.items[existing_index] = existing.model_copy(update=updates)
                    changed = True
                continue

            if knowledge_updates:
                payload = {**payload, **knowledge_updates}
            payload["source"] = "builtin"
            builtin_state.items.append(TagItem.model_validate(payload))
            index_by_key[key] = len(builtin_state.items) - 1
            changed = True

        if changed:
            self._write_builtin_state_unlocked(builtin_state)
        return builtin_state

    def _compose_state_unlocked(
        self,
        user_state: _TagState,
        builtin_state: _TagState,
    ) -> _TagState:
        merged: dict[str, TagItem] = {}
        for item in builtin_state.items:
            merged[self._key(item.dimension, item.value)] = item
        for item in user_state.items:
            merged[self._key(item.dimension, item.value)] = item
        return _TagState(items=list(merged.values()))

    def _collect_conflicts_unlocked(
        self,
        user_state: _TagState,
        builtin_state: _TagState,
    ) -> list[dict[str, object]]:
        builtin_by_key = {
            self._key(item.dimension, item.value): item
            for item in builtin_state.items
        }
        conflicts: list[dict[str, object]] = []
        for user_item in user_state.items:
            key = self._key(user_item.dimension, user_item.value)
            builtin_item = builtin_by_key.get(key)
            if builtin_item is None:
                continue

            diff: dict[str, dict[str, object | None]] = {}
            for field_name in ("subject", "chapter"):
                user_value = getattr(user_item, field_name, None)
                builtin_value = getattr(builtin_item, field_name, None)
                if user_value and builtin_value and user_value != builtin_value:
                    diff[field_name] = {
                        "user": user_value,
                        "builtin": builtin_value,
                    }

            user_aliases = list(dict.fromkeys([str(x).strip() for x in (user_item.aliases or []) if str(x).strip()]))
            builtin_aliases = list(dict.fromkeys([str(x).strip() for x in (builtin_item.aliases or []) if str(x).strip()]))
            if user_aliases and builtin_aliases and user_aliases != builtin_aliases:
                diff["aliases"] = {
                    "user": user_aliases,
                    "builtin": builtin_aliases,
                }

            if diff:
                conflicts.append(
                    {
                        "dimension": user_item.dimension.value,
                        "value": user_item.value,
                        "key": key,
                        "conflicts": diff,
                    }
                )
        return conflicts

    def _write_conflicts_unlocked(self, conflicts: list[dict[str, object]]) -> None:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(conflicts),
            "items": conflicts,
        }
        tmp = self.conflicts_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.conflicts_path)

    def _write_user_state_unlocked(self, state: _TagState) -> None:
        self._write_state_file_unlocked(self.user_tags_path, state)

    def _write_builtin_state_unlocked(self, state: _TagState) -> None:
        self._write_state_file_unlocked(self.builtin_tags_path, state)

    def _write_state_file_unlocked(self, path: Path, state: _TagState) -> None:
        serialized_items: list[dict[str, object]] = []
        for item in state.items:
            row = item.model_dump(mode="json")
            # Keep non-knowledge dimensions explicit, but omit default knowledge
            # to reduce storage redundancy in tag files.
            if row.get("dimension") == TagDimension.KNOWLEDGE.value:
                row.pop("dimension", None)
            serialized_items.append(row)
        payload = {"items": serialized_items}
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)


# Default singleton used by the API and the agent prompt context.
tag_store = TagStore()
