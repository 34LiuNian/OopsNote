from __future__ import annotations

import base64
import hashlib
import time
from io import BytesIO
from types import SimpleNamespace

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

from oopsnote.api import main
from oopsnote.ai import HermesRunner
from oopsnote.core import AssetStore, BatchProcessJobStore, BatchSessionStore, Problem, RunStatus, RunStore, TagStore, TaskCreateRequest, TaskStore, TaskStatus


class RecordingBatchRunner:
    def __init__(self, task_store: TaskStore) -> None:
        self.task_store = task_store
        self.submitted: list[str] = []

    def recover_stale(self) -> int:
        return 0

    def submit(self, task_id: str):
        self.submitted.append(task_id)
        run_id = f"run-{len(self.submitted)}"
        self.task_store.update(
            task_id,
            status=TaskStatus.PROCESSING,
            active_run_id=run_id,
        )
        return SimpleNamespace(id=run_id)


def png_base64(color: str = "white") -> str:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_tracked_knowledge_catalog_supports_subject_search_and_tree():
    client = TestClient(main.app)

    tags = client.get(
        "/tags",
        params={
            "dimension": "knowledge",
            "query": "牛顿第二定律",
            "subject": "physics",
            "scope": "core",
            "limit": 5,
        },
    )
    tree = client.get("/tags/tree", params={"subject": "physics"})

    assert tags.status_code == 200
    assert tags.json()["items"][0]["value"] == "牛顿第二定律"
    assert {item["subject"] for item in tags.json()["items"]} == {"physics"}
    assert tree.status_code == 200
    assert tree.json()["subjects"]["physics"]["root"]["title"] == "高中物理综合库"


def test_web_contract_uses_wrapped_collections_and_persisted_upload(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    monkeypatch.setattr(main, "STORAGE_DIR", storage)
    monkeypatch.setattr(main, "TASK_STORE", TaskStore(base_dir=storage))
    monkeypatch.setattr(
        main,
        "TAG_STORE",
        TagStore(
            user_path=storage / "settings" / "tags_user.json",
            builtin_path=storage / "settings" / "tags_builtin.json",
        ),
    )
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(base_dir=storage / "assets"))
    monkeypatch.setattr(
        main,
        "BATCH_SESSION_STORE",
        BatchSessionStore(storage / "settings" / "batch_sessions.json"),
    )
    client = TestClient(main.app)

    payload = {
        "subject": "数学",
        "filename": "region.png",
        "mime_type": "image/png",
        "image_base64": png_base64(),
        "knowledge_tags": ["函数"],
        "error_tags": ["定义域"],
        "user_tags": ["期中"],
    }
    created = client.post("/upload", json=payload)

    assert created.status_code == 200
    task = created.json()["task"]
    assert task["status"] == "pending"
    assert task["asset"]["path"].endswith(".png")
    assert task["asset"]["path"] != "/assets/region.png"
    assert task["problem"] is None
    assert task["solution"] is None
    assert task["tag"] is None
    assert "problems" not in task

    tasks = client.get("/tasks").json()
    tags = client.get("/tags?query=函数").json()
    problems = client.get("/problems").json()

    assert tasks["items"][0]["id"] == task["id"]
    assert tags["items"][0]["value"] == "函数"
    assert problems == {"items": []}

    stored = main.TASK_STORE.set_problem(
        task["id"],
        Problem(
            subject="数学",
            problem_text="求 $1+1$。",
            answer="$2$",
            explanation="$1+1=2$。",
        ),
    )
    detail = client.get(f"/tasks/{task['id']}").json()["task"]
    assert detail["problem"]["problem_id"] == stored.problem.id
    assert detail["solution"]["answer"] == "$2$"
    assert detail["tag"]["problem_id"] == stored.problem.id

    edited = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "problem_text": "计算 $1+1$。",
            "question_no": "12",
            "user_tags": ["重点"],
            "diagram_detected": True,
            "diagram_kind": "tikz",
            "diagram_tikz_source": "\\draw (0,0) -- (1,1);",
            "diagram_svg": "<svg></svg>",
            "diagram_render_status": "ready",
        },
    )
    assert edited.status_code == 200
    edited_problem = edited.json()["task"]["problem"]
    assert edited_problem["problem_text"] == "计算 $1+1$。"
    assert edited_problem["question_no"] == "12"
    assert edited_problem["user_tags"] == ["重点"]
    assert edited_problem["diagram_tikz_source"] == "\\draw (0,0) -- (1,1);"
    assert edited_problem["diagram_render_status"] == "ready"
    assert edited_problem["diagram_image_path"] is None
    assert edited_problem["diagram_position"] == "right"
    assert edited_problem["diagram_scale_percent"] is None

    image_edited = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_tikz_source": "stale tikz must be cleared",
            "diagram_svg": "<svg>stale</svg>",
            "diagram_image_path": task["asset"]["path"],
            "diagram_position": "left",
            "diagram_scale_percent": 125,
        },
    )
    assert image_edited.status_code == 200
    image_problem = image_edited.json()["task"]["problem"]
    assert image_problem["diagram_kind"] == "image"
    assert image_problem["diagram_image_path"] == task["asset"]["path"]
    assert image_problem["diagram_tikz_source"] is None
    assert image_problem["diagram_svg"] is None
    assert image_problem["diagram_position"] == "left"
    assert image_problem["diagram_scale_percent"] == 125

    invalid_image = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_image_path": "/assets/another.png",
        },
    )
    assert invalid_image.status_code == 422

    problem_summary = client.get("/problems").json()["items"][0]
    assert problem_summary["diagram_kind"] == "image"
    assert problem_summary["diagram_image_path"] == task["asset"]["path"]


