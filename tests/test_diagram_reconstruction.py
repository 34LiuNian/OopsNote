from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

from oopsnote.ai.backends.langchain import LangChainRunner
from oopsnote.ai.diagram_renderer import TikzRenderBundle
from oopsnote.ai.dispatcher import ManagedTaskDispatcher
from oopsnote.ai.providers import ProviderCapabilities, ProviderProfile
from oopsnote.core import (
    AppSettingsStore,
    AssetStore,
    DiagramItem,
    DiagramRunMode,
    DiagramRunStep,
    DiagramStatus,
    Problem,
    RunPurpose,
    RunStatus,
    RunStore,
    TaskCreateRequest,
    TaskStatus,
    TaskStore,
)


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _Model:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self.outputs = outputs
        self.calls = 0

    async def ainvoke(self, messages):
        assert len(messages) == 2
        output = self.outputs[self.calls]
        self.calls += 1
        return SimpleNamespace(
            content=json.dumps(output),
            usage_metadata={"input_tokens": 10, "output_tokens": 5},
        )


class _Factory:
    def __init__(self, model: _Model) -> None:
        self.model = model
        self.secret_store = SimpleNamespace()

    def create_vision_json_model(self, profile):
        assert profile.capability.vision
        return self.model


class _Renderer:
    def __init__(self, assets: AssetStore) -> None:
        self.assets = assets
        self.calls = 0

    def render(self, source: str) -> TikzRenderBundle:
        self.calls += 1
        key = f"fake-{self.calls:02d}"
        return TikzRenderBundle(
            svg_path=self.assets.save_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "diagram.svg", key),
            pdf_path=self.assets.save_bytes(b"%PDF-1.4\n%%EOF\n", "diagram.pdf", key),
            png_path=self.assets.save_bytes(_PNG, "diagram.png", key),
            renderer_profile_version="test-v1",
        )


def _runner(tmp_path: Path, outputs: list[dict[str, object]]):
    tasks = TaskStore(tmp_path / "tasks")
    runs = RunStore(tmp_path / "runs")
    assets = AssetStore(tmp_path / "tasks" / "assets")
    source_path = assets.save_bytes(_PNG, "source.png", "source")
    task = tasks.create(TaskCreateRequest(subject="physics", asset_path=source_path))
    task = tasks.update(
        task.id,
        status=TaskStatus.COMPLETED,
        problem=Problem(subject="physics", has_diagram=True),
    )
    item = DiagramItem(source_asset_path=source_path)
    tasks.add_diagram_item(task.id, item)
    profile = ProviderProfile(
        id="test",
        version=1,
        provider="openai",
        model="vision-test",
        capability=ProviderCapabilities(vision=True),
    )
    run = runs.create(
        task.id,
        backend="langchain",
        purpose=RunPurpose.DIAGRAM,
        priority=20,
        diagram_item_id=item.id,
        diagram_mode=DiagramRunMode.AUTO,
        diagram_max_candidates=4,
        diagram_step=DiagramRunStep.GENERATE,
        provider="openai",
        model="vision-test",
        provider_profile_snapshot={"policy_version": 1, "diagram": profile.model_dump(mode="json")},
    )
    tasks.update_diagram_item(
        task.id,
        item.id,
        active_run_id=run.id,
        status=DiagramStatus.QUEUED,
    )
    model = _Model(outputs)
    renderer = _Renderer(assets)
    runner = LangChainRunner(
        project_root=Path(__file__).resolve().parents[1],
        task_store=tasks,
        run_store=runs,
        settings_store=AppSettingsStore(tmp_path / "settings.json"),
        provider_factory=lambda: _Factory(model),
        tool_client_factory=lambda: None,
        asset_store=assets,
        tikz_renderer=renderer,
        timeout_seconds=10,
    )
    return runner, tasks, runs, task.id, item.id, run.id, model, renderer


def _drain_quantums(runner, runs, task_id: str, run_id: str) -> None:
    for _ in range(16):
        run = runs.get(run_id)
        if run.status != RunStatus.QUEUED:
            return
        runner.run(task_id, run_id)
    raise AssertionError("diagram run did not reach a terminal state")


def test_review_outputs_the_next_candidate_and_retains_both_versions(tmp_path: Path):
    runner, tasks, runs, task_id, item_id, run_id, model, renderer = _runner(
        tmp_path,
        [
            {"decision": "revise", "tikz_source": "\\draw (0,0)--(1,0);", "hard_errors": []},
            {
                "decision": "revise",
                "tikz_source": "\\draw[->] (0,0)--(1,0);",
                "hard_errors": ["missing arrow"],
            },
            {"decision": "accept", "hard_errors": [], "soft_differences": ["line width"]},
        ],
    )

    _drain_quantums(runner, runs, task_id, run_id)

    task = tasks.get(task_id)
    item = next(value for value in task.diagram_items if value.id == item_id)
    assert task.status == TaskStatus.COMPLETED
    assert item.status == DiagramStatus.READY_TIKZ
    assert item.active_run_id is None
    assert len(item.candidates) == 2
    assert item.candidates[1].parent_candidate_id == item.candidates[0].id
    assert item.selected_candidate_id == item.candidates[1].id
    assert item.candidates[1].pdf_path and item.candidates[1].svg_path
    assert model.calls == 3
    assert renderer.calls == 2


