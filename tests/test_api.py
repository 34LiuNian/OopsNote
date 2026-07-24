from __future__ import annotations

import base64
import hashlib

from fastapi.testclient import TestClient

from oopsnote.api import main
from oopsnote.ai import HermesRunner
from oopsnote.core import AssetStore, BatchSessionStore, Problem, RunStatus, RunStore, TagStore, TaskStore, TaskStatus


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
        "image_base64": base64.b64encode(b"image-bytes").decode(),
        "knowledge_tags": ["函数"],
        "error_tags": ["定义域"],
        "user_tags": ["期中"],
    }
    created = client.post("/upload", json=payload)

    assert created.status_code == 200
    task = created.json()["task"]
    assert task["status"] == "pending"
    assert task["asset"]["path"].endswith("region.png")
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
        json={"problem_text": "计算 $1+1$。"},
    )
    assert edited.status_code == 200
    assert edited.json()["task"]["problem"]["problem_text"] == "计算 $1+1$。"


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
        headers={"x-oopsnote-filename": "mock.pdf", "content-type": "application/pdf"},
    )
    assert created.status_code == 200
    assert created.json()["session"]["asset_path"].endswith(f"batch-{digest}.pdf")

    updated = client.patch(
        f"/batch-sessions/{digest}",
        json={
            "page_count": 423,
            "subject": "数学",
            "notes": "目录后开始",
            "active_page": 4,
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

    duplicate = client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={"x-oopsnote-filename": "renamed.pdf", "content-type": "application/pdf"},
    )
    assert duplicate.status_code == 200
    restored = client.get(f"/batch-sessions/{digest}").json()["session"]
    assert restored["filename"] == "mock.pdf"
    assert restored["active_page"] == 4
    assert restored["segments"][0]["page_index"] == 3
    assert restored["segments"][0]["continuation"]["page_index"] == 4
    assert [part["page_index"] for part in restored["segments"][0]["parts"]] == [3, 4]
    assert restored["crop_rect"] == {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    assert restored["crop_confirmed"] is False
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
            "page_count": 3,
            "crop_rect": {"x": 0.1, "y": 0.08, "width": 0.8, "height": 0.84},
            "crop_confirmed": True,
            "segments": [{
                "id": "selection-1",
                "parts": [
                    {"page_index": 0, "x": 0.2, "y": 0.8, "width": 0.5, "height": 0.2, "order": 0},
                    {"page_index": 1, "x": 0.2, "y": 0, "width": 0.5, "height": 1, "order": 1},
                    {"page_index": 2, "x": 0.2, "y": 0, "width": 0.5, "height": 0.15, "order": 2},
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
    assert len(session["segments"][0]["parts"]) == 3
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
            "image_base64": base64.b64encode(b"cropped-question").decode(),
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
    linked_segment = {
        **session["segments"][0],
        "task_id": task["id"],
        "status": "processing",
        "review_reason": None,
        "review_previous_status": None,
        "review_resolved": False,
    }
    assert client.patch(f"/batch-sessions/{digest}", json={"segments": [linked_segment]}).status_code == 200
    auto_review = client.get(f"/batch-sessions/{digest}").json()["session"]["segments"][0]
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
    assert client.patch(f"/batch-sessions/{digest}", json={"segments": [resolved_segment]}).status_code == 200
    resolved = client.get(f"/batch-sessions/{digest}").json()["session"]["segments"][0]
    assert resolved["status"] == "completed"
    assert resolved["review_resolved"] is True

    deleted = client.delete(f"/batch-sessions/{digest}")
    assert deleted.status_code == 200
    assert deleted.json()["preserved_task_ids"] == [task["id"]]
    assert client.get(f"/batch-sessions/{digest}").status_code == 404
    retained = client.get(f"/tasks/{task['id']}").json()["task"]
    assert retained["trace"]["batch_session_available"] is False


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
    assert client.get(f"/tasks/{task['id']}").json()["task"]["status"] == "completed"
    runs = client.get(f"/tasks/{task['id']}/runs").json()["items"]
    assert runs[0]["status"] == "completed"
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
