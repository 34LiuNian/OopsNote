from __future__ import annotations

import base64
import hashlib
import time
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from oopsnote.ai import ManagedAiRunner
from oopsnote.ai.diagram_renderer import TikzRenderBundle, TikzRenderClient
from oopsnote.api import auth, main
from oopsnote.core import (
    AssetStore,
    BatchProcessJobStore,
    BatchSegment,
    BatchSegmentPart,
    BatchSessionRecord,
    BatchSessionStore,
    DiagramCandidate,
    DiagramItem,
    DiagramStatus,
    Problem,
    ProblemMergeStore,
    RunArtifact,
    RunStatus,
    RunStore,
    TagStore,
    TaskCreateRequest,
    TaskRecord,
    TaskRun,
    TaskStage,
    TaskStatus,
    TaskStore,
)


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


class RecordingStudyRunner:
    def __init__(self, task_store: TaskStore) -> None:
        self.task_store = task_store
        self.submitted: list[str] = []

    def submit(self, task_id: str) -> TaskRun:
        self.submitted.append(task_id)
        run = TaskRun(task_id=task_id)
        self.task_store.update(task_id, status=TaskStatus.PROCESSING, active_run_id=run.id)
        return run


class StubManagedRunner(ManagedAiRunner):
    backend_name = "langchain"

    def run(self, task_id: str, run_id: str) -> None:
        del task_id, run_id


def png_base64(color: str = "white") -> str:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_search_rejects_invalid_since_query_at_http_boundary():
    response = TestClient(main.app).get("/search", params={"since": "not-a-date"})

    assert response.status_code == 422


def test_diagram_settings_hide_without_deleting_and_candidate_delete_rolls_back(
    tmp_path, monkeypatch
):
    task_store = TaskStore(tmp_path / "tasks")
    asset_store = AssetStore(tmp_path / "assets")
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "ASSET_STORE", asset_store)
    source_path = asset_store.save_bytes(b"source", "source.png", "source")
    task = task_store.create(TaskCreateRequest(subject="math", asset_path=source_path))
    task_store.update(
        task.id,
        status=TaskStatus.COMPLETED,
        problem=Problem(problem_text="有图", has_diagram=True),
    )
    first = DiagramCandidate(ordinal=1, tikz_source=r"\draw (0,0)--(1,0);")
    second = DiagramCandidate(
        ordinal=2,
        parent_candidate_id=first.id,
        tikz_source=r"\draw[->] (0,0)--(1,0);",
    )
    item = DiagramItem(
        source_asset_path=source_path,
        status=DiagramStatus.READY_TIKZ,
        selected_candidate_id=second.id,
        candidates=[first, second],
    )
    task_store.add_diagram_item(task.id, item)
    client = TestClient(main.app)

    task_store.update_diagram_item(task.id, item.id, active_run_id="diagram-run-1")
    blocked = client.delete(f"/tasks/{task.id}/diagrams/{item.id}/candidates/{second.id}")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "diagram_run_active"
    assert len(task_store.get(task.id).diagram_items[0].candidates) == 2
    task_store.update_diagram_item(
        task.id,
        item.id,
        expected_active_run_id="diagram-run-1",
        active_run_id=None,
    )

    hidden = client.patch(f"/tasks/{task.id}/problem/diagram", json={"enabled": False})
    assert hidden.status_code == 200
    hidden_problem = hidden.json()["task"]["problem"]
    assert hidden_problem["diagram_enabled"] is False
    assert hidden_problem["diagram_kind"] is None
    assert len(hidden_problem["diagram_items"][0]["candidates"]) == 2
    assert hidden.json()["task"]["revision_count"] is None

    shown = client.patch(
        f"/tasks/{task.id}/problem/diagram",
        json={"enabled": True, "kind": "tikz"},
    )
    assert shown.status_code == 200
    assert shown.json()["task"]["problem"]["diagram_kind"] == "tikz"

    removed = client.delete(f"/tasks/{task.id}/diagrams/{item.id}/candidates/{second.id}")
    assert removed.status_code == 200
    removed_item = removed.json()["task"]["problem"]["diagram_items"][0]
    assert removed_item["selected_candidate_id"] == first.id
    assert [candidate["ordinal"] for candidate in removed_item["candidates"]] == [1]

    removed = client.delete(f"/tasks/{task.id}/diagrams/{item.id}/candidates/{first.id}")
    assert removed.status_code == 200
    empty_item = removed.json()["task"]["problem"]["diagram_items"][0]
    assert empty_item["selected_candidate_id"] is None
    assert empty_item["status"] == "detected"
    assert removed.json()["task"]["problem"]["diagram_kind"] is None


