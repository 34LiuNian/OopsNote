from __future__ import annotations

import types
import unittest
from unittest.mock import Mock

from app.agents.pipeline import AgentPipeline, PipelineDependencies


class _FakeOcrExtractor:
    def __init__(self, client) -> None:
        self.llm_extractor = types.SimpleNamespace(client=client)
        self.model_resolver = lambda agent: f"model-for-{agent}"
        self.thinking_resolver = lambda _agent: True


class PipelineRuntimePortsTests(unittest.TestCase):
    def _build_pipeline(self, *, ocr_extractor, orchestrator=None) -> AgentPipeline:
        deps = PipelineDependencies(
            extractor=Mock(),
            solution_writer=Mock(),
            tagger=Mock(),
            diagram_reconstructor=None,
            archiver=Mock(),
            archive_store=Mock(),
            ocr_extractor=ocr_extractor,
        )
        return AgentPipeline(deps=deps, orchestrator=orchestrator)

    def test_get_segmenter_runtime_access(self) -> None:
        client = object()
        pipeline = self._build_pipeline(ocr_extractor=_FakeOcrExtractor(client))

        runtime = pipeline.get_segmenter_runtime_access()

        self.assertIsNotNone(runtime)
        assert runtime is not None
        self.assertIs(runtime.client, client)
        self.assertEqual(runtime.model_resolver("SEGMENTER"), "model-for-SEGMENTER")
        self.assertTrue(runtime.thinking_resolver("SEGMENTER"))

    def test_list_runtime_clients_deduplicates_shared_clients(self) -> None:
        shared = object()
        orchestrator = types.SimpleNamespace(
            solver=types.SimpleNamespace(client=shared),
            tagger=types.SimpleNamespace(client=shared),
        )
        pipeline = self._build_pipeline(
            ocr_extractor=_FakeOcrExtractor(shared),
            orchestrator=orchestrator,
        )

        clients = pipeline.list_runtime_clients()

        self.assertEqual(len(clients), 1)
        self.assertIs(clients[0], shared)


if __name__ == "__main__":
    unittest.main()
