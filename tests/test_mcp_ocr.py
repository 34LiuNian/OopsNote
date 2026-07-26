from __future__ import annotations

import json

import pytest

from oopsnote.core import AssetStore, TaskCreateRequest, TaskStatus, TaskStore
from oopsnote.mcp import ocr
from oopsnote.mcp import server
from oopsnote.mcp.ocr_contract import OCR_INSTRUCTION, normalize_ocr_result
from oopsnote.mcp.restricted import AI_TOOL_NAMES


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
                                "problem_text": "求 $1+1$。",
                                "options": [],
                                "has_diagram": False,
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
    assert captured["url"] == ocr.OCR_ENDPOINT
    assert captured["json"]["model"] == "test-vision-model"
    assert captured["headers"]["Authorization"] == "Bearer local-test-key"
    assert "local-test-key" not in json.dumps(captured["json"], ensure_ascii=False)
    assert "review_reason" in OCR_INSTRUCTION
    assert "independent top-level question" in OCR_INSTRUCTION

    cached = ocr.ocr_image(task.id, "run-1")
    assert cached == result


def test_ocr_contract_trims_following_top_level_question():
    result = normalize_ocr_result(
        {
            "content_format": "oopsmark-v1",
            "subject": "math",
            "question_type": "解答题",
            "problem_text": "21. 第一题\n\n（1）小问一\n（2）小问二\n\n22. 第二题",
            "options": [],
            "has_diagram": False,
            "uncertain_regions": [],
            "confidence": 1,
        },
        expected_question_no="21",
    )

    assert result["problem_text"] == "21. 第一题\n\n（1）小问一\n（2）小问二"
    assert result["review_reason"] == "multiple_questions"


def test_ocr_contract_normalizes_subquestions_and_option_bodies():
    result = normalize_ocr_result(
        {
            "content_format": "oopsmark-v1",
            "subject": "math",
            "question_type": "单选题",
            "problem_text": "题干\n\n1. 第一问\n2. 第二问",
            "options": ["A. $x$", "B] $y$", "（C）$z$", "4、$w$"],
            "has_diagram": False,
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
                "uncertain_regions": [],
                "confidence": 2,
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