def test_rerender_backfills_authoritative_tikz_size_metrics(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "tasks")
    asset_store = AssetStore(tmp_path / "assets")
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "ASSET_STORE", asset_store)
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(
        task.id,
        status=TaskStatus.COMPLETED,
        problem=Problem(problem_text="旧题图", has_diagram=True),
    )
    legacy = DiagramCandidate(
        ordinal=1,
        tikz_source=r"\begin{tikzpicture}\draw (0,0)--(1,0);\end{tikzpicture}",
        pdf_path="/assets/legacy.pdf",
    )
    item = DiagramItem(
        status=DiagramStatus.READY_TIKZ,
        selected_candidate_id=legacy.id,
        candidates=[legacy],
    )
    task_store.add_diagram_item(task.id, item)

    def render_bundle(renderer: TikzRenderClient, source: str) -> TikzRenderBundle:
        assert source == legacy.tikz_source
        return TikzRenderBundle(
            svg_path=renderer.asset_store.save_bytes(b"<svg/>", "diagram.svg", "rerender"),
            pdf_path=renderer.asset_store.save_bytes(b"pdf", "diagram.pdf", "rerender"),
            png_path=renderer.asset_store.save_bytes(b"png", "diagram.png", "rerender"),
            renderer_profile_version="tikz-xelatex-v6-test",
            base_font_size_pt=10,
            canvas_width_em=12.5,
            canvas_height_em=7.25,
        )

    monkeypatch.setattr(TikzRenderClient, "render", render_bundle)

    response = TestClient(main.app).post(f"/tasks/{task.id}/problem/diagram")

    assert response.status_code == 200
    problem = response.json()["task"]["problem"]
    assert problem["diagram_base_font_size_pt"] == 10
    assert problem["diagram_canvas_width_em"] == 12.5
    assert problem["diagram_canvas_height_em"] == 7.25
    repaired = task_store.get(task.id).diagram_items[0].candidates[0]
    assert repaired.renderer_profile_version == "tikz-xelatex-v6-test"
    assert repaired.base_font_size_pt == 10
    assert repaired.canvas_width_em == 12.5
    assert repaired.canvas_height_em == 7.25


def test_problem_view_migrates_legacy_svg_dimensions_for_web_sizing(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "tasks")
    asset_store = AssetStore(tmp_path / "assets")
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "ASSET_STORE", asset_store)
    task = task_store.create(TaskCreateRequest(subject="physics"))
    task_store.update(
        task.id,
        status=TaskStatus.COMPLETED,
        problem=Problem(problem_text="旧题图", has_diagram=True),
    )
    svg_path = asset_store.save_bytes(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="329.48pt" height="156.73pt" />',
        "diagram.svg",
        "legacy-web-sizing",
    )
    candidate = DiagramCandidate(
        ordinal=1,
        tikz_source=r"\draw (0,0)--(1,0);",
        svg_path=svg_path,
        renderer_profile_version="tikz-xelatex-v4-poppler",
    )
    item = DiagramItem.model_validate(
        {
            "status": DiagramStatus.READY_TIKZ,
            "selected_candidate_id": candidate.id,
            "candidates": [candidate],
            "scale_percent": 200,
        }
    )
    task_store.add_diagram_item(task.id, item)

    view = main._problem_view(task_store.get(task.id), task_store.get(task.id).problem)

    base_font_pdf_pt = 10 * 72 / 72.27
    assert view["diagram_base_font_size_pt"] == 10
    assert view["diagram_canvas_width_em"] == pytest.approx(329.48 / base_font_pdf_pt)
    assert view["diagram_canvas_height_em"] == pytest.approx(156.73 / base_font_pdf_pt)
    assert view["diagram_scale_adjustment_percent"] == 100


def test_problem_view_keeps_materialized_image_crop_out_of_the_display_projection():
    item = DiagramItem(
        source_asset_path="/assets/source.png",
        source_region={"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.5},
        fallback_image_path="/assets/diagram-crop.png",
        status=DiagramStatus.READY_IMAGE,
    )
    task = TaskRecord(
        status=TaskStatus.COMPLETED,
        problem=Problem(problem_text="有裁剪题图", has_diagram=True),
        diagram_items=[item],
    )

    view = main._problem_view(task, task.problem)

    assert view["diagram_image_path"] == "/assets/diagram-crop.png"
    assert "diagram_image_crop" not in view
    assert view["diagram_items"][0]["source_asset_path"] == "/assets/source.png"
    assert view["diagram_items"][0]["source_region"] == {
        "x": 0.2,
        "y": 0.3,
        "width": 0.4,
        "height": 0.5,
    }


def test_problem_view_does_not_project_legacy_diagram_flag_as_renderable_diagram():
    task = TaskRecord(
        status=TaskStatus.COMPLETED,
        problem=Problem(problem_text="历史图形标记", has_diagram=True),
    )

    view = main._problem_view(task, task.problem)

    assert view["has_diagram"] is True
    assert view["diagram_detected"] is False
    assert view["diagram_enabled"] is False
    assert view["diagram_kind"] is None


def test_problem_created_at_normalizes_legacy_naive_timestamp():
    problem = Problem(created_at="2026-08-07T12:00:00")

    assert problem.created_at.tzinfo is not None
    assert problem.created_at.utcoffset().total_seconds() == 0


def test_run_view_exposes_evidence_index_without_model_output():
    run = TaskRun(
        task_id="task-1",
        artifacts=[
            RunArtifact(
                stage=TaskStage.OCR,
                kind="ocr",
                raw_output="provider-only-output",
                parsed_output={"problem_text": "normalized"},
            )
        ],
    )

    view = main._run_view(run)

    assert view["evidence"]["artifacts"][0]["kind"] == "ocr"
    assert view["evidence"]["validation_error_count"] == 0
    assert "provider-only-output" not in str(view)


def test_failed_task_view_prefers_terminal_error_over_stale_stage_message(tmp_path, monkeypatch):
    task_store = TaskStore(tmp_path / "tasks")
    run_store = RunStore(tmp_path / "runs")
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", run_store)

    task = task_store.create(TaskCreateRequest(subject="math"))
    run = run_store.create(task.id, backend="langchain")
    task_store.update(
        task.id,
        status=TaskStatus.FAILED,
        stage=TaskStage.STARTING,
        stage_message="LangChain provider started",
        active_run_id=None,
        last_error="供应商返回 503",
        last_error_code="provider_unavailable",
    )
    run_store.finish(
        run.id,
        RunStatus.FAILED,
        error_code="provider_unavailable",
        error_message="供应商返回 503",
    )

    view = main._task_view(task_store.get(task.id))
    summary = main._task_summary(task_store.get(task.id))

    assert view["stage_message"] == "供应商侧请求失败：供应商返回 503"
    assert summary["stage_message"] == "供应商侧请求失败：供应商返回 503"


def test_explicit_local_auth_mode_bypasses_authentication_for_application_routes():
    with patch.dict(
        "os.environ",
        {"OOPSNOTE_AUTH_MODE": "local"},
        clear=False,
    ):
        response = TestClient(main.app).get("/tasks")

    assert response.status_code == 200


def test_health_reports_explicit_local_auth_mode():
    with patch.dict("os.environ", {"OOPSNOTE_AUTH_MODE": "local"}, clear=False):
        response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["auth"]["mode"] == "local"


def test_asset_route_serves_only_one_file_from_the_active_asset_root(tmp_path, monkeypatch):
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    (asset_root / "owned.png").write_bytes(b"owned")
    (tmp_path / "secret.txt").write_bytes(b"secret")
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(asset_root))

    with patch.dict("os.environ", {"OOPSNOTE_AUTH_MODE": "local"}, clear=False):
        client = TestClient(main.app)
        served = client.get("/assets/owned.png")
        missing = client.get("/assets/missing.png")
        traversal = client.get("/assets/../secret.txt")

    assert served.status_code == 200
    assert served.content == b"owned"
    assert missing.status_code == 404
    assert traversal.status_code == 404


