"""Tracked knowledge-catalog and runtime user-tag management."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from oopsnote.catalog import KNOWLEDGE_TAGS_PATH, KNOWLEDGE_TREES_PATH

from .models import TagCreateRequest, TagDimension, TagItem


class TagStore:
    """文件持久化的标签注册表。

    - 内置标签（builtin.json）不可删除，用户标签（user.json）可增删改。
    - 按引用计数排序，优先展示常用标签。
    """

    # REST and the shared MCP server use separate store instances in the same
    # process. They still write the same JSON file, so locking must be shared.
    _lock = threading.RLock()

    def __init__(
        self,
        user_path: Optional[Path] = None,
        builtin_path: Optional[Path] = None,
        tree_path: Optional[Path] = None,
    ) -> None:
        base = Path(__file__).resolve().parents[1] / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.user_path = user_path or base / "tags_user.json"
        self.builtin_path = builtin_path or KNOWLEDGE_TAGS_PATH
        self.tree_path = tree_path or KNOWLEDGE_TREES_PATH
        self._builtin_cache: Optional[list[TagItem]] = None
        self._tree_cache: Optional[dict[str, Any]] = None

    # ── 加载 ──────────────────────────────────────────

    def _load_builtin(self) -> list[TagItem]:
        if self._builtin_cache is not None:
            return list(self._builtin_cache)
        if not self.builtin_path.exists():
            return []
        raw = json.loads(self.builtin_path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("items", [])
        result: list[TagItem] = []
        for i in items:
            i["source"] = "builtin"
            result.append(TagItem(**i))
        self._builtin_cache = result
        return list(result)

    def _load_user(self) -> list[TagItem]:
        if not self.user_path.exists():
            return []
        raw = json.loads(self.user_path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("items", [])
        result: list[TagItem] = []
        for i in items:
            i["source"] = "user"
            result.append(TagItem(**i))
        return result

    def _write_user(self, items: list[TagItem]) -> None:
        self.user_path.parent.mkdir(parents=True, exist_ok=True)
        data = [i.model_dump(mode="json") for i in items]
        tmp = self.user_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.user_path)

    def _all_items(self) -> list[TagItem]:
        """合并内置 + 用户标签，用户标签覆盖同名。"""
        builtin = self._load_builtin()
        user = self._load_user()
        # User tags override a builtin with the same dimension, subject, and value.
        seen: set[tuple[TagDimension, Optional[str], str]] = set()
        result: list[TagItem] = []
        for item in user + builtin:
            key = (item.dimension, item.subject, item.value.casefold())
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    # ── 查询 ──────────────────────────────────────────

    def list_all(self) -> list[TagItem]:
        """列出所有标签，按 ref_count 降序。"""
        items = self._all_items()
        items.sort(key=lambda t: (-t.ref_count, t.value))
        return items

    def search(
        self,
        dimension: Optional[TagDimension] = None,
        query: Optional[str] = None,
        limit: int = 50,
        *,
        subject: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> list[TagItem]:
        """搜索标签（按 value 或 alias 匹配）。"""
        q = (query or "").strip().casefold()
        items = self._all_items()
        if dimension:
            items = [t for t in items if t.dimension == dimension]
        if subject:
            items = [
                t for t in items
                if t.subject == subject
                or (t.subject is None and t.dimension != TagDimension.KNOWLEDGE)
            ]
        if scope:
            items = [
                t for t in items
                if t.source == "user" or scope == t.scope or scope in t.scopes
            ]
        if q:
            items = [
                t for t in items
                if q in t.value.casefold()
                or any(q in a.casefold() for a in t.aliases)
            ]
        def rank(item: TagItem) -> tuple[int, int, int, str]:
            if not q:
                match_rank = 0
            else:
                value = item.value.casefold()
                aliases = [alias.casefold() for alias in item.aliases]
                if value == q:
                    match_rank = 0
                elif value.startswith(q):
                    match_rank = 1
                elif q in value:
                    match_rank = 2
                elif any(alias == q or alias.endswith(f"/{q}") for alias in aliases):
                    match_rank = 3
                else:
                    match_rank = 4
            return (match_rank, -item.ref_count, item.depth or 0, item.value)

        items.sort(key=rank)
        if not subject:
            # The UI stores tag values rather than catalog IDs. Avoid rendering
            # indistinguishable cross-subject duplicates when it has no subject context.
            unique: list[TagItem] = []
            seen_values: set[tuple[TagDimension, str]] = set()
            for item in items:
                key = (item.dimension, item.value.casefold())
                if key not in seen_values:
                    seen_values.add(key)
                    unique.append(item)
            items = unique
        return items[:max(1, limit)]

    def knowledge_tree(self, subject: Optional[str] = None) -> dict[str, Any]:
        """Return the cleaned tracked knowledge tree, optionally for one subject."""

        if self._tree_cache is not None:
            document = self._tree_cache
        elif not self.tree_path.exists():
            return {"schema_version": "xkw-knowledge-tree-v1", "subjects": {}}
        else:
            document = json.loads(self.tree_path.read_text(encoding="utf-8"))
            self._tree_cache = document
        if not subject:
            return document
        item = document.get("subjects", {}).get(subject)
        return {
            "schema_version": document.get("schema_version", "xkw-knowledge-tree-v1"),
            "subjects": {subject: item} if item else {},
        }

    # ── 增删改 ────────────────────────────────────────

    def upsert(
        self,
        dimension: TagDimension,
        value: str,
        aliases: Optional[list[str]] = None,
        subject: Optional[str] = None,
    ) -> TagItem:
        """创建或更新标签。已存在则合并 aliases。"""
        value = value.strip()
        if not value:
            raise ValueError("tag value is required")
        aliases = [a.strip() for a in (aliases or []) if a.strip()]

        with self._lock:
            user = self._load_user()
            key = (dimension, subject, value.casefold())
            for item in user:
                if (item.dimension, item.subject, item.value.casefold()) == key:
                    # 更新 aliases
                    merged = list(dict.fromkeys(item.aliases + aliases))
                    if merged != item.aliases:
                        item.aliases = merged
                        self._write_user(user)
                    return item
            # 新建
            from uuid import uuid4
            new_item = TagItem(
                id=uuid4().hex,
                dimension=dimension,
                value=value,
                aliases=aliases,
                subject=subject,
                source="user",
            )
            user.append(new_item)
            self._write_user(user)
            return new_item

    def delete(self, tag_id: str) -> bool:
        """按 ID 删除用户标签。内置标签不可删。"""
        with self._lock:
            user = self._load_user()
            before = len(user)
            user = [t for t in user if t.id != tag_id]
            if len(user) < before:
                self._write_user(user)
                return True
        return False

    def get_by_id(self, tag_id: str) -> Optional[TagItem]:
        for item in self._all_items():
            if item.id == tag_id:
                return item
        return None

    def ensure(self, dimension: TagDimension, values: list[str]) -> list[TagItem]:
        """确保一批标签存在（批量 upsert）。"""
        result: list[TagItem] = []
        for v in values:
            if v.strip():
                result.append(self.upsert(dimension, v.strip()))
        return result
