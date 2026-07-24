from __future__ import annotations

import json

from oopsnote.mcp import ocr
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
    image = tmp_path / "question.png"
    image.write_bytes(b"not-a-real-png-but-the-provider-is-mocked")
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

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(ocr.httpx, "post", fake_post)

    result = ocr.ocr_image(str(image))

    assert result["content_format"] == "oopsmark-v1"
    assert result["problem_text"] == "求 $1+1$。"
    assert captured["url"] == ocr.OCR_ENDPOINT
    assert captured["json"]["model"] == "test-vision-model"
    assert captured["headers"]["Authorization"] == "Bearer local-test-key"
    assert "local-test-key" not in json.dumps(captured["json"], ensure_ascii=False)