def test_auth_config_rejects_unknown_mode():
    with (
        patch.dict("os.environ", {"OOPSNOTE_AUTH_MODE": "bypass"}, clear=False),
        pytest.raises(RuntimeError),
    ):
        auth.auth_config_from_env()


def test_unauthenticated_request_is_rejected_by_better_auth_default(monkeypatch):
    monkeypatch.delenv("OOPSNOTE_AUTH_MODE", raising=False)
    monkeypatch.setenv("OOPSNOTE_BFF_HMAC_SECRET", "x" * 64)
    # 未显式配置时默认模式即 better-auth：无内部身份签名的一律拒绝。
    response = TestClient(main.app).get("/tasks")
    assert response.status_code == 401


def test_batch_projection_preserves_admission_failure_for_pending_task(monkeypatch):
    task = TaskRecord(
        id="task-1",
        status=TaskStatus.PENDING,
        asset_path="/assets/selection.png",
    )

    class StubTaskStore:
        def get(self, task_id: str) -> TaskRecord:
            assert task_id == task.id
            return task

    monkeypatch.setattr(main, "TASK_STORE", StubTaskStore())
    record = BatchSessionRecord(
        file_hash="a" * 64,
        filename="questions.pdf",
        asset_path="/assets/questions.pdf",
        page_count=1,
        segments=[
            BatchSegment(
                parts=[BatchSegmentPart(page_index=0, x=0, y=0, width=1, height=1)],
                question_no=1,
                status="failed",
                task_id=task.id,
                error="selected LangChain channel has no credential",
            )
        ],
    )

    projected = main._sync_batch_session_tasks(record)

    assert projected.segments[0].status == "failed"
    assert projected.segments[0].error == "selected LangChain channel has no credential"


def test_batch_session_list_uses_one_task_snapshot_without_hashing_sources(monkeypatch):
    file_hashes = ("a" * 64, "b" * 64)
    tasks = [
        TaskRecord(
            id=f"task-{index}",
            status=TaskStatus.COMPLETED,
            metadata={
                "selection_snapshot": {
                    "source_file_hash": file_hash,
                    "segment_id": f"segment-{index}",
                    "question_no": index,
                    "parts": [
                        {
                            "page_index": 0,
                            "column_index": 0,
                            "x": 0,
                            "y": 0,
                            "width": 1,
                            "height": 1,
                            "order": 0,
                        }
                    ],
                }
            },
        )
        for index, file_hash in enumerate(file_hashes, start=1)
    ]
    records = [
        BatchSessionRecord(
            file_hash=file_hash,
            filename=f"questions-{index}.pdf",
            asset_path=f"/assets/questions-{index}.pdf",
            page_count=1,
            segments=[
                BatchSegment(
                    id=f"segment-{index}",
                    parts=[BatchSegmentPart(page_index=0, x=0, y=0, width=1, height=1)],
                    question_no=index,
                    status="processing",
                    task_id=f"task-{index}",
                )
            ],
        )
        for index, file_hash in enumerate(file_hashes, start=1)
    ]

    class StubTaskStore:
        list_calls = 0

        def list_all(self) -> list[TaskRecord]:
            self.list_calls += 1
            return tasks

        def get(self, task_id: str) -> TaskRecord:
            pytest.fail(f"list projection read task {task_id} outside its snapshot")

    class StubBatchSessionStore:
        def list_all(self) -> list[BatchSessionRecord]:
            return records

    class StubAssetStore:
        def exists(self, asset_path: str) -> bool:
            return asset_path.startswith("/assets/")

        def matches_sha256(self, asset_path: str, expected_sha256: str) -> bool:
            pytest.fail(f"history list hashed {asset_path} as {expected_sha256}")

    task_store = StubTaskStore()
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "BATCH_SESSION_STORE", StubBatchSessionStore())
    monkeypatch.setattr(main, "ASSET_STORE", StubAssetStore())

    response = TestClient(main.app).get("/batch-sessions")

    assert response.status_code == 200
    assert task_store.list_calls == 1
    assert [item["source_available"] for item in response.json()["items"]] == [True, True]
    assert [item["segments"][0]["status"] for item in response.json()["items"]] == [
        "completed",
        "completed",
    ]
    assert [len(item["submitted_selections"]) for item in response.json()["items"]] == [1, 1]