def test_model_boundary_normalizes_equivalent_provider_json_shapes(tmp_path: Path):
    runner, tasks, runs, task_id, item_id, run_id, model, renderer = _runner(
        tmp_path,
        [
            {
                "decision": "revise",
                "tikz_source": "\\draw (0,0)--(1,0);",
                "source_region": {"x": 40, "y": 30, "width": 420, "height": 280},
                "hard_errors": [],
                "soft_differences": "estimated proportions",
            },
            {"decision": "accept", "hard_errors": [], "soft_differences": "line width"},
        ],
    )

    _drain_quantums(runner, runs, task_id, run_id)

    item = next(value for value in tasks.get(task_id).diagram_items if value.id == item_id)
    assert item.status == DiagramStatus.READY_TIKZ
    assert item.candidates[0].soft_differences == ["line width"]
    assert model.calls == 2
    assert renderer.calls == 1


def test_model_boundary_normalizes_pixel_region_only_for_keep_image():
    result = LangChainRunner._parse_diagram_result(
        SimpleNamespace(content=json.dumps({
            "decision": "keep_image",
            "source_region": {"x": 40, "y": 30, "width": 420, "height": 280},
            "hard_errors": [],
            "soft_differences": [],
        })),
        source_dimensions=(738, 440),
    )

    assert result.source_region is not None
    assert abs(result.source_region.x - (40 / 738)) < 1e-9
    assert abs(result.source_region.y - (30 / 440)) < 1e-9
    assert abs(result.source_region.width - (420 / 738)) < 1e-9
    assert abs(result.source_region.height - (280 / 440)) < 1e-9


def test_missing_provider_model_is_a_deterministic_configuration_error():
    error = RuntimeError(
        "Error calling model 'gemini': 404 NOT_FOUND. Model is not supported by this account"
    )

    assert LangChainRunner._error_code(error) == "provider_model_unavailable"


def test_candidate_limit_never_creates_a_fifth_candidate(tmp_path: Path):
    runner, tasks, runs, task_id, item_id, run_id, model, renderer = _runner(
        tmp_path,
        [
            {"decision": "revise", "tikz_source": "\\draw (0,0)--(1,0);", "hard_errors": []},
            {"decision": "revise", "tikz_source": "\\draw (0,0)--(2,0);", "hard_errors": ["wrong label"]},
        ],
    )
    runs.update(run_id, diagram_max_candidates=1)

    _drain_quantums(runner, runs, task_id, run_id)

    item = next(value for value in tasks.get(task_id).diagram_items if value.id == item_id)
    assert item.status == DiagramStatus.NEEDS_REVIEW
    assert item.needs_review is True
    assert len(item.candidates) == 1
    assert model.calls == 2
    assert renderer.calls == 1


def test_legacy_singular_metadata_migrates_to_one_authoritative_item():
    from oopsnote.core import TaskRecord

    task = TaskRecord.model_validate({
        "id": "legacy",
        "asset_path": "/assets/source.png",
        "metadata": {
            "diagram_detected": True,
            "diagram_kind": "tikz",
            "diagram_tikz_source": "\\draw (0,0)--(1,0);",
            "diagram_svg": "<svg/>",
            "source": "exam",
        },
    })

    assert len(task.diagram_items) == 1
    assert task.diagram_items[0].status == DiagramStatus.NEEDS_REVIEW
    assert task.diagram_items[0].candidates[0].source_kind == "legacy"
    assert task.metadata == {"source": "exam"}


def test_dispatcher_orders_primary_work_before_queued_background_diagram(tmp_path: Path):
    runs = RunStore(tmp_path / "runs")
    low = runs.create(
        "task-diagram",
        purpose=RunPurpose.DIAGRAM,
        priority=20,
        diagram_item_id="item",
        diagram_mode=DiagramRunMode.AUTO,
        diagram_max_candidates=4,
        diagram_step=DiagramRunStep.GENERATE,
    )
    high = runs.create("task-problem", purpose=RunPurpose.PROBLEM, priority=0)
    runner = SimpleNamespace(run_store=runs, backend_name="fake")
    dispatcher = ManagedTaskDispatcher(runner, workers=1)
    dispatcher.start = lambda: None

    dispatcher.schedule(low.task_id, low.id)
    dispatcher.schedule(high.task_id, high.id)

    assert dispatcher._queue.get_nowait()[3] == high.id
    assert dispatcher._queue.get_nowait()[3] == low.id
