from __future__ import annotations

import json

import httpx
import pytest

from oopsnote.core import (
    AssetStore,
    RunStatus,
    RunStore,
    TaskCreateRequest,
    TaskRun,
    TaskStatus,
    TaskStore,
)
from oopsnote.mcp import ocr
from oopsnote.mcp import server
from oopsnote.mcp.ocr_contract import OCR_INSTRUCTION, normalize_ocr_result
from oopsnote.mcp.restricted import AI_TOOL_NAMES, managed_ocr_image


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "content_format": "oopsmark-v1",
                                "subject": "math",
                                "question_type": "填空题",
                                "printed_question_no": 6,
                                "printed_chapter": "函数",
                                "problem_text": "求 $1+1$。",
                                "options": [],
                                "has_diagram": False,
                                "student_response_status": "unanswered",
                                "student_response": "",
                                "uncertain_regions": [],
                                "confidence": 1,
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }


def test_restricted_surface_contains_exactly_ocr_and_pipeline_tools():
    assert set(AI_TOOL_NAMES) == {
        "ocr_image",
        "get_task",
        "get_asset_path",
        "list_tags",
        "create_tag",
        "report_task_stage",
        "submit_solution_candidate",
        "finalize_task",
        "fail_task",
    }


def test_ocr_image_reads_local_config_and_returns_object(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    image = storage / "assets" / "question.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"not-a-real-png-but-the-provider-is-mocked")
    task_store = TaskStore(storage)
    asset_store = AssetStore(storage / "assets")
    task = task_store.create(TaskCreateRequest(subject="math", asset_path="/assets/question.png"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    monkeypatch.setattr(server, "TASK_STORE", task_store)
    monkeypatch.setattr(server, "ASSET_STORE", asset_store)
    run_store = RunStore(storage / "runs")
    run_store._write(TaskRun(id="run-1", task_id=task.id, status=RunStatus.RUNNING))
    monkeypatch.setattr(server, "RUN_STORE", run_store)
    config = tmp_path / "extensions.json"
    config.write_text(
        json.dumps(
            {
                "ocr_image": {
                    "dashscope_api_key": "local-test-key",
                    "model": "test-vision-model",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OOPSNOTE_OCR_CONFIG", str(config))
    captured = {}

    class FakeClient:
        def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    def fake_client():
        return FakeClient()

    monkeypatch.setattr(ocr, "_ocr_client", fake_client)

    result = ocr.ocr_image(task.id, "run-1")

    assert result["content_format"] == "oopsmark-v1"
    assert result["problem_text"] == "求 $1+1$。"
    assert result["printed_question_no"] == 6
    assert result["printed_chapter"] == "函数"
    observed = task_store.get(task.id)
    assert observed.ocr_context is not None
    assert observed.ocr_context.printed_question_no == 6
    assert observed.ocr_context.printed_chapter == "函数"
    artifact = run_store.get("run-1").artifacts[0]
    assert artifact.kind == "ocr"
    assert json.loads(artifact.raw_output)["printed_question_no"] == 6
    assert artifact.parsed_output == result
    assert captured["url"] == ocr.OCR_ENDPOINT
    assert captured["json"]["model"] == "test-vision-model"
    assert captured["headers"]["Authorization"] == "Bearer local-test-key"
    assert "local-test-key" not in json.dumps(captured["json"], ensure_ascii=False)
    assert "review_reason" in OCR_INSTRUCTION
    assert "independent top-level question" in OCR_INSTRUCTION

    cached = ocr.ocr_image(task.id, "run-1")
    assert cached == result


def test_cancelled_run_does_not_attach_stale_ocr_context(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    image = storage / "assets" / "question.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    task_store = TaskStore(storage)
    task = task_store.create(TaskCreateRequest(asset_path="/assets/question.png"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    monkeypatch.setattr(server, "TASK_STORE", task_store)
    monkeypatch.setattr(server, "ASSET_STORE", AssetStore(storage / "assets"))
    run_store = RunStore(storage / "runs")
    run_store._write(TaskRun(id="run-1", task_id=task.id, status=RunStatus.RUNNING))
    monkeypatch.setattr(server, "RUN_STORE", run_store)

    def cancel_during_ocr(_image_path):
        task_store.mark_status(task.id, TaskStatus.CANCELLED)
        return {
            "content_format": "oopsmark-v1",
            "subject": "math",
            "question_type": "填空题",
            "printed_question_no": 6,
            "printed_chapter": "函数",
            "problem_text": "求 $1+1$。",
            "options": [],
            "has_diagram": False,
            "student_response_status": "unanswered",
            "student_response": "",
            "uncertain_regions": [],
            "confidence": 1,
        }

    monkeypatch.setattr(ocr, "_ocr_image_path", cancel_during_ocr)

    result = ocr.ocr_image(task.id, "run-1")

    assert result["printed_question_no"] == 6
    cancelled = task_store.get(task.id)
    assert cancelled.status == TaskStatus.CANCELLED
    assert cancelled.ocr_context is None
    assert run_store.get("run-1").artifacts[0].kind == "ocr"


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        (429, "ocr_rate_limit"),
        (503, "ocr_provider_unavailable"),
        (401, "ocr_provider_error"),
        ("timeout", "ocr_timeout"),
        ("network", "ocr_network_error"),
    ],
)
def test_ocr_provider_failures_have_stable_codes(
    tmp_path,
    monkeypatch,
    failure,
    expected_code,
):
    image = tmp_path / "question.png"
    image.write_bytes(b"image")
    request = httpx.Request("POST", ocr.OCR_ENDPOINT)

    class FailingClient:
        def post(self, *_args, **_kwargs):
            if failure == "timeout":
                raise httpx.ReadTimeout("slow", request=request)
            if failure == "network":
                raise httpx.ConnectError("offline", request=request)
            response = httpx.Response(failure, request=request)
            raise httpx.HTTPStatusError(
                f"HTTP {failure}",
                request=request,
                response=response,
            )

    monkeypatch.setattr(
        ocr,
        "_load_ocr_config",
        lambda: {"dashscope_api_key": "test", "model": "vision"},
    )
    monkeypatch.setattr(ocr, "_ocr_client", lambda: FailingClient())

    with pytest.raises(ocr.OcrProviderError) as captured:
        ocr._ocr_image_path(image)

    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    ("outcome", "expected_code", "review_reason"),
    [
        (ocr.OcrProviderError("ocr_timeout", "DashScope OCR timeout"), "ocr_timeout", None),
        (
            {
                "problem_text": "",
                "review_reason": "unreadable",
            },
            "ocr_unreadable",
            "unreadable",
        ),
    ],
)
def test_managed_ocr_failure_atomically_closes_the_active_task(
    tmp_path,
    monkeypatch,
    outcome,
    expected_code,
    review_reason,
):
    task_store = TaskStore(tmp_path / "storage")
    task = task_store.create(TaskCreateRequest(subject="math"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    monkeypatch.setattr(server, "TASK_STORE", task_store)

    def fake_ocr(_task_id, _run_id):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(ocr, "ocr_image", fake_ocr)

    if isinstance(outcome, Exception):
        with pytest.raises(ocr.OcrProviderError):
            managed_ocr_image(task.id, "run-1")
    else:
        assert managed_ocr_image(task.id, "run-1") == outcome

    failed = task_store.get(task.id)
    assert failed.status == TaskStatus.FAILED
    assert failed.active_run_id is None
    assert failed.last_error_code == expected_code
    assert failed.metadata.get("intake_review_reason") == review_reason


def test_ocr_contract_trims_following_top_level_question():
    result = normalize_ocr_result(
        {
            "content_format": "oopsmark-v1",
            "subject": "math",
            "question_type": "解答题",
            "problem_text": "21. 第一题\n\n（1）小问一\n（2）小问二\n\n22. 第二题",
            "options": [],
            "has_diagram": False,
            "student_response_status": "unanswered",
            "student_response": "",
            "uncertain_regions": [],
            "confidence": 1,
        },
        expected_question_no="21",
    )

    assert result["problem_text"] == "21. 第一题\n\n（1）小问一\n（2）小问二"
    assert result["review_reason"] == "multiple_questions"


def test_ocr_contract_accepts_only_explicit_bounded_printed_context():
    payload = {
        "content_format": "oopsmark-v1",
        "subject": "math",
        "question_type": "解答题",
        "printed_question_no": 12,
        "printed_chapter": "  函数与导数  ",
        "problem_text": "求函数的最值。",
        "options": [],
        "has_diagram": False,
        "student_response_status": "unanswered",
        "student_response": "",
        "uncertain_regions": [],
        "confidence": 1,
    }

    result = normalize_ocr_result(payload)

    assert result["printed_question_no"] == 12
    assert result["printed_chapter"] == "函数与导数"
    with pytest.raises(ValueError):
        normalize_ocr_result({**payload, "printed_question_no": 0})


def test_ocr_contract_allows_empty_text_only_for_an_unreadable_image():
    unreadable = {
        "content_format": "oopsmark-v1",
        "subject": "math",
        "question_type": "解答题",
        "problem_text": "",
        "options": [],
        "has_diagram": False,
        "student_response_status": "unknown",
        "student_response": "",
        "review_reason": "unreadable",
        "uncertain_regions": ["whole image"],
        "confidence": 0,
    }

    assert normalize_ocr_result(unreadable)["problem_text"] == ""
    with pytest.raises(ValueError, match="requires review_reason=unreadable"):
        normalize_ocr_result({**unreadable, "review_reason": None})


def test_ocr_contract_normalizes_subquestions_and_option_bodies():
    result = normalize_ocr_result(
        {
            "content_format": "oopsmark-v1",
            "subject": "math",
            "question_type": "单选题",
            "problem_text": "题干\n\n1. 第一问\n2. 第二问",
            "options": ["A. $x$", "B] $y$", "（C）$z$", "4、$w$"],
            "has_diagram": False,
            "student_response_status": "unanswered",
            "student_response": "",
            "uncertain_regions": [],
            "confidence": 1,
        }
    )

    assert result["problem_text"] == "题干\n\n（1）第一问\n（2）第二问"
    assert result["options"] == ["$x$", "$y$", "$z$", "$w$"]
    assert "omit printed labels" in OCR_INSTRUCTION


def test_ocr_contract_rejects_invalid_provider_shape():
    with pytest.raises(ValueError):
        normalize_ocr_result(
            {
                "content_format": "oopsmark-v1",
                "subject": "math",
                "question_type": "解答题",
                "problem_text": "1. 题目",
                "options": [],
                "has_diagram": False,
                "student_response_status": "unanswered",
                "student_response": "",
                "uncertain_regions": [],
                "confidence": 2,
            }
        )


def test_ocr_contract_requires_evidence_for_answered_status():
    with pytest.raises(ValueError, match="requires student_response"):
        normalize_ocr_result(
            {
                "content_format": "oopsmark-v1",
                "subject": "math",
                "question_type": "解答题",
                "problem_text": "求 $1+1$。",
                "options": [],
                "has_diagram": False,
                "student_response_status": "answered",
                "student_response": "",
                "uncertain_regions": [],
                "confidence": 1,
            }
        )


def test_ocr_and_asset_resolution_reject_wrong_run_and_unmanaged_paths(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    asset_store = AssetStore(storage / "assets")
    task_store = TaskStore(storage)
    managed = storage / "assets" / "managed.png"
    managed.write_bytes(b"image")
    task = task_store.create(TaskCreateRequest(asset_path="/assets/managed.png"))
    task_store.update(task.id, status=TaskStatus.PROCESSING, active_run_id="run-1")
    monkeypatch.setattr(server, "TASK_STORE", task_store)
    monkeypatch.setattr(server, "ASSET_STORE", asset_store)

    with pytest.raises(ValueError, match="not active"):
        server.get_asset_path(task.id, "wrong-run")
    with pytest.raises(ValueError, match="not active"):
        ocr.ocr_image(task.id, "wrong-run")

    task_store.update(task.id, asset_path="/assets/../secret.png")
    with pytest.raises(ValueError, match="outside"):
        server.get_asset_path(task.id, "run-1")
