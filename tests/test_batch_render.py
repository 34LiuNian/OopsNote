from __future__ import annotations

from io import BytesIO

import pymupdf
from PIL import Image

from oopsnote.core import BatchCropRect, BatchSegment, BatchSourceRenderer


def test_batch_renderer_crops_and_stacks_image_parts(tmp_path):
    source = Image.new("RGB", (100, 80), "white")
    for x in range(100):
        for y in range(80):
            source.putpixel((x, y), (x, y, 0))
    path = tmp_path / "source.png"
    source.save(path)
    source.close()
    segment = BatchSegment.model_validate({
        "id": "selection",
        "parts": [
            {"page_index": 0, "x": 0, "y": 0, "width": 0.5, "height": 0.5, "order": 0},
            {"page_index": 0, "x": 0.5, "y": 0.5, "width": 0.5, "height": 0.5, "order": 1},
        ],
        "question_no": 1,
    })

    with BatchSourceRenderer(path, "image/png") as renderer:
        payload = renderer.render_segment(segment, BatchCropRect())

    rendered = Image.open(BytesIO(payload))
    assert rendered.size == (50, 80)
    assert rendered.getpixel((10, 10)) == (10, 10, 0)
    assert rendered.getpixel((10, 50)) == (60, 50, 0)
    rendered.close()


def test_batch_renderer_uses_pdf_scale_and_uniform_crop(tmp_path):
    path = tmp_path / "source.pdf"
    document = pymupdf.open()
    page = document.new_page(width=100, height=80)
    page.draw_rect(page.rect, color=(0, 0, 0), fill=(1, 1, 1))
    page.draw_rect(pymupdf.Rect(25, 20, 75, 60), color=(1, 0, 0), fill=(1, 0, 0))
    document.save(path)
    document.close()
    segment = BatchSegment.model_validate({
        "id": "selection",
        "parts": [
            {"page_index": 0, "column_index": 1, "x": 0, "y": 0, "width": 1, "height": 1, "order": 0},
        ],
        "question_no": 1,
    })

    with BatchSourceRenderer(path, "application/pdf") as renderer:
        payload = renderer.render_segment(
            segment,
            BatchCropRect(x=0.25, y=0.25, width=0.5, height=0.5),
        )

    rendered = Image.open(BytesIO(payload))
    assert rendered.size == (75, 60)
    center = rendered.getpixel((rendered.width // 2, rendered.height // 2))
    assert center[0] > 240 and center[1] < 20 and center[2] < 20
    rendered.close()