def test_tag_rename_and_merge_migrate_persisted_problem_references(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    tag_store = TagStore(
        user_path=storage / "settings" / "tags_user.json",
        builtin_path=storage / "settings" / "tags_builtin.json",
    )
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "TAG_STORE", tag_store)
    client = TestClient(main.app)

    old_error = client.post("/tags", json={"dimension": "error", "value": "旧错因"}).json()["items"][0]
    source_custom = client.post("/tags", json={"dimension": "custom", "value": "待合并"}).json()["items"][0]
    target_custom = client.post("/tags", json={"dimension": "custom", "value": "目标标签"}).json()["items"][0]
    task = task_store.create(TaskCreateRequest(
        subject="math",
        metadata={"user_tags": ["待合并"]},
    ))
    task_store.set_problem(task.id, Problem(
        subject="math",
        problem_text="题目",
        error_hypothesis=["旧错因"],
    ))

    renamed = client.put(f"/tags/{old_error['id']}", json={"value": "新错因"})
    merged = client.post(
        f"/tags/{source_custom['id']}/merge",
        json={"target_id": target_custom["id"]},
    )

    assert renamed.status_code == 200
    assert task_store.get(task.id).problem.error_hypothesis == ["新错因"]
    assert merged.status_code == 200
    assert merged.json()["tasks_modified"] == 1
    assert merged.json()["fields_modified"] == 1
    assert task_store.get(task.id).metadata["user_tags"] == ["目标标签"]


