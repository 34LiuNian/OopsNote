from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from oopsnote.ai.backends.langchain import LangChainRunner
from oopsnote.ai.diagram_agent import (
    ACCEPT_TIKZ_CANDIDATE,
    KEEP_SOURCE_IMAGE,
    REQUEST_DIAGRAM_REVIEW,
    SUBMIT_TIKZ_REVISION,
    legal_diagram_tools,
)
from oopsnote.ai.diagram_renderer import TikzRenderBundle, TikzRenderClient, TikzRenderError
from oopsnote.ai.dispatcher import ManagedTaskDispatcher
from oopsnote.ai.providers import ProviderCapabilities, ProviderProfile
from oopsnote.api import main
from oopsnote.core import (
    AppSettingsStore,
    AssetStore,
    DiagramItem,
    DiagramRunMode,
    DiagramRunStep,
    DiagramSourceRegion,
    DiagramStatus,
    DiagramTransport,
    Problem,
    RunPurpose,
    RunStatus,
    RunStore,
    TagStore,
    TaskCreateRequest,
    TaskStatus,
    TaskStore,
    WorkspaceId,
)
from oopsnote.mcp import server
from oopsnote.mcp.context import (
    McpCapability,
    McpStores,
    activate_capability,
    reset_capability,
)

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _Model:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.outputs = calls
        self.calls = 0
        self.messages: list[list[Any]] = []
        self.bound_tools: list[frozenset[str]] = []

    async def ainvoke(self, messages):
        self.messages.append(list(messages))
        name, args = self.outputs[self.calls]
        self.calls += 1
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": args,
                    "id": f"diagram-call-{self.calls}",
                    "type": "tool_call",
                }
            ],
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )


class _Factory:
    def __init__(self, model: _Model) -> None:
        self.model = model
        self.secret_store = SimpleNamespace()

    def create_diagram_model(self, profile):
        assert profile.capability.vision
        assert profile.capability.tool_calling
        return self.model

    def bind_managed_tools(self, model, profile, *, tool_names, **kwargs):
        del profile, kwargs
        model.bound_tools.append(frozenset(tool_names))
        return model


