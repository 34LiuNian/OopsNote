from __future__ import annotations

import base64
import hashlib

from fastapi.testclient import TestClient

from oopsnote.api import main
from oopsnote.ai import HermesRunner
from oopsnote.core import AssetStore, BatchSessionStore, RunStatus, RunStore, TagStore, TaskStore, TaskStatus


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

    tasks = client.get("/tasks").json()
    tags = client.get("/tags?query=函数").json()
    problems = client.get("/problems").json()

    assert tasks["items"][0]["id"] == task["id"]
    assert tags["items"][0]["value"] == "函数"
    assert problems == {"items": []}


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
            "segments": [{"id": "region-1", "page_index": 3, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}],
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
    assert client.get("/batch-sessions").json()["items"][0]["file_hash"] == digest


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