def test_batch_session_deduplicates_source_and_persists_progress(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(base_dir=storage / "assets"))
    monkeypatch.setattr(
        main,
        "BATCH_SESSION_STORE",
        BatchSessionStore(storage / "settings" / "batch_sessions.json"),
    )
    client = TestClient(main.app)
    source = b"same-pdf-content"
    digest = hashlib.sha256(source).hexdigest()

    created = client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={"x-oopsnote-filename": "mock.pdf", "x-oopsnote-page-count": "7", "content-type": "application/pdf"},
    )
    assert created.status_code == 200
    assert created.json()["session"]["asset_path"].endswith(f"batch-{digest}.pdf")
    assert created.json()["session"]["page_count"] == 7

    updated = client.patch(
        f"/batch-sessions/{digest}",
        json={
            "expected_revision": 0,
            "page_count": 423,
            "subject": "数学",
            "notes": "目录后开始",
            "active_page": 4,
            "excluded_page_indices": [2],
            "segments": [{
                "id": "region-1",
                "page_index": 3,
                "x": 0.1,
                "y": 0.2,
                "width": 0.3,
                "height": 0.4,
                "continuation": {"page_index": 4, "x": 0.1, "y": 0, "width": 0.3, "height": 0.25},
            }],
        },
    )
    assert updated.status_code == 200

    renamed = client.patch(
        f"/batch-sessions/{digest}",
        json={"filename": "renamed.pdf", "expected_revision": updated.json()["session"]["revision"]},
    )
    assert renamed.status_code == 200
    assert renamed.json()["session"]["filename"] == "renamed.pdf"

    duplicate = client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={"x-oopsnote-filename": "renamed.pdf", "content-type": "application/pdf"},
    )
    assert duplicate.status_code == 200
    restored = client.get(f"/batch-sessions/{digest}").json()["session"]
    assert restored["filename"] == "renamed.pdf"
    assert restored["active_page"] == 4
    assert restored["excluded_page_indices"] == [2]
    assert restored["segments"][0]["page_index"] == 3
    assert restored["segments"][0]["continuation"]["page_index"] == 4
    assert [part["page_index"] for part in restored["segments"][0]["parts"]] == [3, 4]
    assert restored["crop_rect"] == {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    assert restored["crop_confirmed"] is False
    assert restored["column_layout"] == {"column_count": 1, "overlap_ratio": 0.5}
    assert client.get("/batch-sessions").json()["items"][0]["file_hash"] == digest


def test_batch_session_persists_parts_crop_and_deletes_without_tasks(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    run_store = RunStore(storage / "runs")
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(base_dir=storage / "assets"))
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", run_store)
    monkeypatch.setattr(
        main,
        "TAG_STORE",
        TagStore(storage / "settings" / "tags.json"),
    )
    monkeypatch.setattr(
        main,
        "BATCH_SESSION_STORE",
        BatchSessionStore(storage / "settings" / "batch_sessions.json"),
    )
    client = TestClient(main.app)
    source = b"continuous-pdf"
    digest = hashlib.sha256(source).hexdigest()
    assert client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={"x-oopsnote-filename": "continuous.pdf", "content-type": "application/pdf"},
    ).status_code == 200
    updated = client.patch(
        f"/batch-sessions/{digest}",
        json={
            "expected_revision": 0,
            "page_count": 3,
            "crop_rect": {"x": 0.1, "y": 0.08, "width": 0.8, "height": 0.84},
            "crop_confirmed": True,
            "column_layout": {"column_count": 2, "overlap_ratio": 0.5},
            "segments": [{
                "id": "selection-1",
                "parts": [
                    {"page_index": 0, "column_index": 1, "x": 0.2, "y": 0.8, "width": 0.5, "height": 0.2, "order": 0},
                    {"page_index": 1, "column_index": 0, "x": 0.2, "y": 0, "width": 0.5, "height": 1, "order": 1},
                    {"page_index": 2, "column_index": 0, "x": 0.2, "y": 0, "width": 0.5, "height": 0.15, "order": 2},
                ],
                "question_no": 1,
                "status": "needs_review",
                "review_reason": "multiple_questions",
                "review_previous_status": "pending",
            }],
        },
    )
    assert updated.status_code == 200
    session = updated.json()["session"]
    assert session["crop_confirmed"] is True
    assert session["column_layout"] == {"column_count": 2, "overlap_ratio": 0.5}
    assert len(session["segments"][0]["parts"]) == 3
    assert session["segments"][0]["parts"][0]["column_index"] == 1
    assert session["segments"][0]["status"] == "needs_review"
    assert session["segments"][0]["review_reason"] == "multiple_questions"

    task = client.post(
        "/upload?auto_process=false",
        json={
            "subject": "auto",
            "notes": "",
            "knowledge_tags": [],
            "error_tags": [],
            "user_tags": [],
            "image_base64": png_base64("blue"),
            "filename": "selection-1.png",
            "mime_type": "image/png",
            "batch_session_hash": digest,
            "batch_segment_id": "selection-1",
            "batch_page_index": 0,
            "batch_question_no": 1,
        },
    ).json()["task"]
    assert task["trace"]["batch_session_available"] is True

    task_store.update(
        task["id"],
        status=TaskStatus.COMPLETED,
        problem=Problem(subject="math", problem_text="第一道完整题"),
        metadata={**task_store.get(task["id"]).metadata, "intake_review_reason": "multiple_questions"},
    )
    renamed = client.patch(
        f"/batch-sessions/{digest}",
        json={"filename": "renamed-continuous.pdf", "expected_revision": session["revision"]},
    )
    assert renamed.status_code == 200
    renamed_task = client.get(f"/tasks/{task['id']}").json()["task"]
    assert renamed_task["problem"]["source"] == "renamed-continuous.pdf"
    assert renamed_task["trace"]["source_file_name"] == "renamed-continuous.pdf"
    assert renamed_task["trace"]["page_index"] == 0
    source_items = client.get("/tags", params={"dimension": "meta"}).json()["items"]
    assert [item["value"] for item in source_items] == ["renamed-continuous.pdf"]
    assert source_items[0]["ref_count"] == 1
    linked_segment = {
        **session["segments"][0],
        "task_id": task["id"],
        "status": "processing",
        "review_reason": None,
        "review_previous_status": None,
        "review_resolved": False,
    }
    assert client.patch(
        f"/batch-sessions/{digest}",
        json={
            "segments": [linked_segment],
            "expected_revision": renamed.json()["session"]["revision"],
        },
    ).status_code == 200
    persisted_before_read = main.BATCH_SESSION_STORE.get(digest)
    auto_review_session = client.get(f"/batch-sessions/{digest}").json()["session"]
    persisted_after_read = main.BATCH_SESSION_STORE.get(digest)
    auto_review = auto_review_session["segments"][0]
    assert persisted_after_read.revision == persisted_before_read.revision
    assert persisted_after_read.segments[0].status == "processing"
    assert auto_review["status"] == "needs_review"
    assert auto_review["review_reason"] == "multiple_questions"
    assert auto_review["review_previous_status"] == "completed"

    resolved_segment = {
        **auto_review,
        "status": "completed",
        "review_reason": None,
        "review_previous_status": None,
        "review_resolved": True,
    }
    assert client.patch(
        f"/batch-sessions/{digest}",
        json={
            "segments": [resolved_segment],
            "expected_revision": auto_review_session["revision"],
        },
    ).status_code == 200
    resolved = client.get(f"/batch-sessions/{digest}").json()["session"]["segments"][0]
    assert resolved["status"] == "completed"
    assert resolved["review_resolved"] is True

    deleted = client.delete(f"/batch-sessions/{digest}")
    assert deleted.status_code == 200
    assert deleted.json()["preserved_task_ids"] == [task["id"]]
    assert client.get(f"/batch-sessions/{digest}").status_code == 404
    retained = client.get(f"/tasks/{task['id']}").json()["task"]
    assert retained["trace"]["batch_session_available"] is False


