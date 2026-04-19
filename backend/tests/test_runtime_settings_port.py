from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.services.tasks_service import TasksService


class _FakeRepository:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir


class _PipelineWithClients:
    def __init__(self, clients) -> None:
        self._clients = list(clients)

    def list_runtime_clients(self):
        return list(self._clients)


class _ClientWithoutDebugPayload:
    def __init__(self) -> None:
        self.debug_payload = False
        self.calls = []

    def reconfigure(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
    ) -> None:
        self.calls.append(
            {
                "base_url": base_url,
                "api_key": api_key,
                "model": model,
                "temperature": temperature,
            }
        )


class RuntimeSettingsPortTests(unittest.TestCase):
    def _build_service(self, pipeline) -> TasksService:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        repository = _FakeRepository(Path(tmp.name) / "tasks")
        repository.base_dir.mkdir(parents=True, exist_ok=True)
        return TasksService(
            repository=repository,
            pipeline=pipeline,
            asset_store=Mock(),
            tag_store=Mock(),
        )

    def test_apply_runtime_settings_calls_reconfigure(self) -> None:
        client = Mock()
        client.reconfigure = Mock()
        svc = self._build_service(_PipelineWithClients([client]))

        stats = svc.apply_runtime_settings(
            base_url="https://example.test/v1",
            api_key="sk-test",
            model="gpt-test",
            temperature=0.33,
            debug_payload=True,
        )

        self.assertEqual(stats["clients_total"], 1)
        self.assertEqual(stats["clients_updated"], 1)
        client.reconfigure.assert_called_once_with(
            base_url="https://example.test/v1",
            api_key="sk-test",
            model="gpt-test",
            temperature=0.33,
            debug_payload=True,
        )

    def test_apply_runtime_settings_handles_missing_debug_payload_arg(self) -> None:
        client = _ClientWithoutDebugPayload()
        svc = self._build_service(_PipelineWithClients([client]))

        stats = svc.apply_runtime_settings(
            base_url="https://example.test/v1",
            model="gpt-test",
            debug_payload=True,
        )

        self.assertEqual(stats["clients_total"], 1)
        self.assertEqual(stats["clients_updated"], 1)
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(client.debug_payload)

    def test_apply_runtime_settings_without_collector_is_safe(self) -> None:
        svc = self._build_service(pipeline=object())

        stats = svc.apply_runtime_settings(debug_payload=True)

        self.assertEqual(stats["clients_total"], 0)
        self.assertEqual(stats["clients_updated"], 0)


if __name__ == "__main__":
    unittest.main()
