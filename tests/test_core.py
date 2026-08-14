"""OopsNote Core 测试。"""

import base64
import json
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import oopsnote.core.store as store_module
from oopsnote.core import (
    AssetStore,
    BatchProcessJob,
    BatchProcessJobStore,
    BatchSegment,
    BatchSessionRecord,
    BatchSessionStore,
    Problem,
    ProblemMergeStore,
    RunArtifact,
    RunStatus,
    RunStore,
    RunValidationError,
    Searcher,
    SearchQuery,
    StateConflict,
    StorageCorruptionError,
    TagDimension,
    TagStore,
    TaskCreateRequest,
    TaskRecord,
    TaskStage,
    TaskStatus,
    TaskStore,
    problem_fingerprint,
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

    def test_transition_uses_status_and_active_run_compare_and_set(self):
        store = TaskStore(base_dir=Path(tempfile.mkdtemp()))
        task = store.create(TaskCreateRequest(subject="math"))
        claimed = store.transition(
            task.id,
            expected_statuses={TaskStatus.PENDING},
            expected_active_run_id=None,
            status=TaskStatus.PROCESSING,
            active_run_id="run-1",
        )
        assert claimed.active_run_id == "run-1"

        with pytest.raises(StateConflict):
            store.transition(
                task.id,
                expected_statuses={TaskStatus.PROCESSING},
                expected_active_run_id="old-run",
                status=TaskStatus.COMPLETED,
            )
        assert store.get(task.id).status == TaskStatus.PROCESSING

    def test_corrupt_task_is_reported_instead_of_silently_disappearing(self):
        base = Path(tempfile.mkdtemp())
        store = TaskStore(base_dir=base)
        (base / "broken.json").write_text("{not-json", encoding="utf-8")

        with pytest.raises(StorageCorruptionError, match=r"broken\.json"):
            store.list_all()

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

        t = store.mark_status(
            t.id,
            TaskStatus.FAILED,
            "模型超时",
            error_code="ocr_timeout",
        )
        assert t.status == TaskStatus.FAILED
        assert t.last_error == "模型超时"
        assert t.last_error_code == "ocr_timeout"
        t = store.mark_status(t.id, TaskStatus.PROCESSING)
        assert t.last_error is None
        assert t.last_error_code is None
        store.delete(t.id)

    def test_get_retries_transient_windows_file_lock(self, tmp_path, monkeypatch):
        store = TaskStore(base_dir=tmp_path)
        task = store.create(TaskCreateRequest(subject="数学"))
        original_read = Path.read_text
        attempts = 0

        def temporarily_locked(path, *args, **kwargs):
            nonlocal attempts
            if path == store._path(task.id) and attempts < 2:
                attempts += 1
                raise PermissionError(13, "sharing violation", str(path))
            return original_read(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", temporarily_locked)
        monkeypatch.setattr(store_module.time, "sleep", lambda _seconds: None)

        assert store.get(task.id).id == task.id
        assert attempts == 2

    def test_write_retries_transient_windows_replace_lock(self, tmp_path, monkeypatch):
        store = TaskStore(base_dir=tmp_path)
        task = store.create(TaskCreateRequest(subject="math"))
        original_replace = Path.replace
        attempts = 0

        def temporarily_locked(source, destination):
            nonlocal attempts
            if destination == store._path(task.id) and attempts < 2:
                attempts += 1
                raise PermissionError(13, "sharing violation", str(destination))
            return original_replace(source, destination)

        monkeypatch.setattr(Path, "replace", temporarily_locked)
        monkeypatch.setattr(store_module.time, "sleep", lambda _seconds: None)

        updated = store.update(task.id, subject="physics")

        assert updated.subject == "physics"
        assert store.get(task.id).subject == "physics"
        assert attempts == 2

    def test_update_rejects_invalid_or_unknown_fields_before_writing(self, tmp_path):
        store = TaskStore(base_dir=tmp_path)
        task = store.create(TaskCreateRequest(subject="math"))

        with pytest.raises(ValueError):
            store.update(task.id, status="not-a-task-status")
        with pytest.raises(TypeError, match="Unknown TaskRecord field"):
            store.update(task.id, typo_field="silently ignored before")

        persisted = store.get(task.id)
        assert persisted.status == TaskStatus.PENDING
        assert persisted.subject == "math"


class TestRunStore:
    def test_persists_attempts_and_stage_transitions(self, tmp_path):
        store = RunStore(tmp_path / "runs")
        first = store.create("task-1")
        assert first.backend == "pi"
        store.start(first.id, pid=123, log_path="runs/first.log")
        store.observe_stage(first.id, TaskStage.OCR, "提取题面")
        store.observe_stage(first.id, TaskStage.SOLVING, "生成解析")
        completed = store.finish(first.id, RunStatus.COMPLETED, exit_code=0)

        second = store.create("task-1")
        assert second.attempt == 2
        assert completed.stage_runs[0].status.value == "completed"
        assert completed.stage_runs[1].status.value == "completed"
        assert completed.ended_at is not None

    def test_terminal_transition_owns_end_to_end_duration(self, tmp_path):
        store = RunStore(tmp_path / "runs")
        run = store.create("task-1")
        queued_at = datetime.now(UTC) - timedelta(seconds=2)
        store.update(run.id, queued_at=queued_at, duration_ms=1)

        completed = store.finish(run.id, RunStatus.COMPLETED)

        assert completed.duration_ms is not None
        assert 1_900 <= completed.duration_ms <= 3_000

    def test_evidence_is_append_only_and_validation_failures_are_deduplicated(self, tmp_path):
        store = RunStore(tmp_path / "runs")
        run = store.create("task-1")
        artifact = RunArtifact(
            stage=TaskStage.OCR,
            kind="ocr",
            raw_output='{"raw":true}',
            parsed_output={"raw": True},
        )

        first = store.record_artifact(run.id, artifact)
        repeated = store.record_artifact(
            run.id,
            artifact.model_copy(update={"recorded_at": datetime.now(UTC)}),
        )

        assert len(first.artifacts) == 1
        assert len(repeated.artifacts) == 1
        with pytest.raises(StateConflict, match="already has ocr evidence"):
            store.record_artifact(
                run.id,
                artifact.model_copy(update={"raw_output": '{"raw":false}'}),
            )

        error = RunValidationError(
            stage=TaskStage.FINALIZING,
            raw_output="{}",
            message="problem missing answer",
        )
        store.record_validation_error(run.id, error)
        store.record_validation_error(
            run.id,
            error.model_copy(update={"recorded_at": datetime.now(UTC)}),
        )
        assert len(store.get(run.id).validation_errors) == 1

    def test_active_run_uses_heartbeat(self, tmp_path):
        store = RunStore(tmp_path / "runs")
        run = store.create("task-1")
        old = datetime.now(UTC) - timedelta(hours=1)
        store.update(run.id, heartbeat_at=old)
        assert store.active_for_task("task-1").id == run.id

    def test_update_rejects_invalid_or_unknown_fields_before_writing(self, tmp_path):
        store = RunStore(tmp_path / "runs")
        run = store.create("task-1")

        with pytest.raises(ValueError):
            store.update(run.id, status="not-a-run-status")
        with pytest.raises(TypeError, match="Unknown TaskRun field"):
            store.update(run.id, typo_field=True)

        assert store.get(run.id).status == RunStatus.QUEUED


class TestBatchProcessJobStore:
    def test_save_revalidates_caller_supplied_model_copy(self, tmp_path):
        store = BatchProcessJobStore(tmp_path / "batch-jobs")
        job = BatchProcessJob(file_hash="abc123", backend="pi-rust")
        store.save(job)

        invalid = job.model_copy(update={"status": "not-a-job-status"})
        with pytest.raises(ValueError):
            store.save(invalid)

        assert store.get(job.file_hash).status == "pending"


class TestBatchSessionStore:
    def test_create_revalidates_caller_supplied_model_copy(self, tmp_path):
        path = tmp_path / "batch-sessions.json"
        store = BatchSessionStore(path)
        record = BatchSessionRecord(
            file_hash="abc123",
            filename="questions.pdf",
            asset_path="/assets/questions.pdf",
            page_count=1,
        )
        invalid = record.model_copy(update={"excluded_page_indices": [-1]})

        with pytest.raises(ValueError):
            store.create(invalid)

        assert not path.exists()

    def test_segments_require_contiguous_order_and_valid_document_locations(self):
        with pytest.raises(ValueError, match="orders must be unique and contiguous"):
            BatchSegment.model_validate(
                {
                    "parts": [
                        {"page_index": 0, "x": 0, "y": 0, "width": 1, "height": 0.5, "order": 0},
                        {"page_index": 1, "x": 0, "y": 0, "width": 1, "height": 0.5, "order": 2},
                    ],
                }
            )

        with pytest.raises(ValueError, match="follow document reading order"):
            BatchSessionRecord.model_validate(
                {
                    "file_hash": "abc123",
                    "filename": "questions.pdf",
                    "asset_path": "/assets/questions.pdf",
                    "page_count": 2,
                    "segments": [
                        {
                            "parts": [
                                {
                                    "page_index": 1,
                                    "x": 0,
                                    "y": 0,
                                    "width": 1,
                                    "height": 0.5,
                                    "order": 0,
                                },
                                {
                                    "page_index": 0,
                                    "x": 0,
                                    "y": 0,
                                    "width": 1,
                                    "height": 0.5,
                                    "order": 1,
                                },
                            ],
                        }
                    ],
                }
            )

        with pytest.raises(ValueError, match="unavailable column"):
            BatchSessionRecord.model_validate(
                {
                    "file_hash": "abc123",
                    "filename": "questions.pdf",
                    "asset_path": "/assets/questions.pdf",
                    "page_count": 1,
                    "segments": [
                        {
                            "parts": [
                                {
                                    "page_index": 0,
                                    "column_index": 1,
                                    "x": 0,
                                    "y": 0,
                                    "width": 1,
                                    "height": 0.5,
                                    "order": 0,
                                }
                            ],
                        }
                    ],
                }
            )


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

    def test_ai_progressively_loads_up_to_six_branches_and_only_leaves(self, tmp_path):
        def leaf(node_id, title, scope="core"):
            return {
                "source_id": node_id,
                "title": title,
                "scope": scope,
                "is_leaf": True,
                "children": [],
            }

        level_two = [
            {
                "source_id": f"branch-{index}",
                "title": f"二级分支{index}",
                "scope": "core",
                "is_leaf": False,
                "children": [leaf(f"leaf-{index}", f"叶子标签{index}")],
            }
            for index in range(7)
        ]
        level_two[0]["children"].append(leaf("competition", "竞赛叶子", "competition"))
        level_two[6]["is_leaf"] = True
        level_two[6]["children"] = []
        tree_path = tmp_path / "knowledge_trees.json"
        tree_path.write_text(
            json.dumps(
                {
                    "subjects": {
                        "math": {
                            "root": {
                                "source_id": "root",
                                "title": "数学",
                                "scope": "core",
                                "is_leaf": False,
                                "children": [
                                    {
                                        "source_id": "level-one",
                                        "title": "一级目录",
                                        "scope": "core",
                                        "is_leaf": False,
                                        "children": level_two,
                                    }
                                ],
                            }
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        tags = TagStore(
            user_path=tmp_path / "tags_user.json",
            builtin_path=tmp_path / "tags_builtin.json",
            tree_path=tree_path,
        )

        groups = tags.ai_knowledge_branches("math", scope="core")
        values = tags.ai_knowledge_leaves(
            "math",
            [f"branch-{index}" for index in range(6)],
            scope="core",
        )

        assert groups == [
            {
                "value": "一级目录",
                "children": [
                    {"id": f"branch-{index}", "value": f"二级分支{index}"} for index in range(7)
                ],
            }
        ]
        assert tags.ai_knowledge_branches("数学", scope="core") == groups
        assert values == [f"叶子标签{index}" for index in range(6)]
        assert "竞赛叶子" not in values
        assert "竞赛叶子" in tags.knowledge_leaf_values("math")
        assert tags.ai_knowledge_leaves("math", ["branch-6"]) == ["二级分支6"]
        with pytest.raises(ValueError, match="between 1 and 6"):
            tags.ai_knowledge_leaves(
                "math",
                [f"branch-{index}" for index in range(7)],
            )
        with pytest.raises(ValueError, match="unknown level-two"):
            tags.ai_knowledge_leaves("math", ["level-one"])

    def test_subject_aliases_share_one_user_tag_namespace(self, tmp_path):
        tags = TagStore(
            user_path=tmp_path / "tags_user.json",
            builtin_path=tmp_path / "tags_builtin.json",
            tree_path=tmp_path / "knowledge_trees.json",
        )

        created = tags.upsert(TagDimension.ERROR, "计算失误", subject="数学")
        matched = tags.upsert(TagDimension.ERROR, "计算失误", subject="math")

        assert created.id == matched.id
        assert matched.subject == "math"
        assert [item.id for item in tags.search(TagDimension.ERROR, subject="数学")] == [created.id]

    def test_instances_serialize_writes_to_shared_file(self, tmp_path):
        user_path = tmp_path / "tags_user.json"
        builtin_path = tmp_path / "tags_builtin.json"
        stores = [TagStore(user_path=user_path, builtin_path=builtin_path) for _ in range(12)]
        threads = [
            threading.Thread(
                target=store.upsert,
                args=(TagDimension.CUSTOM, f"tag-{index}"),
            )
            for index, store in enumerate(stores)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
            assert not thread.is_alive()

        assert {item.value for item in stores[0].list_all()} == {
            f"tag-{index}" for index in range(12)
        }


class TestSearcher:
    def _make_task(self, subject, **problem_kw):
        p = Problem(subject=subject, **problem_kw)
        t = TaskRecord(subject=subject, problem=p)
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

    def test_same_original_filename_never_overwrites_existing_asset(self):
        store = AssetStore(base_dir=Path(tempfile.mkdtemp()))
        first = "data:text/plain;base64," + base64.b64encode(b"first").decode()
        second = "data:text/plain;base64," + base64.b64encode(b"second").decode()

        first_path = store.save_base64(first, "image.png")
        second_path = store.save_base64(second, "image.png")

        assert first_path != second_path
        assert store.resolve(first_path).read_bytes() == b"first"
        assert store.resolve(second_path).read_bytes() == b"second"

    def test_stable_asset_is_repaired_when_existing_content_differs(self):
        store = AssetStore(base_dir=Path(tempfile.mkdtemp()))
        path = store.save_bytes(b"old", "source.png", stable_name="stable")

        assert store.save_bytes(b"new", "source.png", stable_name="stable") == path
        assert store.resolve(path).read_bytes() == b"new"


class TestSearcherExtra:
    def test_since_filter(self):
        """since 过滤掉旧题。"""
        from datetime import datetime

        old = Problem(subject="数学", created_at=datetime(2020, 1, 1, tzinfo=UTC))
        new = Problem(subject="数学", created_at=datetime.now(UTC))
        s = Searcher(
            [
                TaskRecord(subject="数学", problem=old),
                TaskRecord(subject="数学", problem=new),
            ]
        )
        results = s.search(SearchQuery(since="2024-01-01"))
        assert len(results) == 1

    def test_invalid_since_is_rejected_at_query_boundary(self):
        """Invalid dates must fail validation instead of becoming no filter."""
        with pytest.raises(ValueError):
            SearchQuery(since="not-a-date")

    def test_since_filter_handles_legacy_naive_problem_timestamp(self):
        old = Problem(subject="数学", created_at=datetime(2020, 1, 1))
        task = TaskRecord(subject="数学", problem=old)

        results = Searcher([task]).search(SearchQuery(since="2024-01-01T00:00:00+00:00"))

        assert results == []

    def test_regex_error_handled(self):
        """非法正则不会崩溃。"""
        t = TaskRecord(subject="数学", problem=Problem(subject="数学", problem_text="test"))
        s = Searcher([t])
        results = s.search(SearchQuery(regex="\\"))
        assert len(results) == 0


class TestProblemIdentity:
    def test_fingerprint_ignores_whitespace_but_not_option_order(self):
        first = Problem(subject="math", problem_text="Find  x", options=["1", "2"])
        same = Problem(subject="math", problem_text=" Find\n x ", options=["1", "2"])
        reordered = Problem(subject="math", problem_text="Find x", options=["2", "1"])

        assert problem_fingerprint(first) == problem_fingerprint(same)
        assert problem_fingerprint(first) != problem_fingerprint(reordered)

    def test_merge_store_resolves_chain_and_rejects_cycle(self, tmp_path):
        store = ProblemMergeStore(tmp_path / "problem_merges.json")
        store.merge("b", "a")
        store.merge("c", "b")

        assert store.canonical_for("c") == "a"
        with pytest.raises(ValueError, match="already merged"):
            store.merge("a", "c")


class TestTaskPrintedContext:
    def test_manual_identifiers_override_ocr_and_can_fall_back(self):
        task = TaskRecord(
            metadata={"question_no": "8", "chapter": "人工章节"},
            ocr_context={
                "printed_question_no": 6,
                "printed_chapter": "印刷章节",
            },
        )

        assert task.effective_question_no() == "8"
        assert task.effective_chapter() == "人工章节"

        automatic = task.model_copy(update={"metadata": {"question_no": None, "chapter": None}})
        assert automatic.effective_question_no() == "6"
        assert automatic.effective_chapter() == "印刷章节"