def test_batch_process_renders_all_pending_segments_and_enqueues_once(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    runner = RecordingBatchRunner(task_store)
    monkeypatch.setattr(main, "STORAGE_DIR", storage)
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(storage / "assets"))
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(storage / "runs"))
    monkeypatch.setattr(main, "TAG_STORE", TagStore(storage / "settings" / "tags.json"))
    monkeypatch.setattr(
        main,
        "BATCH_SESSION_STORE",
        BatchSessionStore(storage / "settings" / "batch_sessions.json"),
    )
    monkeypatch.setattr(main, "BATCH_PROCESS_JOB_STORE", BatchProcessJobStore(storage / "batch_jobs"))
    monkeypatch.setattr(main, "PI_RUNNER", runner)
    client = TestClient(main.app)

    document = pymupdf.open()
    page = document.new_page(width=100, height=100)
    page.draw_rect(page.rect, color=(0, 0, 0), fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(0, 0, 50, 50), color=(1, 0, 0), fill=(1, 0, 0))
    source = document.tobytes()
    document.close()
    digest = hashlib.sha256(source).hexdigest()
    assert client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={
            "x-oopsnote-filename": "questions.pdf",
            "x-oopsnote-page-count": "1",
            "content-type": "application/pdf",
        },
    ).status_code == 200
    assert client.patch(
        f"/batch-sessions/{digest}",
        json={
            "expected_revision": 0,
            "page_count": 1,
            "crop_confirmed": True,
            "segments": [
                {
                    "id": "segment-1",
                    "parts": [{"page_index": 0, "x": 0, "y": 0, "width": 0.5, "height": 0.5, "order": 0}],
                    "question_no": 1,
                    "status": "pending",
                },
                {
                    "id": "segment-2",
                    "parts": [{"page_index": 0, "x": 0.5, "y": 0.5, "width": 0.5, "height": 0.5, "order": 0}],
                    "question_no": 2,
                    "status": "pending",
                },
            ],
        },
    ).status_code == 200

    processed = client.post(
        f"/batch-sessions/{digest}/process",
        json={"expected_revision": 1},
    )

    assert processed.status_code == 200
    payload = processed.json()
    assert payload["requested"] == 2
    assert payload["created"] == 2
    assert payload["queued"] == 2
    assert payload["failed"] == 0
    assert payload["job_status"] == "submitted"
    assert [item["status"] for item in payload["items"]] == ["processing", "processing"]
    assert len(runner.submitted) == 2
    assert all(segment["task_id"] for segment in payload["session"]["segments"])
    assert {segment["status"] for segment in payload["session"]["segments"]} == {"processing"}
    tasks = task_store.list_all()
    assert len(tasks) == 2
    assert {task.metadata["batch_question_no"] for task in tasks} == {1, 2}
    assert all((storage / task.asset_path.lstrip("/")).is_file() for task in tasks)
    job = main.BATCH_PROCESS_JOB_STORE.get(digest)
    assert {state.status for state in job.segments} == {"processing"}
    assert all(state.task_id and state.run_id for state in job.segments)

    stale_empty = client.patch(
        f"/batch-sessions/{digest}",
        json={"expected_revision": 1, "segments": []},
    )
    assert stale_empty.status_code == 409
    current_empty = client.patch(
        f"/batch-sessions/{digest}",
        json={
            "expected_revision": payload["session"]["revision"],
            "segments": [],
        },
    )
    assert current_empty.status_code == 409
    retained_session = client.get(f"/batch-sessions/{digest}").json()["session"]
    assert len(retained_session["segments"]) == 2
    assert all(segment["task_id"] for segment in retained_session["segments"])

    repeated = client.post(
        f"/batch-sessions/{digest}/process",
        json={"expected_revision": payload["session"]["revision"]},
    )
    assert repeated.status_code == 200
    assert repeated.json()["requested"] == 0
    assert len(runner.submitted) == 2


