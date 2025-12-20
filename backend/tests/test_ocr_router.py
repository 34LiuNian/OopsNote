from __future__ import annotations

import base64
from datetime import datetime, timezone

from app.agents.extractor import LLMOcrExtractor, OcrExtractor, OcrRouter
from app.clients.stub import StubAIClient
from app.models import AssetMetadata, AssetSource, CropRegion, DetectionOutput, TaskCreateRequest


def _write_1x1_png(path) -> None:
    # 1x1 transparent PNG
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO0pJ8cAAAAASUVORK5CYII="
    )
    path.write_bytes(base64.b64decode(png_b64))


def test_ocr_router_falls_back_without_override(tmp_path) -> None:
    image_path = tmp_path / "a.png"
    _write_1x1_png(image_path)

    asset = AssetMetadata(
        asset_id="asset-1",
        source=AssetSource.UPLOAD,
        original_reference=None,
        path=str(image_path),
        mime_type="image/png",
        size_bytes=image_path.stat().st_size,
        created_at=datetime.now(timezone.utc),
    )

    payload = TaskCreateRequest(image_url="https://example.com/a.png", subject="math")
    detection = DetectionOutput(action="single", regions=[CropRegion(id="r1", bbox=[0.1, 0.1, 0.8, 0.8], label="full")])

    router = OcrRouter(
        base_extractor=OcrExtractor(),
        llm_extractor=LLMOcrExtractor(StubAIClient()),
        model_resolver=lambda _agent: None,
    )

    problems = router.run(payload, detection, asset)
    assert problems
    # Placeholder extractor produces this math prompt text.
    assert "直角三角形" in problems[0].problem_text


def test_ocr_router_uses_llm_when_override_present(tmp_path) -> None:
    image_path = tmp_path / "a.png"
    _write_1x1_png(image_path)

    asset = AssetMetadata(
        asset_id="asset-1",
        source=AssetSource.UPLOAD,
        original_reference=None,
        path=str(image_path),
        mime_type="image/png",
        size_bytes=image_path.stat().st_size,
        created_at=datetime.now(timezone.utc),
    )

    payload = TaskCreateRequest(image_url="https://example.com/a.png", subject="math")
    detection = DetectionOutput(action="single", regions=[CropRegion(id="r1", bbox=[0.1, 0.1, 0.8, 0.8], label="full")])

    router = OcrRouter(
        base_extractor=OcrExtractor(),
        llm_extractor=LLMOcrExtractor(StubAIClient()),
        model_resolver=lambda _agent: "any-vision-model",
    )

    problems = router.run(payload, detection, asset)
    assert problems
    assert "LLM-OCR" in problems[0].problem_text