def test_cors_does_not_allow_an_arbitrary_origin():
    response = TestClient(main.app).options(
        "/settings/ai/profiles",
        headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "GET"},
    )

    assert response.headers.get("access-control-allow-origin") is None


def test_duplicate_candidates_merge_without_removing_source_task(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(base_dir=storage)
    monkeypatch.setattr(main, "STORAGE_DIR", storage)
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(storage / "runs"))
    monkeypatch.setattr(
        main, "PROBLEM_MERGE_STORE", ProblemMergeStore(storage / "settings" / "problem_merges.json")
    )

    current = task_store.create(TaskCreateRequest(subject="math"))
    candidate = task_store.create(TaskCreateRequest(subject="math"))
    current = task_store.set_problem(
        current.id,
        Problem(
            subject="math", problem_text="Find $x$.", options=["1", "2"], answer="A", explanation=""
        ),
    )
    candidate = task_store.set_problem(
        candidate.id,
        Problem(
            subject="math",
            problem_text=" Find   $x$. ",
            options=["1", "2"],
            answer="A",
            explanation="",
        ),
    )
    client = TestClient(main.app)

    listed = client.get(f"/tasks/{current.id}/duplicates")
    assert listed.status_code == 200
    assert [item["task"]["id"] for item in listed.json()["items"]] == [candidate.id]

    merged = client.post(
        f"/tasks/{current.id}/duplicates/{candidate.id}/merge",
        json={"direction": "into_current"},
    )
    assert merged.status_code == 200
    assert task_store.get(candidate.id).problem is not None
    detail = client.get(f"/tasks/{candidate.id}").json()["task"]
    assert detail["merged_into"]["task_id"] == current.id
    assert client.get(f"/tasks/{current.id}/duplicates").json() == {"items": []}