class _ToolClient:
    def __init__(
        self,
        tasks: TaskStore,
        runs: RunStore,
        assets: AssetStore,
        tags: TagStore,
    ) -> None:
        self.stores = McpStores(
            task_store=tasks,
            run_store=runs,
            asset_store=assets,
            tag_store=tags,
        )

    async def call(self, remote_name: str, arguments: dict[str, Any]) -> Any:
        if remote_name == KEEP_SOURCE_IMAGE and isinstance(arguments.get("source_region"), dict):
            arguments = {
                **arguments,
                "source_region": DiagramSourceRegion.model_validate(arguments["source_region"]),
            }
        capability = McpCapability(
            workspace_id=WorkspaceId.new(),
            stores=self.stores,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        token = activate_capability(capability)
        try:
            return getattr(server, remote_name)(**arguments)
        finally:
            reset_capability(token)


class _Renderer:
    def __init__(self, assets: AssetStore, failures: list[TikzRenderError] | None = None) -> None:
        self.assets = assets
        self.failures = list(failures or [])
        self.calls = 0

    def render(self, source: str) -> TikzRenderBundle:
        del source
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        key = f"fake-{self.calls:02d}"
        return TikzRenderBundle(
            svg_path=self.assets.save_bytes(
                b"<svg xmlns='http://www.w3.org/2000/svg'/>", "diagram.svg", key
            ),
            pdf_path=self.assets.save_bytes(b"%PDF-1.4\n%%EOF\n", "diagram.pdf", key),
            png_path=self.assets.save_bytes(_PNG, "diagram.png", key),
            renderer_profile_version="test-v1",
            base_font_size_pt=10,
            canvas_width_em=12,
            canvas_height_em=8,
        )


@dataclass
class _Harness:
    runner: LangChainRunner
    tasks: TaskStore
    runs: RunStore
    task_id: str
    item_id: str
    run_id: str
    model: _Model
    renderer: _Renderer
    tool_client: _ToolClient


def _runner(
    tmp_path: Path,
    calls: list[tuple[str, dict[str, Any]]],
    *,
    transport: DiagramTransport = DiagramTransport.MESSAGE_IMAGE_BRIDGE,
    mode: DiagramRunMode = DiagramRunMode.AUTO,
    max_candidates: int = 4,
    renderer_failures: list[TikzRenderError] | None = None,
) -> _Harness:
    tasks = TaskStore(tmp_path / "tasks")
    runs = RunStore(tmp_path / "runs")
    assets = AssetStore(tmp_path / "tasks" / "assets")
    tags = TagStore(
        user_path=tmp_path / "tags-user.json",
        builtin_path=tmp_path / "tags-builtin.json",
    )
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
        capability=ProviderCapabilities(
            vision=True,
            tool_calling=True,
            tool_result_image=transport == DiagramTransport.NATIVE_TOOL_IMAGE,
        ),
    )
    run = runs.create(
        task.id,
        backend="langchain",
        purpose=RunPurpose.DIAGRAM,
        priority=20,
        diagram_item_id=item.id,
        diagram_mode=mode,
        diagram_max_candidates=max_candidates,
        diagram_step=DiagramRunStep.GENERATE,
        diagram_transport=transport,
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
    model = _Model(calls)
    renderer = _Renderer(assets, renderer_failures)
    client = _ToolClient(tasks, runs, assets, tags)
    runner = LangChainRunner(
        project_root=Path(__file__).resolve().parents[1],
        task_store=tasks,
        run_store=runs,
        settings_store=AppSettingsStore(tmp_path / "settings.json"),
        provider_factory=lambda: _Factory(model),
        tool_client_factory=lambda: client,
        asset_store=assets,
        tikz_renderer=renderer,
        timeout_seconds=10,
    )
    return _Harness(runner, tasks, runs, task.id, item.id, run.id, model, renderer, client)


def _item(harness: _Harness) -> DiagramItem:
    return next(
        value
        for value in harness.tasks.get(harness.task_id).diagram_items
        if value.id == harness.item_id
    )


def test_technical_diagram_failure_is_not_human_review(tmp_path: Path):
    harness = _runner(tmp_path, [])
    harness.runner._fail_diagram(
        harness.task_id,
        harness.run_id,
        "'str' object has no attribute 'choices'",
        "runner_error",
    )
    task = harness.tasks.get(harness.task_id)
    item = _item(harness)
    assert item.status == DiagramStatus.FAILED
    assert item.needs_review is False
    assert harness.runs.get(harness.run_id).error_code == "runner_error"
    problem_view = main._problem_view(task, task.problem)
    assert problem_view["diagram_needs_review"] is False
    assert problem_view["diagram_error_category"] == "internal"


def test_model_supplied_identity_cannot_override_managed_diagram_run(tmp_path: Path):
    harness = _runner(
        tmp_path,
        [
            (
                SUBMIT_TIKZ_REVISION,
                {
                    "task_id": "task_1",
                    "run_id": "run_1",
                    "tikz_source": "\\draw (0,0)--(1,0);",
                },
            ),
            (
                ACCEPT_TIKZ_CANDIDATE,
                {"task_id": "default", "run_id": "default"},
            ),
        ],
    )

    harness.runner.run(harness.task_id, harness.run_id)

    item = _item(harness)
    assert item.status == DiagramStatus.READY_TIKZ
    assert harness.runs.get(harness.run_id).status == RunStatus.COMPLETED
    assert harness.model.calls == 2


def test_provider_gateway_html_is_publicly_summarized_but_retained_as_evidence(tmp_path: Path):
    harness = _runner(tmp_path, [])
    raw_error = (
        "524 <none>. {'message': '<!DOCTYPE html><html><head>"
        "<title>modelflare.dev | 524: A timeout occurred</title>"
        "</head><body>origin timed out</body></html>'}"
    )
    harness.runner._fail_diagram(
        harness.task_id,
        harness.run_id,
        raw_error,
        "runner_error",
    )

    stored_item = _item(harness)
    stored_run = harness.runs.get(harness.run_id)
    assert stored_item.last_error == raw_error
    assert stored_run.error_message == raw_error

    task = harness.tasks.get(harness.task_id)
    problem_view = main._problem_view(task, task.problem)
    expected = "供应商侧请求失败：modelflare.dev 网关响应超时（HTTP 524）"
    assert problem_view["diagram_error"] == expected
    assert problem_view["diagram_error_category"] == "model_request"
    assert problem_view["diagram_needs_review"] is False
    assert problem_view["diagram_items"][0]["last_error"] == expected
    assert problem_view["diagram_items"][0]["last_error_code"] == "provider_unavailable"
    assert "<!DOCTYPE" not in str(problem_view)
    assert main._run_view(stored_run)["error_message"] == expected


def test_agent_revision_loop_retains_versions_and_accepts_latest(tmp_path: Path):
    harness = _runner(
        tmp_path,
        [
            (SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw (0,0)--(1,0);"}),
            (
                SUBMIT_TIKZ_REVISION,
                {
                    "tikz_source": "\\draw[->] (0,0)--(1,0);",
                    "hard_errors": ["missing arrow"],
                },
            ),
            (ACCEPT_TIKZ_CANDIDATE, {"soft_differences": ["line width"]}),
        ],
    )
    harness.runner.run(harness.task_id, harness.run_id)
    item = _item(harness)
    assert item.status == DiagramStatus.READY_TIKZ
    assert item.active_run_id is None
    assert len(item.candidates) == 2
    assert item.candidates[1].parent_candidate_id == item.candidates[0].id
    assert item.selected_candidate_id == item.candidates[1].id
    assert item.candidates[1].pdf_path and item.candidates[1].svg_path
    assert item.candidates[1].canvas_width_em == 12
    assert item.candidates[1].canvas_height_em == 8
    assert item.candidates[1].soft_differences == ["line width"]
    assert harness.runs.get(harness.run_id).status == RunStatus.COMPLETED
    assert harness.model.calls == 3
    assert harness.renderer.calls == 2


def test_chat_transport_bridges_rendered_image_in_a_human_message(tmp_path: Path):
    harness = _runner(
        tmp_path,
        [
            (SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw (0,0)--(1,0);"}),
            (ACCEPT_TIKZ_CANDIDATE, {}),
        ],
    )
    harness.runner.run(harness.task_id, harness.run_id)
    second_turn = harness.model.messages[1]
    assert isinstance(second_turn[-2], ToolMessage)
    assert isinstance(second_turn[-2].content, str)
    assert isinstance(second_turn[-1], HumanMessage)
    assert any(
        isinstance(block, dict) and block.get("type") == "image_url"
        for block in second_turn[-1].content
    )


def test_responses_transport_returns_rendered_image_in_tool_output(tmp_path: Path):
    harness = _runner(
        tmp_path,
        [
            (SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw (0,0)--(1,0);"}),
            (ACCEPT_TIKZ_CANDIDATE, {}),
        ],
        transport=DiagramTransport.NATIVE_TOOL_IMAGE,
    )
    harness.runner.run(harness.task_id, harness.run_id)
    second_turn = harness.model.messages[1]
    assert isinstance(second_turn[-1], ToolMessage)
    assert isinstance(second_turn[-1].content, list)
    assert any(
        isinstance(block, dict) and block.get("type") == "image_url"
        for block in second_turn[-1].content
    )


def test_diagram_retry_preserves_transport_and_provider_snapshot(tmp_path: Path):
    harness = _runner(tmp_path, [], transport=DiagramTransport.NATIVE_TOOL_IMAGE)
    original = harness.runs.get(harness.run_id)
    harness.runs.finish(
        original.id,
        RunStatus.FAILED,
        error_code="provider_timeout",
        error_message="provider timed out",
    )
    harness.runs.update(original.id, retryable=True)
    harness.tasks.update_diagram_item(
        harness.task_id,
        harness.item_id,
        expected_active_run_id=original.id,
        active_run_id=None,
        status=DiagramStatus.FAILED,
    )
    scheduled = []
    harness.runner._dispatcher.schedule = lambda task_id, run_id: scheduled.append(
        (task_id, run_id)
    )

    retry = harness.runner.retry_diagram_if_eligible(harness.task_id, original.id)

    assert retry is not None
    assert retry.diagram_transport == DiagramTransport.NATIVE_TOOL_IMAGE
    assert retry.provider_profile_snapshot == original.provider_profile_snapshot
    assert scheduled == [(harness.task_id, retry.id)]


def test_historical_diagram_run_without_transport_is_readable_but_not_executable(
    tmp_path: Path,
):
    harness = _runner(tmp_path, [])
    historical = harness.runs.update(harness.run_id, diagram_transport=None)
    assert historical.diagram_transport is None

    harness.runner.run(harness.task_id, harness.run_id)

    failed = harness.runs.get(harness.run_id)
    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "model_output_invalid"
    assert "predates the tool protocol" in (failed.error_message or "")
    assert harness.model.calls == 0


def test_compile_error_is_returned_to_agent_for_a_revision(tmp_path: Path):
    harness = _runner(
        tmp_path,
        [
            (SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw bad;"}),
            (SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw (0,0)--(1,0);"}),
            (ACCEPT_TIKZ_CANDIDATE, {}),
        ],
        renderer_failures=[TikzRenderError("renderer_failed", "Undefined control sequence")],
    )
    harness.runner.run(harness.task_id, harness.run_id)
    item = _item(harness)
    assert item.status == DiagramStatus.READY_TIKZ
    assert len(item.candidates) == 2
    assert item.candidates[0].render_error_code == "renderer_failed"
    assert item.candidates[1].png_path
    first_result = harness.model.messages[1][-1]
    assert isinstance(first_result, ToolMessage)
    assert "Undefined control sequence" in str(first_result.content)


def test_renderer_environment_error_stops_after_first_candidate_for_human_review(
    tmp_path: Path,
):
    evidence = 'Package fontspec Error: The font "Noto Serif CJK SC" cannot be found'
    harness = _runner(
        tmp_path,
        [
            (SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw (0,0)--(1,0);"}),
            (SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw (0,0)--(2,0);"}),
        ],
        renderer_failures=[
            TikzRenderError(
                "renderer_environment_error",
                "TikZ renderer shared preamble is invalid; manual intervention is required",
                evidence=evidence,
            )
        ],
    )

    harness.runner.run(harness.task_id, harness.run_id)

    item = _item(harness)
    run = harness.runs.get(harness.run_id)
    assert item.status == DiagramStatus.NEEDS_REVIEW
    assert item.needs_review is True
    assert item.active_run_id is None
    assert item.last_error_code == "renderer_environment_error"
    assert len(item.candidates) == 1
    assert item.candidates[0].render_error_message == evidence
    assert item.candidates[0].review_reason == "TikZ 渲染服务环境异常，需要人工介入修复"
    assert harness.model.calls == 1
    assert harness.renderer.calls == 1
    assert run.status == RunStatus.FAILED
    assert run.error_code == "renderer_environment_error"
    assert run.retryable is False
    task = harness.tasks.get(harness.task_id)
    problem_view = main._problem_view(task, task.problem)
    assert problem_view["diagram_needs_review"] is True
    assert problem_view["diagram_error_category"] == "human_review"
    assert problem_view["diagram_error"] == "TikZ 渲染服务环境异常，需要人工介入修复"


def test_resumed_render_checkpoint_environment_error_does_not_call_model(tmp_path: Path):
    harness = _runner(
        tmp_path,
        [],
        renderer_failures=[
            TikzRenderError(
                "renderer_environment_error",
                "TikZ renderer shared preamble is invalid",
                evidence="shared preamble probe failed",
            )
        ],
    )
    asyncio.run(
        harness.tool_client.call(
            SUBMIT_TIKZ_REVISION,
            {
                "task_id": harness.task_id,
                "run_id": harness.run_id,
                "tikz_source": "\\draw (0,0)--(1,0);",
            },
        )
    )

    harness.runner.run(harness.task_id, harness.run_id)

    item = _item(harness)
    assert item.status == DiagramStatus.NEEDS_REVIEW
    assert len(item.candidates) == 1
    assert harness.model.calls == 0
    assert harness.renderer.calls == 1


def test_candidate_limit_binds_human_review_instead_of_an_extra_revision(tmp_path: Path):
    harness = _runner(
        tmp_path,
        [
            (SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw (0,0)--(1,0);"}),
            (
                REQUEST_DIAGRAM_REVIEW,
                {"reason": "label still differs", "hard_errors": ["wrong label"]},
            ),
        ],
        max_candidates=1,
    )
    harness.runner.run(harness.task_id, harness.run_id)
    item = _item(harness)
    assert item.status == DiagramStatus.NEEDS_REVIEW
    assert item.needs_review is True
    assert len(item.candidates) == 1
    assert harness.model.bound_tools[1] == frozenset(
        {ACCEPT_TIKZ_CANDIDATE, KEEP_SOURCE_IMAGE, REQUEST_DIAGRAM_REVIEW}
    )


def test_rebuild_mode_never_exposes_keep_source_image(tmp_path: Path):
    harness = _runner(
        tmp_path,
        [(SUBMIT_TIKZ_REVISION, {"tikz_source": "\\draw (0,0)--(1,0);"})],
        mode=DiagramRunMode.REBUILD,
    )
    run = harness.runs.get(harness.run_id)
    assert legal_diagram_tools(run, _item(harness)) == frozenset({SUBMIT_TIKZ_REVISION})


def test_repeated_tikz_submission_is_idempotent(tmp_path: Path):
    harness = _runner(tmp_path, [])
    arguments = {
        "task_id": harness.task_id,
        "run_id": harness.run_id,
        "tikz_source": "\\draw (0,0)--(1,0);",
    }
    first = asyncio.run(harness.tool_client.call(SUBMIT_TIKZ_REVISION, dict(arguments)))
    second = asyncio.run(harness.tool_client.call(SUBMIT_TIKZ_REVISION, dict(arguments)))
    assert first["candidate_id"] == second["candidate_id"]
    assert second["repeated"] is True
    assert len(_item(harness).candidates) == 1


def test_missing_provider_model_is_a_deterministic_configuration_error():
    error = RuntimeError(
        "Error calling model 'gemini': 404 NOT_FOUND. Model is not supported by this account"
    )
    assert LangChainRunner._error_code(error) == "provider_model_unavailable"


def test_missing_renderer_configuration_is_not_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OOPSNOTE_LATEX_RENDERER_URL", raising=False)
    renderer = TikzRenderClient(AssetStore(tmp_path / "assets"))
    with pytest.raises(TikzRenderError) as caught:
        renderer.render(r"\begin{tikzpicture}\draw (0,0)--(1,0);\end{tikzpicture}")
    assert caught.value.code == "renderer_unavailable"
    assert caught.value.retryable is False


def test_renderer_client_persists_normalized_typography_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    response = httpx.Response(
        200,
        json={
            "svg_base64": base64.b64encode(b"<svg><path d='M0 0'/></svg>").decode(),
            "pdf_base64": base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode(),
            "png_base64": base64.b64encode(_PNG).decode(),
            "renderer_profile_version": "tikz-xelatex-v6-poppler",
            "base_font_size_pt": 10,
            "canvas_width_em": 12.5,
            "canvas_height_em": 8.25,
        },
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)
    renderer = TikzRenderClient(AssetStore(tmp_path / "assets"), "http://renderer")

    bundle = renderer.render(r"\draw (0,0)--(1,0);")

    assert bundle.base_font_size_pt == 10
    assert bundle.canvas_width_em == 12.5
    assert bundle.canvas_height_em == 8.25


def test_renderer_client_preserves_structured_environment_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    evidence = 'Package fontspec Error: The font "Noto Serif CJK SC" cannot be found'
    response = httpx.Response(
        503,
        json={
            "detail": {
                "code": "renderer_environment_error",
                "message": "TikZ renderer shared preamble is invalid",
                "retryable": False,
                "evidence": evidence,
            }
        },
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)
    renderer = TikzRenderClient(AssetStore(tmp_path / "assets"), "http://renderer")

    with pytest.raises(TikzRenderError) as caught:
        renderer.render(r"\begin{tikzpicture}\draw (0,0)--(1,0);\end{tikzpicture}")

    assert caught.value.code == "renderer_environment_error"
    assert caught.value.retryable is False
    assert caught.value.evidence == evidence


def test_renderer_client_classifies_legacy_missing_shared_font(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    evidence = (
        'Package fontspec Error: The font "Noto Serif CJK SC" cannot be found; No pages of output.'
    )
    response = httpx.Response(422, json={"detail": evidence})
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)
    renderer = TikzRenderClient(AssetStore(tmp_path / "assets"), "http://renderer")

    with pytest.raises(TikzRenderError) as caught:
        renderer.render(r"\begin{tikzpicture}\draw (0,0)--(1,0);\end{tikzpicture}")

    assert caught.value.code == "renderer_environment_error"
    assert caught.value.retryable is False
    assert "Package fontspec Error" in (caught.value.evidence or "")


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
