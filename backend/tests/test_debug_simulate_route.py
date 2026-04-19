from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from app.bootstrap import create_app
from app.models import TaskCreateRequest, TaskRecord, TaskStatus


class _FakeRepository:
    def __init__(self) -> None:
        self.patches = []

    def patch_task(self, task_id: str, **kwargs) -> None:
        self.patches.append((task_id, kwargs))


class _FakeService:
    def __init__(self, task: TaskRecord) -> None:
        self.repository = _FakeRepository()
        self._task = task

    def emit_stream_event(self, task_id, event, payload) -> None:
        return None

    def get_task(self, task_id: str) -> TaskRecord:
        return self._task


class _FakeThread:
    def __init__(self, target=None, name=None, daemon=None) -> None:
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False

    def start(self) -> None:
        self.started = True


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


class DebugSimulateRouteTests(unittest.TestCase):
    def test_simulate_route_is_not_in_tasks_router(self) -> None:
        app = create_app()
        paths = {route.path for route in app.routes if hasattr(route, "path")}

        self.assertNotIn("/tasks/{task_id}/simulate", paths)
        self.assertIn("/debug/tasks/{task_id}/simulate", paths)

    def test_debug_simulate_flag_disabled_returns_404(self) -> None:
        from app.api.debug_tasks import simulate_processing

        request = _build_request("/debug/tasks/t1/simulate")
        with patch.dict(os.environ, {"APP_ENABLE_SIMULATE_TASK_API": "false"}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                simulate_processing(request, "t1", background=True)

        self.assertEqual(ctx.exception.status_code, 404)

    def test_debug_simulate_enabled_uses_service(self) -> None:
        from app.api.debug_tasks import simulate_processing

        now = datetime.now(timezone.utc)
        task = TaskRecord(
            id="t1",
            payload=TaskCreateRequest(image_url="https://example.com/img.png"),
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        fake_service = _FakeService(task)
        request = _build_request("/debug/tasks/t1/simulate")

        with patch.dict(os.environ, {"APP_ENABLE_SIMULATE_TASK_API": "true"}, clear=False):
            with patch("app.api.debug_tasks.get_tasks_service", return_value=fake_service):
                with patch("app.api.debug_tasks.threading.Thread", _FakeThread):
                    response = simulate_processing(request, "t1", background=True)

        self.assertEqual(response.task.id, "t1")
        self.assertTrue(fake_service.repository.patches)
        patched_task_id, kwargs = fake_service.repository.patches[0]
        self.assertEqual(patched_task_id, "t1")
        self.assertEqual(kwargs.get("stage"), "simulating")


if __name__ == "__main__":
    unittest.main()
