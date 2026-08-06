from fastapi.testclient import TestClient

from oopsnote.ai.backends.hermes import HermesRunner
from oopsnote.api import main
from oopsnote.api.errors import ApiErrorCategory, category_for_error_code
from oopsnote.core import RunStore, TaskCreateRequest, TaskStatus, TaskStore


def test_persisted_error_codes_have_stable_api_categories() -> None:
    assert category_for_error_code("provider_unavailable") == ApiErrorCategory.MODEL_REQUEST
    assert category_for_error_code("renderer_failed") == ApiErrorCategory.TIKZ_COMPILE
    assert category_for_error_code(
        "renderer_failed",
        needs_review=True,
    ) == ApiErrorCategory.TIKZ_COMPILE
    assert category_for_error_code("runner_error") == ApiErrorCategory.INTERNAL
    assert category_for_error_code(None, needs_review=True) == ApiErrorCategory.HUMAN_REVIEW


def test_missing_task_error_contains_only_request_context(tmp_path, monkeypatch) -> None:
    task_store = TaskStore(tmp_path / "storage")
    monkeypatch.setattr(main, "TASK_STORE", task_store)

    response = TestClient(main.app).get("/tasks/missing-task")

    assert response.status_code == 404
    assert response.json() == {
        "detail": {
            "category": "request",
            "code": "task_not_found",
            "message": "题目不存在",
            "retryable": False,
            "scope": "task",
            "task_id": "missing-task",
        }
    }


def test_process_conflict_is_classified_by_lifecycle_owner(tmp_path, monkeypatch) -> None:
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    run_store = RunStore(storage / "runs")
    runner = HermesRunner(
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
    )
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING)
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", run_store)
    monkeypatch.setattr(main, "_runner_for", lambda _backend: runner)

    response = TestClient(main.app).post(f"/tasks/{task.id}/process")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail == {
        "category": "request",
        "code": "task_busy",
        "message": "题目已有正在运行的任务",
        "retryable": False,
        "scope": "task",
        "task_id": task.id,
    }
    assert "diagram_items" not in detail


def test_request_validation_error_keeps_submission_context() -> None:
    response = TestClient(main.app).post(
        "/tasks/task-for-validation/diagrams/reconstruct",
        json={"max_candidates": 99},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["category"] == "request"
    assert detail["code"] == "request_invalid"
    assert detail["scope"] == "diagram"
    assert detail["task_id"] == "task-for-validation"
    assert detail["details"]["issues"]
