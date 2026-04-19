from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request


class _FakeService:
    def run_debug_multipage_batch(self, payload, *, auto_process: bool = True) -> str:
        _ = payload
        _ = auto_process
        return "batch-demo-1"

    def get_debug_multipage_batch(self, batch_id: str):
        _ = batch_id
        return {
            "batch_id": "batch-demo-1",
            "status": "processing",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:10+00:00",
            "total_images": 1,
            "total_regions": 2,
            "total_tasks": 2,
            "completed_tasks": 1,
            "failed_tasks": 0,
            "cancelled_tasks": 0,
            "tasks": [
                {
                    "task_id": "t1",
                    "page_index": 1,
                    "region_index": 1,
                    "status": "completed",
                    "stage": "done",
                    "stage_message": "ok",
                }
            ],
            "warnings": [],
        }


def _build_request(path: str) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": path,
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


class DebugMultipageDemoRouteTests(unittest.TestCase):
    def test_demo_flag_disabled_returns_404(self) -> None:
        from app.api.debug_tasks import get_multipage_demo_batch

        request = _build_request("/debug/multipage/batches/b1")
        with patch.dict(os.environ, {"APP_ENABLE_MULTIPAGE_DEMO_API": "false"}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                get_multipage_demo_batch(request, "b1")

        self.assertEqual(ctx.exception.status_code, 404)

    def test_demo_upload_enabled_returns_batch_id(self) -> None:
        from app.api.debug_tasks import upload_multipage_demo
        from app.models import DebugMultiPageImageInput, DebugMultiPageUploadRequest

        payload = DebugMultiPageUploadRequest(
            images=[DebugMultiPageImageInput(image_base64="Zm9v", filename="a.png")],
            subject="math",
        )
        request = _build_request("/debug/multipage/upload")
        fake_service = _FakeService()

        with patch.dict(os.environ, {"APP_ENABLE_MULTIPAGE_DEMO_API": "true"}, clear=False):
            with patch("app.api.debug_tasks.get_tasks_service", return_value=fake_service):
                response = upload_multipage_demo(request, payload)

        self.assertEqual(response.batch_id, "batch-demo-1")

    def test_demo_batch_enabled_returns_detail(self) -> None:
        from app.api.debug_tasks import get_multipage_demo_batch

        request = _build_request("/debug/multipage/batches/b1")
        fake_service = _FakeService()

        with patch.dict(os.environ, {"APP_ENABLE_MULTIPAGE_DEMO_API": "true"}, clear=False):
            with patch("app.api.debug_tasks.get_tasks_service", return_value=fake_service):
                response = get_multipage_demo_batch(request, "b1")

        self.assertEqual(response.batch_id, "batch-demo-1")
        self.assertEqual(response.total_tasks, 2)


if __name__ == "__main__":
    unittest.main()
