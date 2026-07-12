"""标签库管理。

文件持久化：storage/settings/tags_user.json + tags_builtin.json
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from .models import TagCreateRequest, TagDimension, TagItem


class TagStore:
    """文件持久化的标签注册表。

    - 内置标签（builtin.json）不可删除，用户标签（user.json）可增删改。
    - 按引用计数排序，优先展示常用标签。
    """

    def __init__(
        self,
        user_path: Optional[Path] = None,
        builtin_path: Optional[Path] = None,
    ) -> None:
        base = Path(__file__).resolve().parents[1] / "storage" / "settings"
        base.mkdir(parents=True, exist_ok=True)
        self.user_path = user_path or base / "tags_user.json"
        self.builtin_path = builtin_path or base / "tags_builtin.json"
        self._lock = threading.Lock()

    # ── 加载 ──────────────────────────────────────────

    def _load_builtin(self) -> list[TagItem]:
        if not self.builtin_path.exists():
            return []
        raw = json.loads(self.builtin_path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("items", [])
        result: list[TagItem] = []
        for i in items:
            i["source"] = "builtin"
            result.append(TagItem(**i))
        return result

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
        # 用户标签优先（去重：同 dimension + value）
        seen: set[tuple[TagDimension, str]] = set()
        result: list[TagItem] = []
        for item in user + builtin:
            key = (item.dimension, item.value.casefold())
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
    ) -> list[TagItem]:
        """搜索标签（按 value 或 alias 匹配）。"""
        q = (query or "").strip().casefold()
        items = self._all_items()
        if dimension:
            items = [t for t in items if t.dimension == dimension]
        if q:
            items = [
                t for t in items
                if q in t.value.casefold()
                or any(q in a.casefold() for a in t.aliases)
            ]
        items.sort(key=lambda t: (-t.ref_count, t.value))
        return items[:max(1, limit)]

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
            key = (dimension, value.casefold())
            for item in user:
                if (item.dimension, item.value.casefold()) == key:
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