def test_batch_process_preflights_every_segment_before_creating_tasks(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(storage / "assets"))
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "TAG_STORE", TagStore(storage / "settings" / "tags.json"))
    monkeypatch.setattr(
        main,
        "BATCH_SESSION_STORE",
        BatchSessionStore(storage / "settings" / "batch_sessions.json"),
    )
    monkeypatch.setattr(main, "BATCH_PROCESS_JOB_STORE", BatchProcessJobStore(storage / "batch_jobs"))
    monkeypatch.setattr(main, "PI_RUNNER", RecordingBatchRunner(task_store))
    client = TestClient(main.app)
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    digest = hashlib.sha256(image).hexdigest()
    assert client.put(
        f"/batch-sessions/{digest}/source",
        content=image,
        headers={
            "x-oopsnote-filename": "question.png",
            "x-oopsnote-page-count": "1",
            "content-type": "image/png",
        },
    ).status_code == 200
    assert client.patch(
        f"/batch-sessions/{digest}",
        json={
            "expected_revision": 0,
            "page_count": 1,
            "crop_confirmed": True,
            "segments": [{
                "id": "bad-page",
                "parts": [{"page_index": 1, "x": 0, "y": 0, "width": 1, "height": 1, "order": 0}],
                "question_no": 1,
                "status": "pending",
            }],
        },
    ).status_code == 200

    processed = client.post(
        f"/batch-sessions/{digest}/process",
        json={"expected_revision": 1},
    )

    assert processed.status_code == 422
    assert "unavailable page 2" in processed.json()["detail"]
    assert task_store.list_all() == []


def test_process_endpoint_creates_observable_run(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    run_store = RunStore(storage / "runs")
    runner = HermesRunner(
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
    )
    monkeypatch.setattr(main, "STORAGE_DIR", storage)
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", run_store)
    monkeypatch.setattr(main, "HERMES_RUNNER", runner)

    def fake_run(task_id, run_id):
        task_store.update(task_id, status=TaskStatus.COMPLETED, active_run_id=None)
        run_store.finish(run_id, RunStatus.COMPLETED, exit_code=0)

    monkeypatch.setattr(runner, "run", fake_run)
    client = TestClient(main.app)
    task = client.post("/tasks", json={"subject": "math"}).json()["task"]

    response = client.post(f"/tasks/{task['id']}/process?backend=hermes")
    assert response.status_code == 200
    assert response.json()["run"]["attempt"] == 1
    deadline = time.monotonic() + 2
    while True:
        runs = client.get(f"/tasks/{task['id']}/runs").json()["items"]
        if runs[0]["status"] == "completed" or time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    assert runs[0]["status"] == "completed"
    assert client.get(f"/tasks/{task['id']}").json()["task"]["status"] == "completed"
    assert runs[0]["backend"] == "hermes"
    assert runs[0]["retry_count"] == 0


def test_process_rejects_unknown_backend(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    client = TestClient(main.app)
    task = client.post("/tasks", json={"subject": "math"}).json()["task"]

    response = client.post(f"/tasks/{task['id']}/process?backend=unknown")
    assert response.status_code == 422


def test_problem_views_derive_lettered_option_labels_from_order():
    task = main.TaskRecord(subject="math")
    problem = Problem(
        content_format="oopsmark-v1",
        subject="math",
        question_type="单选题",
        problem_text="请选择。",
        options=["A. $x$", "B] $y$", "$z$", "$w$"],
    )

    detail = main._problem_view(task, problem)
    summary = main._problem_summary(task, problem)

    expected = [
        {"key": "A", "text": "$x$"},
        {"key": "B", "text": "$y$"},
        {"key": "C", "text": "$z$"},
        {"key": "D", "text": "$w$"},
    ]
    assert detail["options"] == expected
    assert summary["options"] == expected