def test_variation_request_carries_parent_error_and_custom_constraints(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(base_dir=storage)
    runner = RecordingStudyRunner(task_store)
    monkeypatch.setattr(main, "STORAGE_DIR", storage)
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(storage / "runs"))
    monkeypatch.setattr(main, "_runner", lambda: runner)
    monkeypatch.setattr(main, "_configured_backend", lambda: "langchain")

    parent = task_store.create(TaskCreateRequest(subject="math"))
    parent = task_store.set_problem(
        parent.id,
        Problem(
            subject="math",
            problem_text="Find $x$.",
            answer="$1$",
            explanation="",
            error_hypothesis=["sign error"],
            knowledge_points=["linear equation"],
        ),
    )
    response = TestClient(main.app).post(
        f"/tasks/{parent.id}/variations",
        json={
            "direction": "add_distractors",
            "custom_request": "Use a real-world setting",
            "count": 2,
        },
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert len(runner.submitted) == 2
    created = task_store.get(runner.submitted[0])
    assert created.metadata["variation_request"]["parent_problem_id"] == parent.problem.id
    assert created.metadata["variation_request"]["error_hypotheses"] == ["sign error"]
    assert created.metadata["variation_request"]["custom_request"] == "Use a real-world setting"


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

    def render_bundle(renderer: TikzRenderClient, source: str) -> TikzRenderBundle:
        del source
        return TikzRenderBundle(
            svg_path=renderer.asset_store.save_bytes(
                b"<svg xmlns='http://www.w3.org/2000/svg'/>", "diagram.svg", "api-test"
            ),
            pdf_path=renderer.asset_store.save_bytes(
                b"%PDF-1.4\n%%EOF\n", "diagram.pdf", "api-test"
            ),
            png_path=renderer.asset_store.save_bytes(
                base64.b64decode(png_base64()), "diagram.png", "api-test"
            ),
            renderer_profile_version="test-v1",
            base_font_size_pt=10,
            canvas_width_em=12,
            canvas_height_em=8,
        )

    monkeypatch.setattr(TikzRenderClient, "render", render_bundle)
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
    main.TASK_STORE.update(
        task["id"],
        ocr_context={"printed_question_no": 6, "printed_chapter": "自动章节"},
    )
    detail = client.get(f"/tasks/{task['id']}").json()["task"]
    assert detail["problem"]["problem_id"] == stored.problem.id
    assert detail["problem"]["question_no"] == "6"
    assert detail["problem"]["chapter"] == "自动章节"
    assert detail["solution"]["answer"] == "$2$"
    assert detail["tag"]["problem_id"] == stored.problem.id

    edited = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "problem_text": "计算 $1+1$。",
            "question_no": "12",
            "chapter": "函数",
            "user_tags": ["重点"],
            "diagram_detected": True,
            "diagram_kind": "tikz",
            "diagram_tikz_source": "\\draw (0,0) -- (1,1);",
            "diagram_svg": "<svg></svg>",
            "diagram_render_status": "ready",
        },
    )
    assert edited.status_code == 200
    edited_task = edited.json()["task"]
    edited_problem = edited_task["problem"]
    assert edited_task["revision_count"] == 1
    assert edited_task["last_revised_at"]
    assert edited_problem["problem_text"] == "计算 $1+1$。"
    assert edited_problem["question_no"] == "12"
    assert edited_problem["chapter"] == "函数"
    assert edited_problem["user_tags"] == ["重点"]
    assert edited_problem["diagram_tikz_source"] == "\\draw (0,0) -- (1,1);"
    assert edited_problem["diagram_render_status"] == "ready_tikz"
    assert edited_problem["diagram_image_path"] is None
    assert edited_problem["diagram_placement"] == {"kind": "side", "side": "right"}
    assert edited_problem["diagram_scale_adjustment_percent"] == 100
    assert edited_problem["diagram_canvas_width_em"] == 12
    assert edited_problem["diagram_canvas_height_em"] == 8

    overridden_difficulty = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={"difficulty_coefficient_override": 0.73},
    )
    assert overridden_difficulty.status_code == 200
    assert (
        overridden_difficulty.json()["task"]["problem"]["difficulty_coefficient_override"] == 0.73
    )
    assert main.TASK_STORE.get(task["id"]).difficulty_coefficient_override == 0.73

    section_total = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={"section_question_count": 30},
    )
    assert section_total.status_code == 200
    section_problem = section_total.json()["task"]["problem"]
    assert section_problem["section_question_count"] == 30
    assert section_problem["difficulty_needs_review"] is False
    assert section_problem["difficulty_review_reason"] is None
    assert main.TASK_STORE.get(task["id"]).section_question_count == 30

    invalid_section_total = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={"section_question_count": 0},
    )
    assert invalid_section_total.status_code == 422
    assert main.TASK_STORE.get(task["id"]).section_question_count == 30

    invalid_difficulty = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={"difficulty_coefficient_override": 1.1},
    )
    assert invalid_difficulty.status_code == 422
    assert main.TASK_STORE.get(task["id"]).difficulty_coefficient_override == 0.73

    image_edited = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_tikz_source": "stale tikz must be cleared",
            "diagram_svg": "<svg>stale</svg>",
            "diagram_image_path": task["asset"]["path"],
            "diagram_placement": {"kind": "side", "side": "left"},
            "diagram_scale_adjustment_percent": 125,
        },
    )
    assert image_edited.status_code == 200
    image_task = image_edited.json()["task"]
    image_problem = image_task["problem"]
    assert image_task["revision_count"] == 4
    assert image_problem["diagram_kind"] == "image"
    assert image_problem["diagram_image_path"] == task["asset"]["path"]
    assert image_problem["diagram_tikz_source"] is None
    assert image_problem["diagram_svg"] is None
    assert image_problem["diagram_placement"] == {"kind": "side", "side": "left"}
    assert image_problem["diagram_scale_adjustment_percent"] == 125

    cropped = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_image_crop": {"x": 0.5, "y": 0, "width": 0.5, "height": 1},
            "diagram_image_tone": "auto",
        },
    )
    assert cropped.status_code == 200
    cropped_problem = cropped.json()["task"]["problem"]
    assert cropped_problem["diagram_image_path"].startswith("/assets/diagram-")
    assert cropped_problem["diagram_image_path"] != task["asset"]["path"]
    assert "diagram_image_crop" not in cropped_problem
    assert cropped_problem["diagram_items"][0]["source_region"] == {
        "x": 0.5,
        "y": 0.0,
        "width": 0.5,
        "height": 1.0,
    }
    assert cropped_problem["diagram_image_tone"] == "auto"
    with Image.open(main.ASSET_STORE.resolve(cropped_problem["diagram_image_path"])) as crop_image:
        assert crop_image.size == (2, 4)

    repeated_crop = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_image_crop": {"x": 0.5, "y": 0, "width": 0.5, "height": 1},
        },
    )
    assert repeated_crop.status_code == 200
    assert (
        repeated_crop.json()["task"]["problem"]["diagram_image_path"]
        == cropped_problem["diagram_image_path"]
    )
    assert (
        repeated_crop.json()["task"]["problem"]["diagram_items"][0]["source_region"]
        == cropped_problem["diagram_items"][0]["source_region"]
    )

    invalid_image = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_image_path": "/assets/another.png",
        },
    )
    assert invalid_image.status_code == 422

    invalid_crop = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_image_crop": {"x": 0.8, "y": 0, "width": 0.4, "height": 1},
        },
    )
    assert invalid_crop.status_code == 422

    invalid_tone = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_image_tone": "",
        },
    )
    assert invalid_tone.status_code == 422

    problem_summary = client.get("/problems").json()["items"][0]
    assert problem_summary["diagram_kind"] == "image"
    assert problem_summary["diagram_image_path"] == cropped_problem["diagram_image_path"]
    assert "diagram_image_crop" not in problem_summary
    assert problem_summary["diagram_items"][0]["source_region"] == {
        "x": 0.5,
        "y": 0.0,
        "width": 0.5,
        "height": 1.0,
    }

    full_image = client.patch(
        f"/tasks/{task['id']}/problem/override",
        json={
            "diagram_detected": True,
            "diagram_kind": "image",
            "diagram_image_crop": None,
        },
    )
    assert full_image.status_code == 200
    full_image_problem = full_image.json()["task"]["problem"]
    assert full_image_problem["diagram_image_path"] == task["asset"]["path"]
    assert full_image_problem["diagram_items"][0]["source_region"] is None
    assert "diagram_image_crop" not in full_image_problem


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

    old_error = client.post("/tags", json={"dimension": "error", "value": "旧错因"}).json()[
        "items"
    ][0]
    source_custom = client.post("/tags", json={"dimension": "custom", "value": "待合并"}).json()[
        "items"
    ][0]
    target_custom = client.post("/tags", json={"dimension": "custom", "value": "目标标签"}).json()[
        "items"
    ][0]
    task = task_store.create(
        TaskCreateRequest(
            subject="math",
            metadata={"user_tags": ["待合并"]},
        )
    )
    task_store.set_problem(
        task.id,
        Problem(
            subject="math",
            problem_text="题目",
            error_hypothesis=["旧错因"],
        ),
    )

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
        headers={
            "x-oopsnote-filename": "mock.pdf",
            "x-oopsnote-page-count": "7",
            "content-type": "application/pdf",
        },
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
            "segments": [
                {
                    "id": "region-1",
                    "parts": [
                        {
                            "page_index": 3,
                            "column_index": 0,
                            "x": 0.1,
                            "y": 0.2,
                            "width": 0.3,
                            "height": 0.4,
                            "order": 0,
                        },
                        {
                            "page_index": 4,
                            "column_index": 0,
                            "x": 0.1,
                            "y": 0,
                            "width": 0.3,
                            "height": 0.25,
                            "order": 1,
                        },
                    ],
                }
            ],
        },
    )
    assert updated.status_code == 200

    renamed = client.patch(
        f"/batch-sessions/{digest}",
        json={
            "filename": "renamed.pdf",
            "expected_revision": updated.json()["session"]["revision"],
        },
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
    assert [part["page_index"] for part in restored["segments"][0]["parts"]] == [3, 4]
    assert restored["crop_rect"] == {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    assert restored["crop_confirmed"] is False
    assert restored["column_layout"] == {"column_count": 1, "overlap_ratio": 0.5}
    assert client.get("/batch-sessions").json()["items"][0]["file_hash"] == digest


def test_batch_source_integrity_failure_is_rejected_and_same_source_repairs_it(
    tmp_path,
    monkeypatch,
):
    storage = tmp_path / "storage"
    asset_store = AssetStore(base_dir=storage / "assets")
    monkeypatch.setattr(main, "ASSET_STORE", asset_store)
    monkeypatch.setattr(main, "TASK_STORE", TaskStore(storage / "tasks"))
    monkeypatch.setattr(
        main,
        "BATCH_SESSION_STORE",
        BatchSessionStore(storage / "settings" / "batch_sessions.json"),
    )
    client = TestClient(main.app)
    source = b"verified-batch-source"
    digest = hashlib.sha256(source).hexdigest()

    created = client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={"x-oopsnote-filename": "questions.pdf", "content-type": "application/pdf"},
    )
    assert created.status_code == 200
    asset_store.resolve(created.json()["session"]["asset_path"]).write_bytes(b"tampered")

    rejected = client.get(f"/batch-sessions/{digest}/source")

    assert rejected.status_code == 404
    assert rejected.json()["detail"]["code"] == "batch_source_unavailable"

    repaired = client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={"x-oopsnote-filename": "questions.pdf", "content-type": "application/pdf"},
    )
    assert repaired.status_code == 200
    restored = client.get(f"/batch-sessions/{digest}/source")
    assert restored.status_code == 200
    assert restored.content == source


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
    assert (
        client.put(
            f"/batch-sessions/{digest}/source",
            content=source,
            headers={"x-oopsnote-filename": "continuous.pdf", "content-type": "application/pdf"},
        ).status_code
        == 200
    )
    initial_session = client.get(f"/batch-sessions/{digest}").json()["session"]
    assert initial_session["source_available"] is True
    removed_source = client.delete(f"/batch-sessions/{digest}/source")
    assert removed_source.status_code == 200
    assert removed_source.json()["source_available"] is False
    missing_session = client.get(f"/batch-sessions/{digest}").json()["session"]
    assert missing_session["source_available"] is False
    unavailable_process = client.post(
        f"/batch-sessions/{digest}/process",
        json={"expected_revision": missing_session["revision"]},
    )
    assert unavailable_process.status_code == 409
    assert unavailable_process.json()["detail"]["code"] == "batch_source_unavailable"
    restored = client.put(
        f"/batch-sessions/{digest}/source",
        content=source,
        headers={
            "x-oopsnote-filename": "questions.pdf",
            "x-oopsnote-page-count": "1",
            "content-type": "application/pdf",
        },
    )
    assert restored.status_code == 200
    assert restored.json()["session"]["source_available"] is True
    updated = client.patch(
        f"/batch-sessions/{digest}",
        json={
            "expected_revision": 1,
            "page_count": 3,
            "crop_rect": {"x": 0.1, "y": 0.08, "width": 0.8, "height": 0.84},
            "crop_confirmed": True,
            "column_layout": {"column_count": 2, "overlap_ratio": 0.5},
            "segments": [
                {
                    "id": "selection-1",
                    "parts": [
                        {
                            "page_index": 0,
                            "column_index": 1,
                            "x": 0.2,
                            "y": 0.8,
                            "width": 0.5,
                            "height": 0.2,
                            "order": 0,
                        },
                        {
                            "page_index": 1,
                            "column_index": 0,
                            "x": 0.2,
                            "y": 0,
                            "width": 0.5,
                            "height": 1,
                            "order": 1,
                        },
                        {
                            "page_index": 2,
                            "column_index": 0,
                            "x": 0.2,
                            "y": 0,
                            "width": 0.5,
                            "height": 0.15,
                            "order": 2,
                        },
                    ],
                    "question_no": 1,
                    "status": "needs_review",
                    "review_reason": "multiple_questions",
                    "review_previous_status": "pending",
                }
            ],
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
        metadata={
            **task_store.get(task["id"]).metadata,
            "intake_review_reason": "multiple_questions",
        },
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
    assert (
        client.patch(
            f"/batch-sessions/{digest}",
            json={
                "segments": [linked_segment],
                "expected_revision": renamed.json()["session"]["revision"],
            },
        ).status_code
        == 200
    )
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
    assert (
        client.patch(
            f"/batch-sessions/{digest}",
            json={
                "segments": [resolved_segment],
                "expected_revision": auto_review_session["revision"],
            },
        ).status_code
        == 200
    )
    resolved = client.get(f"/batch-sessions/{digest}").json()["session"]["segments"][0]
    assert resolved["status"] == "completed"
    assert resolved["review_resolved"] is True

    deleted = client.delete(f"/batch-sessions/{digest}")
    assert deleted.status_code == 200
    assert deleted.json()["preserved_task_ids"] == [task["id"]]
    assert client.get(f"/batch-sessions/{digest}").status_code == 404
    retained = client.get(f"/tasks/{task['id']}").json()["task"]
    assert retained["trace"]["batch_session_available"] is False


def test_batch_delete_selected_parts_preserves_unselected_parts(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(storage / "assets"))
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", RunStore(storage / "runs"))
    monkeypatch.setattr(main, "TAG_STORE", TagStore(storage / "settings" / "tags.json"))
    monkeypatch.setattr(
        main,
        "BATCH_SESSION_STORE",
        BatchSessionStore(storage / "settings" / "batch_sessions.json"),
    )
    client = TestClient(main.app)
    source = b"selected-batch-delete"
    digest = hashlib.sha256(source).hexdigest()
    assert (
        client.put(
            f"/batch-sessions/{digest}/source",
            content=source,
            headers={"x-oopsnote-filename": "delete.pdf", "content-type": "application/pdf"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/batch-sessions/{digest}",
            json={
                "expected_revision": 0,
                "segments": [
                    {
                        "id": "pending-selection",
                        "parts": [{"page_index": 0, "x": 0, "y": 0, "width": 1, "height": 1}],
                        "status": "pending",
                    }
                ],
            },
        ).status_code
        == 200
    )
    task = task_store.create(
        TaskCreateRequest(
            subject="math",
            metadata={"selection_snapshot": {"source_file_hash": digest}},
        )
    )

    deleted_task = client.request(
        "DELETE",
        f"/batch-sessions/{digest}",
        json={"source": False, "selection_records": False, "tasks": True},
    )
    assert deleted_task.status_code == 200
    assert deleted_task.json()["tasks_deleted"] == 1
    assert client.get(f"/tasks/{task.id}").status_code == 404
    assert client.get(f"/batch-sessions/{digest}").status_code == 200

    deleted_remaining = client.request(
        "DELETE",
        f"/batch-sessions/{digest}",
        json={"source": True, "selection_records": True, "tasks": False},
    )
    assert deleted_remaining.status_code == 200
    assert deleted_remaining.json()["source_deleted"] is True
    assert client.get(f"/batch-sessions/{digest}").status_code == 404


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
    monkeypatch.setattr(
        main, "BATCH_PROCESS_JOB_STORE", BatchProcessJobStore(storage / "batch_jobs")
    )
    monkeypatch.setattr(main, "_runner", lambda: runner)
    client = TestClient(main.app)

    document = pymupdf.open()
    page = document.new_page(width=100, height=100)
    page.draw_rect(page.rect, color=(0, 0, 0), fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(0, 0, 50, 50), color=(1, 0, 0), fill=(1, 0, 0))
    source = document.tobytes()
    document.close()
    digest = hashlib.sha256(source).hexdigest()
    assert (
        client.put(
            f"/batch-sessions/{digest}/source",
            content=source,
            headers={
                "x-oopsnote-filename": "questions.pdf",
                "x-oopsnote-page-count": "1",
                "content-type": "application/pdf",
            },
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/batch-sessions/{digest}",
            json={
                "expected_revision": 0,
                "page_count": 1,
                "crop_confirmed": True,
                "segments": [
                    {
                        "id": "segment-1",
                        "parts": [
                            {
                                "page_index": 0,
                                "x": 0,
                                "y": 0,
                                "width": 0.5,
                                "height": 0.5,
                                "order": 0,
                            }
                        ],
                        "question_no": 1,
                        "status": "pending",
                    },
                    {
                        "id": "segment-2",
                        "parts": [
                            {
                                "page_index": 0,
                                "x": 0.5,
                                "y": 0.5,
                                "width": 0.5,
                                "height": 0.5,
                                "order": 0,
                            }
                        ],
                        "question_no": 2,
                        "status": "pending",
                    },
                ],
            },
        ).status_code
        == 200
    )

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
    assert all(task.metadata["selection_snapshot"]["schema_version"] == 1 for task in tasks)
    assert all(task.metadata["selection_snapshot"]["parts"] for task in tasks)
    assert {item["task_id"] for item in payload["session"]["submitted_selections"]} == {
        task.id for task in tasks
    }
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

    original_task_id = payload["session"]["segments"][0]["task_id"]
    task_store.update(original_task_id, status=TaskStatus.FAILED, active_run_id=None)
    assert client.delete(f"/tasks/{original_task_id}").status_code == 200
    stale_session = client.get(f"/batch-sessions/{digest}").json()["session"]
    stale_segment = next(
        segment for segment in stale_session["segments"] if segment["id"] == "segment-1"
    )
    assert stale_segment["status"] == "failed"
    assert stale_segment["error"] == "关联任务不存在"

    retried = client.post(
        f"/batch-sessions/{digest}/segments/segment-1/retry",
        json={"expected_revision": stale_session["revision"]},
    )
    assert retried.status_code == 200
    retry_payload = retried.json()
    assert retry_payload["requested"] == 1
    assert retry_payload["created"] == 1
    assert retry_payload["queued"] == 1
    recreated_segment = next(
        segment for segment in retry_payload["session"]["segments"] if segment["id"] == "segment-1"
    )
    assert recreated_segment["task_id"] != original_task_id
    assert task_store.get(recreated_segment["task_id"]).status == TaskStatus.PROCESSING
    assert len(runner.submitted) == 3


def test_batch_session_rejects_invalid_segment_pages_before_persistence(tmp_path, monkeypatch):
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
    monkeypatch.setattr(
        main, "BATCH_PROCESS_JOB_STORE", BatchProcessJobStore(storage / "batch_jobs")
    )
    client = TestClient(main.app)
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    digest = hashlib.sha256(image).hexdigest()
    assert (
        client.put(
            f"/batch-sessions/{digest}/source",
            content=image,
            headers={
                "x-oopsnote-filename": "question.png",
                "x-oopsnote-page-count": "1",
                "content-type": "image/png",
            },
        ).status_code
        == 200
    )
    invalid_patch = client.patch(
        f"/batch-sessions/{digest}",
        json={
            "expected_revision": 0,
            "page_count": 1,
            "crop_confirmed": True,
            "segments": [
                {
                    "id": "bad-page",
                    "parts": [
                        {"page_index": 1, "x": 0, "y": 0, "width": 1, "height": 1, "order": 0}
                    ],
                    "question_no": 1,
                    "status": "pending",
                }
            ],
        },
    )

    assert invalid_patch.status_code == 422
    detail = invalid_patch.json()["detail"]
    assert detail["category"] == "request"
    assert detail["code"] == "request_invalid"
    assert detail["scope"] == "batch"
    assert "unavailable page" in detail["message"]
    persisted = client.get(f"/batch-sessions/{digest}").json()["session"]
    assert persisted["revision"] == 0
    assert persisted["segments"] == []
    assert task_store.list_all() == []


def test_batch_process_marks_invalid_question_numbers_for_review_and_queues_valid_segments(
    tmp_path, monkeypatch
):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    runner = RecordingBatchRunner(task_store)
    monkeypatch.setattr(main, "ASSET_STORE", AssetStore(storage / "assets"))
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "TAG_STORE", TagStore(storage / "settings" / "tags.json"))
    monkeypatch.setattr(
        main, "BATCH_SESSION_STORE", BatchSessionStore(storage / "settings" / "batch_sessions.json")
    )
    monkeypatch.setattr(
        main, "BATCH_PROCESS_JOB_STORE", BatchProcessJobStore(storage / "batch_jobs")
    )
    monkeypatch.setattr(main, "_runner", lambda: runner)
    client = TestClient(main.app)
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    digest = hashlib.sha256(image).hexdigest()
    assert (
        client.put(
            f"/batch-sessions/{digest}/source",
            content=image,
            headers={
                "x-oopsnote-filename": "question.png",
                "x-oopsnote-page-count": "1",
                "content-type": "image/png",
            },
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/batch-sessions/{digest}",
            json={
                "expected_revision": 0,
                "page_count": 1,
                "crop_confirmed": True,
                "segments": [
                    {
                        "id": "missing",
                        "parts": [{"page_index": 0, "x": 0, "y": 0, "width": 0.5, "height": 1}],
                        "question_no": None,
                    },
                    {
                        "id": "valid",
                        "parts": [{"page_index": 0, "x": 0.5, "y": 0, "width": 0.5, "height": 1}],
                        "question_no": 2,
                    },
                ],
            },
        ).status_code
        == 200
    )

    processed = client.post(f"/batch-sessions/{digest}/process", json={"expected_revision": 1})

    assert processed.status_code == 200
    payload = processed.json()
    assert payload["requested"] == 2
    assert payload["needs_review"] == 1
    assert payload["queued"] == 1
    assert {item["status"] for item in payload["items"]} == {"needs_review", "processing"}
    reviewed = next(
        segment for segment in payload["session"]["segments"] if segment["id"] == "missing"
    )
    assert reviewed["status"] == "needs_review"
    assert reviewed["review_reason"] == "other"
    assert reviewed["task_id"] is None
    assert len(task_store.list_all()) == 1


def test_process_endpoint_creates_observable_run(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    task_store = TaskStore(storage)
    run_store = RunStore(storage / "runs")
    runner = StubManagedRunner(
        project_root=tmp_path,
        task_store=task_store,
        run_store=run_store,
    )
    monkeypatch.setattr(main, "STORAGE_DIR", storage)
    monkeypatch.setattr(main, "TASK_STORE", task_store)
    monkeypatch.setattr(main, "RUN_STORE", run_store)
    monkeypatch.setattr(main, "_runner", lambda: runner)

    def fake_run(task_id, run_id):
        task_store.update(task_id, status=TaskStatus.COMPLETED, active_run_id=None)
        run_store.finish(run_id, RunStatus.COMPLETED, exit_code=0)

    monkeypatch.setattr(runner, "run", fake_run)
    client = TestClient(main.app)
    task = client.post("/tasks", json={"subject": "math"}).json()["task"]

    response = client.post(f"/tasks/{task['id']}/process")
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
    assert runs[0]["backend"] == runner.backend_name
    assert runs[0]["retry_count"] == 0


def test_process_endpoint_does_not_publish_task_backend_selection():
    parameters = main.app.openapi()["paths"]["/tasks/{task_id}/process"]["post"].get(
        "parameters", []
    )
    assert "backend" not in {parameter["name"] for parameter in parameters}


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
