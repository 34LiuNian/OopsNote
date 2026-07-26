"""Server-side rendering of persisted batch-selection segments."""

from __future__ import annotations

import math
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from .models import BatchCropRect, BatchSegment


PDF_RENDER_SCALE = 1.5
PAGE_CACHE_SIZE = 4
MAX_SEGMENT_PIXELS = 80_000_000


def _js_round(value: float) -> int:
    """Match JavaScript Math.round for the non-negative image coordinates."""
    return math.floor(value + 0.5)


class BatchSourceRenderer:
    """Render page-local segment parts from one persisted PDF or image source."""

    def __init__(self, source_path: Path, mime_type: str) -> None:
        self.source_path = source_path
        self.mime_type = mime_type
        self._pdf: pymupdf.Document | None = None
        self._image: Image.Image | None = None
        self._pages: OrderedDict[int, Image.Image] = OrderedDict()

    def __enter__(self) -> "BatchSourceRenderer":
        if self.mime_type == "application/pdf" or self.source_path.suffix.lower() == ".pdf":
            self._pdf = pymupdf.open(self.source_path)
        else:
            opened = Image.open(self.source_path)
            self._image = ImageOps.exif_transpose(opened).convert("RGB")
            opened.close()
        return self

    def __exit__(self, *_args: object) -> None:
        for page in self._pages.values():
            page.close()
        self._pages.clear()
        if self._image is not None:
            self._image.close()
            self._image = None
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None

    @property
    def page_count(self) -> int:
        if self._pdf is not None:
            return self._pdf.page_count
        return 1 if self._image is not None else 0

    def render_segment(self, segment: BatchSegment, crop: BatchCropRect) -> bytes:
        parts: list[Image.Image] = []
        try:
            for part in sorted(segment.parts, key=lambda item: item.order):
                page = self._page(part.page_index)
                source_rect = (
                    crop.x + part.x * crop.width,
                    crop.y + part.y * crop.height,
                    part.width * crop.width,
                    part.height * crop.height,
                )
                left = _js_round(source_rect[0] * page.width)
                top = _js_round(source_rect[1] * page.height)
                width = max(1, _js_round(source_rect[2] * page.width))
                height = max(1, _js_round(source_rect[3] * page.height))
                output = Image.new("RGB", (width, height), "white")
                right = min(page.width, left + width)
                bottom = min(page.height, top + height)
                if right > left and bottom > top:
                    output.paste(page.crop((left, top, right, bottom)), (0, 0))
                parts.append(output)

            canvas_width = max(part.width for part in parts)
            canvas_height = sum(part.height for part in parts)
            if canvas_width * canvas_height > MAX_SEGMENT_PIXELS:
                raise ValueError(
                    f"Rendered segment exceeds {MAX_SEGMENT_PIXELS} pixels"
                )
            canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
            offset = 0
            for part in parts:
                canvas.paste(part, (0, offset))
                offset += part.height
            buffer = BytesIO()
            canvas.save(buffer, format="PNG")
            canvas.close()
            return buffer.getvalue()
        finally:
            for part in parts:
                part.close()

    def validate_segment(self, segment: BatchSegment, crop: BatchCropRect) -> None:
        """Validate every page reference and final canvas size without retaining output."""
        widths: list[int] = []
        heights: list[int] = []
        for part in sorted(segment.parts, key=lambda item: item.order):
            page = self._page(part.page_index)
            width = max(1, _js_round(part.width * crop.width * page.width))
            height = max(1, _js_round(part.height * crop.height * page.height))
            widths.append(width)
            heights.append(height)
        canvas_pixels = max(widths) * sum(heights)
        if canvas_pixels > MAX_SEGMENT_PIXELS:
            raise ValueError(f"Rendered segment exceeds {MAX_SEGMENT_PIXELS} pixels")

    def _page(self, page_index: int) -> Image.Image:
        if page_index < 0 or page_index >= self.page_count:
            raise ValueError(f"Batch segment references unavailable page {page_index + 1}")
        if self._image is not None:
            return self._image
        cached = self._pages.pop(page_index, None)
        if cached is not None:
            self._pages[page_index] = cached
            return cached
        if self._pdf is None:
            raise RuntimeError("Batch source renderer is not open")
        page = self._pdf.load_page(page_index)
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE),
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        rendered = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        self._pages[page_index] = rendered
        while len(self._pages) > PAGE_CACHE_SIZE:
            _, evicted = self._pages.popitem(last=False)
            evicted.close()
        return rendered


__all__ = ["BatchSourceRenderer", "PDF_RENDER_SCALE"]
