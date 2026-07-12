"""OopsNote Core 测试。"""

import base64
import tempfile
from pathlib import Path

import pytest

from oopsnote.core import (
    AssetStore,
    Problem,
    Searcher,
    SearchQuery,
    TagDimension,
    TagStore,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    TaskStore,
)


class TestTaskStore:
    def test_create_and_get(self):
        store = TaskStore(base_dir=Path(tempfile.mkdtemp()))
        t = store.create(TaskCreateRequest(subject="数学"))
        assert t.status == TaskStatus.PENDING
        assert t.subject == "数学"

        t2 = store.get(t.id)
        assert t2.id == t.id

        store.delete(t.id)
        with pytest.raises(KeyError):
            store.get(t.id)

    def test_list_all(self):
        store = TaskStore(base_dir=Path(tempfile.mkdtemp()))
        t1 = store.create(TaskCreateRequest(subject="数学"))
        t2 = store.create(TaskCreateRequest(subject="物理"))
        tasks = store.list_all()
        assert len(tasks) >= 2
        store.delete(t1.id)
        store.delete(t2.id)

    def test_mark_status(self):
        store = TaskStore(base_dir=Path(tempfile.mkdtemp()))
        t = store.create(TaskCreateRequest(subject="数学"))
        t = store.mark_status(t.id, TaskStatus.PROCESSING)
        assert t.status == TaskStatus.PROCESSING

        t = store.mark_status(t.id, TaskStatus.FAILED, "模型超时")
        assert t.status == TaskStatus.FAILED
        assert t.last_error == "模型超时"
        store.delete(t.id)


class TestTagStore:
    def test_upsert_and_search(self):
        tags = TagStore(
            user_path=Path(tempfile.mkdtemp()) / "tags_user.json",
            builtin_path=Path(tempfile.mkdtemp()) / "tags_builtin.json",
        )
        tags.upsert(TagDimension.KNOWLEDGE, "二次函数", aliases=["一元二次函数"])
        tags.upsert(TagDimension.ERROR, "计算失误")

        items = tags.list_all()
        assert len(items) == 2

        results = tags.search(dimension=TagDimension.KNOWLEDGE, query="二次")
        assert len(results) == 1
        assert results[0].value == "二次函数"

    def test_dedup(self):
        tags = TagStore(
            user_path=Path(tempfile.mkdtemp()) / "tags_user.json",
            builtin_path=Path(tempfile.mkdtemp()) / "tags_builtin.json",
        )
        tags.upsert(TagDimension.KNOWLEDGE, "二次函数")
        tags.upsert(TagDimension.KNOWLEDGE, "二次函数", aliases=["新别名"])
        items = tags.list_all()
        assert len(items) == 1
        assert "新别名" in items[0].aliases

    def test_delete(self):
        tags = TagStore(
            user_path=Path(tempfile.mkdtemp()) / "tags_user.json",
            builtin_path=Path(tempfile.mkdtemp()) / "tags_builtin.json",
        )
        tag = tags.upsert(TagDimension.KNOWLEDGE, "要删除的标签")
        assert tags.delete(tag.id)
        assert not tags.delete("nonexistent")


class TestSearcher:
    def _make_task(self, subject, **problem_kw):
        p = Problem(subject=subject, **problem_kw)
        t = TaskRecord(subject=subject, problems=[p])
        return t

    def test_by_subject(self):
        t1 = self._make_task("数学", problem_text="求导", knowledge_points=["导数"])
        t2 = self._make_task("物理", problem_text="牛顿定律", knowledge_points=["力学"])

        s = Searcher([t1, t2])
        results = s.search(SearchQuery(subject="数学"))
        assert len(results) == 1
        assert results[0].subject == "数学"

    def test_by_tags(self):
        t1 = self._make_task("数学", knowledge_points=["二次函数", "最值问题"])
        t2 = self._make_task("数学", knowledge_points=["三角函数"])

        s = Searcher([t1, t2])
        results = s.search(SearchQuery(tags=["二次函数"]))
        assert len(results) == 1
        assert "二次函数" in results[0].knowledge_points

    def test_by_error_type(self):
        t1 = self._make_task("数学", error_hypothesis=["计算失误"])
        t2 = self._make_task("数学", error_hypothesis=["概念不清"])

        s = Searcher([t1, t2])
        results = s.search(SearchQuery(error_type="计算失误"))
        assert len(results) == 1
        assert "计算失误" in results[0].error_hypothesis

    def test_by_regex(self):
        t1 = self._make_task("数学", problem_text="已知 f(x) = x²", answer="2x")
        t2 = self._make_task("数学", problem_text="求 sin 值")

        s = Searcher([t1, t2])
        results = s.search(SearchQuery(regex=r"f\(x\)"))
        assert len(results) == 1

    def test_empty(self):
        s = Searcher([])
        assert s.search(SearchQuery(subject="数学")) == []


class TestAssetStore:
    def test_save_base64(self):
        store = AssetStore(base_dir=Path(tempfile.mkdtemp()))
        data = "data:text/plain;base64," + base64.b64encode(b"hello").decode()
        path = store.save_base64(data)
        assert path.startswith("/assets/")

    def test_save_file(self):
        store = AssetStore(base_dir=Path(tempfile.mkdtemp()))
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"pdf content")
            f.flush()
            path = store.save_file(f.name)
        assert path.startswith("/assets/")
        assert path.endswith(".pdf")

    def test_save_plain_binary(self):
        """非 data: URI 的原始 base64 字符串也能存。"""
        import base64
        store = AssetStore(base_dir=Path(tempfile.mkdtemp()))
        data = base64.b64encode(b"raw bytes").decode()
        path = store.save_base64(data)
        assert path.startswith("/assets/")


class TestSearcherExtra:
    def test_since_filter(self):
        """since 过滤掉旧题。"""
        from datetime import datetime, timedelta, timezone
        old = Problem(subject="数学", created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
        new = Problem(subject="数学", created_at=datetime.now(timezone.utc))
        s = Searcher([
            TaskRecord(subject="数学", problems=[old]),
            TaskRecord(subject="数学", problems=[new]),
        ])
        results = s.search(SearchQuery(since="2024-01-01"))
        assert len(results) == 1

    def test_regex_error_handled(self):
        """非法正则不会崩溃。"""
        t = TaskRecord(subject="数学", problems=[Problem(subject="数学", problem_text="test")])
        s = Searcher([t])
        results = s.search(SearchQuery(regex="\\"))
        assert len(results) == 0
