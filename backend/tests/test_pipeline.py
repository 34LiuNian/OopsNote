"""Pipeline and API integration tests."""

import base64

from fastapi.testclient import TestClient

from app.clients import StubAIClient
from app.agents.pipeline import AgentPipeline, PipelineDependencies
from app.agents.stages import Archiver, HandwrittenExtractor, ProblemRebuilder, SolutionWriter, TaggingProfiler
from app.main import app
from app.models import TaskCreateRequest
from app.repository import ArchiveStore


def test_pipeline_single_problem_extraction():
    """Runs the pipeline once and validates the single-problem flow."""
    stub_client = StubAIClient(seed=123)
    rebuilder = ProblemRebuilder()
    extractor = HandwrittenExtractor(rebuilder=rebuilder)
    deps = PipelineDependencies(
        extractor=extractor,
        solution_writer=SolutionWriter(stub_client),
        tagger=TaggingProfiler(stub_client),
        archiver=Archiver(),
        archive_store=ArchiveStore(),
    )
    pipeline = AgentPipeline(deps)
    payload = TaskCreateRequest(
        image_url="https://example.com/problem.jpg",
        subject="math",
        mock_problem_count=2,
    )

    result = pipeline.run("task-1", payload)

    assert result.detection.action == "single"
    assert len(result.problems) == 1
    assert len(result.solutions) == 1
    assert len(result.tags) == 1


def test_fastapi_create_and_process_task():
    """Creates a task via API and checks completion fields."""
    client = TestClient(app)

    response = client.post(
        "/tasks",
        json={
            "image_url": "https://example.com/problem.jpg",
            "subject": "physics",
            "notes": "multi",
        },
    )
    assert response.status_code == 201
    data = response.json()
    task = data["task"]

    assert task["status"] == "completed"
    assert len(task["problems"]) >= 1
    assert len(task["solutions"]) == len(task["problems"])


def test_upload_endpoint_with_base64():
    """Uploads base64 content and verifies asset metadata."""
    client = TestClient(app)
    payload = base64.b64encode(b"unit-test-image").decode()

    response = client.post(
        "/upload",
        json={
            "image_base64": payload,
            "mime_type": "image/png",
            "filename": "test.png",
            "subject": "math",
        },
    )

    assert response.status_code == 201
    task = response.json()["task"]
    assert task["status"] == "completed"
    assert task["asset"]["source"] == "upload"
    assert task["asset"]["path"].endswith("test.png")


def test_end_to_end_upload_and_fetch_flow():
    """Exercises upload then fetch to validate persistence."""
    client = TestClient(app)
    payload = base64.b64encode(b"end-to-end-image").decode()

    create_response = client.post(
        "/upload",
        json={
            "image_base64": payload,
            "mime_type": "image/png",
            "filename": "e2e.png",
            "subject": "physics",
            "notes": "multi",
        },
    )

    assert create_response.status_code == 201
    created_task = create_response.json()["task"]
    assert created_task["status"] == "completed"
    assert created_task["detection"]["action"] == "single"
    assert len(created_task["problems"]) == 1
    assert len(created_task["solutions"]) == 1
    assert created_task["archive_record"]["stored_problem_ids"]

    task_id = created_task["id"]
    fetch_response = client.get(f"/tasks/{task_id}")
    assert fetch_response.status_code == 200
    fetched_task = fetch_response.json()["task"]
    assert fetched_task["id"] == task_id
    assert fetched_task["status"] == "completed"
    assert fetched_task["detection"]["action"] == "single"
    assert fetched_task["archive_record"]["task_id"] == task_id


def test_problems_library_endpoint_flattens_problems():
    """Ensures the library endpoint returns flattened problems."""
    client = TestClient(app)

    # Create one math and one physics task so that the library view has content.
    payload = base64.b64encode(b"library-image").decode()

    for subject in ["math", "physics"]:
        response = client.post(
            "/upload",
            json={
                "image_base64": payload,
                "mime_type": "image/png",
                "filename": f"lib-{subject}.png",
                "subject": subject,
                "notes": "multi",
            },
        )
        assert response.status_code == 201

    # Query all problems
    all_response = client.get("/problems")
    assert all_response.status_code == 200
    body = all_response.json()
    items = body["items"]
    # We created 2 tasks * 1 problem each = 2 problems
    assert len(items) >= 2

    # Filter by subject
    math_response = client.get("/problems", params={"subject": "math"})
    assert math_response.status_code == 200
    math_items = math_response.json()["items"]
    assert all(item["subject"] == "math" for item in math_items)