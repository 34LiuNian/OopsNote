"""LangChain model adapter under the shared OopsNote managed lifecycle."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import mimetypes
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from oopsnote.ai.diagram_agent import (
    SUBMIT_TIKZ_REVISION,
    active_candidate,
    encode_diagram_tool_result,
    legal_diagram_tools,
    run_candidates,
)
from oopsnote.ai.diagram_renderer import TikzRenderClient, TikzRenderError
from oopsnote.ai.langchain_tools import (
    ContractBoundToolDispatcher,
    RestrictedMcpToolClient,
    langchain_tool_schemas,
)
from oopsnote.ai.managed import ManagedAiRunner
from oopsnote.ai.providers import (
    LangChainModelPolicy,
    ProviderClientFactory,
    ProviderProfile,
    collect_unreferenced_channel_secrets,
    profile_for_channel_model,
    provider_http_status,
)
from oopsnote.ai.run_control import AsyncioTaskRunControl
from oopsnote.ai.skills import (
    load_skill_pack,
    load_skill_prompt,
    load_skill_prompts,
    render_skill_prompt,
    skill_pack_version,
)
from oopsnote.core import (
    AppSettingsStore,
    AssetStore,
    DiagramCandidate,
    DiagramItem,
    DiagramRunMode,
    DiagramRunStep,
    DiagramStatus,
    DiagramTransport,
    RunPurpose,
    RunStatus,
    RunValidationError,
    StateConflict,
    TaskStage,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class DiagramModelContractError(ValueError):
    code = "model_output_invalid"


class LangChainRunner(ManagedAiRunner):
    """Provider calls and explicit tool loop; never a lifecycle owner."""

    backend_name = "langchain"
    max_tool_rounds = 24
    _SOLVER_TOOL_NAMES = frozenset(
        {
            "ocr_image",
            "mcp__oopsnote_pipeline_report_task_stage",
            "mcp__oopsnote_pipeline_submit_solution_candidate",
            "mcp__oopsnote_pipeline_fail_task",
        }
    )
    _REVIEW_TOOL_NAMES = frozenset(
        {
            "mcp__oopsnote_pipeline_report_task_stage",
            "mcp__oopsnote_pipeline_list_tags",
            "mcp__oopsnote_pipeline_create_tag",
            "mcp__oopsnote_pipeline_finalize_task",
            "mcp__oopsnote_pipeline_fail_task",
        }
    )
    _REPORT_TOOL = "mcp__oopsnote_pipeline_report_task_stage"
    _LIST_TAGS_TOOL = "mcp__oopsnote_pipeline_list_tags"
    _CREATE_TAG_TOOL = "mcp__oopsnote_pipeline_create_tag"
    _SUBMIT_TOOL = "mcp__oopsnote_pipeline_submit_solution_candidate"
    _FINALIZE_TOOL = "mcp__oopsnote_pipeline_finalize_task"

    def __init__(
        self,
        *,
        settings_store: AppSettingsStore,
        provider_factory: Callable[[], ProviderClientFactory],
        tool_client_factory: Callable[[], RestrictedMcpToolClient],
        asset_store: AssetStore | None = None,
        tikz_renderer: TikzRenderClient | None = None,
        max_concurrent_tasks: int = 1,
        **kwargs: Any,
    ) -> None:
        self.max_concurrent_tasks = max(1, int(max_concurrent_tasks))
        super().__init__(**kwargs)
        self.settings_store = settings_store
        self.provider_factory = provider_factory
        self.tool_client_factory = tool_client_factory
        self.asset_store = asset_store or AssetStore(self.task_store.base_dir / "assets")
        self.tikz_renderer = tikz_renderer or TikzRenderClient(self.asset_store)
        self._skill_pack = load_skill_pack(self.project_root)
        self._runtime_prompts = load_skill_prompts(self.project_root, "oopsnote-orchestrator")
        self._diagram_skill_prompt = load_skill_prompt(
            self.project_root, "oopsnote-diagram-reconstruction"
        )
        self._diagram_prompts = load_skill_prompts(
            self.project_root, "oopsnote-diagram-reconstruction"
        )
        prompt_sources = {
            "runtime_skills": self._skill_pack,
            "ocr": load_skill_prompt(self.project_root, "oopsnote-ocr-extract"),
            "runtime_messages": self._runtime_prompts,
        }
        self.prompt_version = skill_pack_version(
            json.dumps(prompt_sources, ensure_ascii=False, sort_keys=True)
        )
        self.diagram_prompt_version = skill_pack_version(
            json.dumps(
                {
                    "system": self._diagram_skill_prompt,
                    "messages": self._diagram_prompts,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    def _selected_policy(self) -> LangChainModelPolicy:
        policy = self.settings_store.langchain_model_policy()
        if policy is None:
            raise RuntimeError("no global LangChain model policy is configured")
        return policy

    def _profile_for_selection(self, selection: Any, stage: str | None = None) -> ProviderProfile:
        channels = {channel.id: channel for channel in self.settings_store.provider_channels()}
        channel = channels.get(selection.channel_id)
        if channel is None or not channel.enabled:
            raise RuntimeError("selected LangChain channel is unavailable")
        factory = self.provider_factory()
        if not channel.credential_ref or not factory.secret_store.has(channel.credential_ref):
            raise RuntimeError("selected LangChain channel has no credential")
        try:
            profile = profile_for_channel_model(channel, selection.model_id)
        except KeyError as error:
            raise RuntimeError("selected LangChain model is unavailable") from error
        if not profile.enabled:
            raise RuntimeError("selected LangChain model is disabled")
        if stage in {"vision", "diagram"} and not profile.capability.vision:
            raise RuntimeError("selected LangChain Vision model is not enabled")
        if stage in {"agent", "review", "diagram"} and not profile.capability.tool_calling:
            raise RuntimeError(f"selected LangChain {stage} model has no Tool Calling capability")
        return profile

    def _selected_profile(self) -> ProviderProfile:
        policy = self._selected_policy()
        return self._profile_for_selection(policy.agent, "agent")

    def _run_metadata(self, task_id: str) -> dict[str, Any]:
        del task_id
        policy = self._selected_policy()
        vision = self._profile_for_selection(policy.vision, "vision")
        agent = self._profile_for_selection(policy.agent, "agent")
        review = self._profile_for_selection(policy.review, "review")
        diagram = self._profile_for_selection(policy.diagram, "diagram")
        snapshot: dict[str, Any] = {
            "policy_version": policy.version,
            "vision": vision.model_dump(mode="json"),
            "agent": agent.model_dump(mode="json"),
            "review": review.model_dump(mode="json"),
            "diagram": diagram.model_dump(mode="json"),
        }
        return {
            "provider": agent.provider,
            "model": agent.model,
            "prompt_version": self.prompt_version,
            "provider_profile_snapshot": snapshot,
        }

    def _diagram_run_metadata(self, task_id: str) -> dict[str, Any]:
        del task_id
        policy = self._selected_policy()
        profile = self._profile_for_selection(policy.diagram, "diagram")
        return {
            "provider": profile.provider,
            "model": profile.model,
            "prompt_version": self.diagram_prompt_version,
            "provider_profile_snapshot": {
                "policy_version": policy.version,
                "diagram": profile.model_dump(mode="json"),
            },
            "diagram_transport": (
                DiagramTransport.NATIVE_TOOL_IMAGE
                if profile.capability.tool_result_image
                else DiagramTransport.MESSAGE_IMAGE_BRIDGE
            ),
        }

    def _retry_run_metadata(self, previous: Any) -> dict[str, Any]:
        profile = self._profile_for_run(previous, "agent")
        return {
            "provider": profile.provider,
            "model": profile.model,
            "prompt_version": previous.prompt_version,
            "provider_profile_snapshot": previous.provider_profile_snapshot,
        }

    @staticmethod
    def _profile_for_run(run: Any, stage: str = "agent") -> ProviderProfile:
        snapshot = run.provider_profile_snapshot
        if not isinstance(snapshot, dict):
            raise RuntimeError("LangChain run has no provider profile snapshot")
        staged = snapshot.get(stage)
        return ProviderProfile.model_validate(staged if isinstance(staged, dict) else snapshot)

    @staticmethod
    def _pipeline_metadata(task: Any, key: str, run_id: str) -> dict[str, Any] | None:
        """Read only the pipeline-owned state for the active managed run."""

        value = task.metadata.get(key)
        return value if isinstance(value, dict) and value.get("run_id") == run_id else None

    @staticmethod
    def _has_ocr_artifact(run: Any) -> bool:
        return any(artifact.kind == "ocr" for artifact in run.artifacts)

    def _tool_binding_for(
        self,
        *,
        task: Any,
        run: Any,
        verification_context: bool,
    ) -> tuple[
        frozenset[str],
        dict[str, dict[str, Any]],
        dict[str, tuple[str, ...]],
        dict[str, dict[str, dict[str, Any]]],
    ]:
        """Derive the only legal next MCP calls from authoritative pipeline state.

        Task stage, persisted run artifacts, and MCP-owned tag metadata are the
        source of truth. This keeps the model from spending a complete tool
        round repeating a successful read operation that cannot advance the
        pipeline, without introducing a runner-local workflow state machine.
        """

        def report(stage: TaskStage):
            return (
                frozenset({self._REPORT_TOOL}),
                {self._REPORT_TOOL: {"stage": stage.value}},
                {},
                {},
            )

        if not verification_context:
            if not self._has_ocr_artifact(run):
                if task.asset_path:
                    return frozenset({"ocr_image"}), {}, {}, {}
                return report(TaskStage.OCR)
            if task.stage in {None, TaskStage.QUEUED, TaskStage.STARTING}:
                return report(TaskStage.OCR)
            if task.stage == TaskStage.OCR:
                return report(TaskStage.SOLVING)
            if task.stage == TaskStage.SOLVING and run.solution_candidate is None:
                return (
                    frozenset({self._SUBMIT_TOOL}),
                    {},
                    {},
                    {
                        self._SUBMIT_TOOL: {
                            "problem_json": {
                                "maxLength": 8000,
                                "description": (
                                    "One complete compact Problem JSON string. Keep the entire string under "
                                    "8000 characters and explanation under 1500 characters."
                                ),
                            }
                        }
                    },
                )
            raise RuntimeError("solver cannot derive a legal next pipeline transition")

        if task.stage == TaskStage.VERIFYING:
            return report(TaskStage.TAGGING)
        if task.stage == TaskStage.TAGGING:
            subject = task.subject
            if subject in {"", "auto"}:
                subject = run.solution_candidate.problem.subject
            common = {"subject": subject, "scope": "core"}
            branches = self._pipeline_metadata(task, "_managed_knowledge_branches", run.id)
            selection = self._pipeline_metadata(task, "_managed_tag_selection", run.id)
            errors = self._pipeline_metadata(task, "_managed_error_candidates", run.id)
            if selection is None:
                if branches is None:
                    return (
                        frozenset({self._LIST_TAGS_TOOL}),
                        {self._LIST_TAGS_TOOL: {"dimension": "knowledge", **common}},
                        {},
                        {},
                    )
                branch_ids = [
                    value for value in branches.get("branch_ids", []) if isinstance(value, str)
                ]
                if branch_ids:
                    return (
                        frozenset({self._LIST_TAGS_TOOL}),
                        {self._LIST_TAGS_TOOL: {"dimension": "knowledge", **common}},
                        {self._LIST_TAGS_TOOL: ("branch_ids",)},
                        {
                            self._LIST_TAGS_TOOL: {
                                "branch_ids": {
                                    "items": {"type": "string", "enum": branch_ids},
                                    "minItems": 1,
                                    "maxItems": min(6, len(branch_ids)),
                                    "type": "array",
                                },
                            },
                        },
                    )
                raise RuntimeError("knowledge branch catalog has no selectable branch IDs")
            if errors is None:
                return (
                    frozenset({self._LIST_TAGS_TOOL}),
                    {self._LIST_TAGS_TOOL: {"dimension": "error", **common}},
                    {},
                    {},
                )
            known_errors = {value for value in errors.get("values", []) if isinstance(value, str)}
            missing_errors = set(run.solution_candidate.problem.error_hypothesis) - known_errors
            if missing_errors:
                return frozenset({self._CREATE_TAG_TOOL}), {}, {}, {}
            return report(TaskStage.FINALIZING)
        if task.stage == TaskStage.FINALIZING:
            return (
                frozenset({self._FINALIZE_TOOL}),
                {},
                {},
                {
                    self._FINALIZE_TOOL: {
                        "problem_json": {
                            "maxLength": 8000,
                            "description": (
                                "One complete compact Problem JSON string. Keep the entire string under "
                                "8000 characters and explanation under 1500 characters."
                            ),
                        }
                    }
                },
            )
        raise RuntimeError("verifier cannot derive a legal next pipeline transition")

    def run(self, task_id: str, run_id: str) -> None:
        managed_run = self.run_store.get(run_id)
        is_diagram = managed_run.purpose == RunPurpose.DIAGRAM
        loop = asyncio.new_event_loop()
        task: asyncio.Task[Any] | None = None
        control: AsyncioTaskRunControl | None = None
        control_key = f"diagram:{run_id}" if is_diagram else task_id
        try:
            asyncio.set_event_loop(loop)
            coroutine = (
                self._run_diagram_agent_async(task_id, run_id)
                if is_diagram
                else self._run_async(task_id, run_id)
            )
            task = loop.create_task(coroutine)
            control = AsyncioTaskRunControl(task, loop)
            self._register_control(control_key, control)
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            # cancel() owns the terminal transition; do not overwrite a finalization.
            return
        except Exception as error:
            if is_diagram:
                self._fail_diagram(task_id, run_id, str(error), self._error_code(error))
            else:
                self._fail_start(task_id, run_id, str(error), self._error_code(error))
        finally:
            if control is not None:
                self._clear_control(control_key, control)
            asyncio.set_event_loop(None)
            loop.close()
        if is_diagram:
            self.retry_diagram_if_eligible(task_id, run_id)
        else:
            self.retry_if_eligible(task_id, run_id)
            completed = self.run_store.get(run_id)
            if completed.status == RunStatus.COMPLETED:
                self._ensure_auto_diagram(task_id)
        try:
            factory = self.provider_factory()
            collect_unreferenced_channel_secrets(
                factory.secret_store,
                self.settings_store.provider_channels(),
                self.run_store.list_all(),
            )
        except Exception:
            # Collection is maintenance after a terminal state; failure remains
            # separate from run evidence and cannot rewrite its terminal state.
            logger.exception("LangChain credential reference collection failed")

    def _ensure_auto_diagram(self, task_id: str) -> None:
        """Create the current single slot once; the persisted contract remains multi-slot."""
        with self._admission_lock:
            task = self.task_store.get(task_id)
            if (
                task.problem is None
                or not task.problem.has_diagram
                or not task.asset_path
                or task.diagram_items
            ):
                return
            item = DiagramItem(source_asset_path=task.asset_path)
            self.task_store.add_diagram_item(task_id, item)
        try:
            self.submit_diagram(task_id, item.id)
        except Exception as error:
            self.task_store.update_diagram_item(
                task_id,
                item.id,
                status=DiagramStatus.FAILED,
                needs_review=False,
                last_error=str(error),
                last_error_code="diagram_admission_failed",
            )

    def _fail_diagram(self, task_id: str, run_id: str, message: str, error_code: str) -> None:
        run = self.run_store.get(run_id)
        if run.diagram_item_id:
            with contextlib.suppress(KeyError, StateConflict):
                self.task_store.update_diagram_item(
                    task_id,
                    run.diagram_item_id,
                    expected_active_run_id=run_id,
                    status=DiagramStatus.FAILED,
                    active_run_id=None,
                    needs_review=False,
                    last_error=message,
                    last_error_code=error_code,
                )
        self.run_store.finish(
            run_id,
            RunStatus.FAILED,
            error_code=error_code,
            error_message=message,
        )
        self.run_store.update(
            run_id,
            retryable=self.is_retryable_error(error_code, message),
        )

    def _diagram_rules(self, *, final_review: bool, allow_keep_image: bool) -> str:
        mode = "auto" if allow_keep_image else "tikz"
        phase = "review" if final_review else "generate"
        return render_skill_prompt(
            self._diagram_skill_prompt,
            {
                "decisions": self._diagram_prompts[f"decisions_{phase}_{mode}"],
                "fallback_policy": self._diagram_prompts[f"fallback_policy_{mode}"],
                "source_region_policy": self._diagram_prompts[f"source_region_policy_{mode}"],
            },
        )

    def _image_content(self, asset_path: str) -> dict[str, Any]:
        path = self.asset_store.resolve(asset_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}

    def _diagram_agent_messages(self, run: Any, item: DiagramItem) -> list[Any]:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
        except ImportError as error:
            raise RuntimeError("LangChain core is not installed") from error
        candidate = active_candidate(run, item)
        user_instruction = ""
        if run.diagram_instruction:
            user_instruction = render_skill_prompt(
                self._diagram_prompts["user_instruction"],
                {"instruction": run.diagram_instruction},
            )
        prompt_name = "review_user" if candidate else "initial_user"
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": render_skill_prompt(
                    self._diagram_prompts[prompt_name],
                    {
                        "user_instruction": user_instruction,
                        "tikz_source": candidate.tikz_source if candidate else "",
                    },
                ),
            }
        ]
        if not item.source_asset_path:
            raise RuntimeError("Diagram item has no source asset")
        content.append(self._image_content(item.source_asset_path))
        if candidate and candidate.png_path:
            content.append(self._image_content(candidate.png_path))
        if candidate and candidate.render_error_message:
            content.append(
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "candidate_render_error": {
                                "code": candidate.render_error_code,
                                "message": candidate.render_error_message,
                            }
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
        final_review = len(run_candidates(run, item)) >= int(run.diagram_max_candidates or 0)
        rules = self._diagram_rules(
            final_review=final_review,
            allow_keep_image=run.diagram_mode == DiagramRunMode.AUTO,
        )
        tool_suffix = self._diagram_prompts.get("tool_contract_suffix")
        if tool_suffix:
            rules = f"{rules}\n{tool_suffix}"
        return [SystemMessage(content=rules), HumanMessage(content=content)]

    def _diagram_bridge_followup(self, run: Any, candidate: DiagramCandidate) -> str:
        template = (
            self._diagram_prompts.get("render_result_user") or self._diagram_prompts["review_user"]
        )
        user_instruction = ""
        if run.diagram_instruction:
            user_instruction = render_skill_prompt(
                self._diagram_prompts["user_instruction"],
                {"instruction": run.diagram_instruction},
            )
        return render_skill_prompt(
            template,
            {
                "user_instruction": user_instruction,
                "tikz_source": candidate.tikz_source,
            },
        )

    async def _render_diagram_for_agent(
        self,
        task_id: str,
        run_id: str,
        *,
        timeout: float,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        run = self.run_store.get(run_id)
        task = self.task_store.get(task_id)
        item = next(
            (value for value in task.diagram_items if value.id == run.diagram_item_id),
            None,
        )
        candidate = active_candidate(run, item) if item is not None else None
        if item is None or candidate is None:
            raise RuntimeError("Diagram render checkpoint has no candidate")
        self.run_store.observe_stage(
            run.id, TaskStage.DIAGRAM_RENDERING, "Rendering TikZ candidate"
        )
        try:
            bundle = await asyncio.wait_for(
                asyncio.to_thread(self.tikz_renderer.render, candidate.tikz_source),
                timeout=timeout,
            )
        except TikzRenderError as error:
            if error.code == "renderer_environment_error":
                evidence = error.evidence or str(error)
                review_reason = "TikZ 渲染服务环境异常，需要人工介入修复"
                failed_candidate = DiagramCandidate.model_validate(
                    {
                        **candidate.model_dump(mode="python"),
                        "render_error_code": error.code,
                        "render_error_message": evidence,
                        "review_reason": review_reason,
                    }
                )
                self.task_store.update_diagram_item(
                    task_id,
                    item.id,
                    expected_active_run_id=run.id,
                    candidates=[
                        failed_candidate if value.id == candidate.id else value
                        for value in item.candidates
                    ],
                    status=DiagramStatus.NEEDS_REVIEW,
                    active_run_id=None,
                    needs_review=True,
                    last_error=str(error),
                    last_error_code=error.code,
                )
                self.run_store.finish(
                    run.id,
                    RunStatus.FAILED,
                    error_code=error.code,
                    error_message=str(error),
                )
                self.run_store.update(run.id, retryable=False)
                return (
                    {
                        "ok": False,
                        "terminal": True,
                        "needs_review": True,
                        "candidate_id": candidate.id,
                        "source_sha256": candidate.source_sha256,
                        "render_error": {"code": error.code, "message": str(error)},
                    },
                    None,
                )
            if error.code not in {"invalid_tikz_source", "renderer_failed"}:
                raise
            self.task_store.update_diagram_candidate(
                task_id,
                item.id,
                candidate.id,
                expected_active_run_id=run.id,
                render_error_code=error.code,
                render_error_message=str(error),
            )
            self.task_store.update_diagram_item(
                task_id,
                item.id,
                expected_active_run_id=run.id,
                status=DiagramStatus.GENERATING,
            )
            self.run_store.update(run.id, diagram_step=DiagramRunStep.GENERATE)
            self.run_store.observe_stage(
                run.id,
                TaskStage.DIAGRAM_GENERATING,
                "Revising TikZ after a compile error",
            )
            return (
                {
                    "ok": False,
                    "candidate_id": candidate.id,
                    "source_sha256": candidate.source_sha256,
                    "render_error": {"code": error.code, "message": str(error)},
                },
                None,
            )
        self.task_store.update_diagram_candidate(
            task_id,
            item.id,
            candidate.id,
            expected_active_run_id=run.id,
            svg_path=bundle.svg_path,
            pdf_path=bundle.pdf_path,
            png_path=bundle.png_path,
            renderer_profile_version=bundle.renderer_profile_version,
            base_font_size_pt=bundle.base_font_size_pt,
            canvas_width_em=bundle.canvas_width_em,
            canvas_height_em=bundle.canvas_height_em,
            render_error_code=None,
            render_error_message=None,
        )
        self.task_store.update_diagram_item(
            task_id,
            item.id,
            expected_active_run_id=run.id,
            status=DiagramStatus.REVIEWING,
        )
        self.run_store.update(run.id, diagram_step=DiagramRunStep.REVIEW)
        self.run_store.observe_stage(
            run.id, TaskStage.DIAGRAM_REVIEWING, "Comparing rendered candidate"
        )
        return (
            {
                "ok": True,
                "candidate_id": candidate.id,
                "source_sha256": candidate.source_sha256,
                "renderer_profile_version": bundle.renderer_profile_version,
            },
            self._image_content(bundle.png_path),
        )

    async def _time_out_diagram(self, task_id: str, run_id: str) -> None:
        message = f"LangChain diagram run exceeded {self.timeout_seconds}s timeout"
        run = self.run_store.get(run_id)
        if run.diagram_item_id:
            with contextlib.suppress(KeyError, StateConflict):
                self.task_store.update_diagram_item(
                    task_id,
                    run.diagram_item_id,
                    expected_active_run_id=run_id,
                    status=DiagramStatus.FAILED,
                    active_run_id=None,
                    needs_review=False,
                    last_error=message,
                    last_error_code="process_timeout",
                )
        self.run_store.finish(
            run_id,
            RunStatus.TIMED_OUT,
            error_code="process_timeout",
            error_message=message,
        )

    async def _run_diagram_agent_async(self, task_id: str, run_id: str) -> None:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        except ImportError as error:
            raise RuntimeError("LangChain core is not installed") from error
        run = self.run_store.get(run_id)
        if run.diagram_transport is None:
            raise DiagramModelContractError(
                "diagram run predates the tool protocol; start a fresh reconstruction run"
            )
        profile = self._profile_for_run(run, "diagram")
        factory = self.provider_factory()
        model = factory.create_diagram_model(profile)
        dispatcher = ContractBoundToolDispatcher(
            self.tool_client_factory(),
            task_id=task_id,
            run_id=run_id,
        )
        event_path = self.run_store.base_dir / f"{run_id}.events.jsonl"
        started = time.monotonic()
        messages: list[Any] | None = None
        invalid_recoveries = 0
        tool_error_recoveries = 0
        self.run_store.start(run_id, None, f"runs/{event_path.name}")
        self._event(
            event_path,
            "diagram_agent_started",
            {
                "provider": profile.provider,
                "model": profile.model,
                "transport": run.diagram_transport.value,
            },
        )
        for round_index in range(self.max_tool_rounds):
            remaining = self.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                await self._time_out_diagram(task_id, run_id)
                return
            run = self.run_store.get(run_id)
            task = self.task_store.get(task_id)
            item = next(
                (value for value in task.diagram_items if value.id == run.diagram_item_id),
                None,
            )
            if item is None:
                raise StateConflict("Diagram run no longer has its item")
            if item.active_run_id != run_id:
                if item.status in {
                    DiagramStatus.READY_TIKZ,
                    DiagramStatus.READY_IMAGE,
                    DiagramStatus.NEEDS_REVIEW,
                }:
                    self.run_store.finish(run_id, RunStatus.COMPLETED)
                    return
                raise StateConflict("Diagram run no longer owns its item")
            if run.diagram_step == DiagramRunStep.RENDER:
                try:
                    await self._render_diagram_for_agent(
                        task_id,
                        run_id,
                        timeout=remaining,
                    )
                except TimeoutError:
                    await self._time_out_diagram(task_id, run_id)
                    return
                messages = None
                continue
            if messages is None:
                messages = self._diagram_agent_messages(run, item)
            tool_names = legal_diagram_tools(run, item)
            constants = {name: {"task_id": task_id, "run_id": run_id} for name in tool_names}
            schemas = {
                value["function"]["name"]: value["function"]["parameters"]
                for value in langchain_tool_schemas(tool_names, constants=constants)
            }
            bound_model = factory.bind_managed_tools(
                model,
                profile,
                tool_names=tool_names,
                constants=constants,
                require_call=True,
            )
            try:
                response = await asyncio.wait_for(bound_model.ainvoke(messages), timeout=remaining)
            except TimeoutError:
                await self._time_out_diagram(task_id, run_id)
                return
            self._record_model_usage(run_id, response)
            messages.append(response)
            tool_calls = list(getattr(response, "tool_calls", None) or [])
            invalid_calls = list(getattr(response, "invalid_tool_calls", None) or [])
            raw_calls = getattr(response, "additional_kwargs", {}).get("tool_calls", [])
            if len(tool_calls) != 1 or invalid_calls:
                invalid_recoveries += 1
                call_ids = [str(call.get("id")) for call in tool_calls if call.get("id")]
                invalid_ids, _ = self._invalid_tool_call_ids(invalid_calls, raw_calls)
                call_ids.extend(value for value in invalid_ids if value not in call_ids)
                if call_ids:
                    for call_id in call_ids:
                        messages.append(
                            ToolMessage(
                                content=self._runtime_prompts["invalid_tool_result"],
                                tool_call_id=call_id,
                            )
                        )
                else:
                    messages.pop()
                self._event(
                    event_path,
                    "diagram_invalid_tool_call",
                    {
                        "round": round_index + 1,
                        "valid_calls": len(tool_calls),
                        "invalid_calls": len(invalid_calls),
                        "recovery": invalid_recoveries,
                    },
                )
                if invalid_recoveries > 2:
                    raise DiagramModelContractError(
                        "diagram model did not return exactly one valid tool call"
                    )
                messages.append(
                    SystemMessage(
                        content=render_skill_prompt(
                            self._runtime_prompts["invalid_tool_recovery"],
                            {"truncation_instruction": ""},
                        )
                    )
                )
                continue
            invalid_recoveries = 0
            call = tool_calls[0]
            self._event(
                event_path,
                "diagram_tool_call",
                {"round": round_index + 1, "call": self._tool_call_summary(call)},
            )
            try:
                result = await asyncio.wait_for(
                    dispatcher.call(
                        call["name"],
                        dict(call.get("args") or {}),
                        allowed_parameters=schemas,
                    ),
                    timeout=max(0.01, self.timeout_seconds - (time.monotonic() - started)),
                )
            except TimeoutError:
                await self._time_out_diagram(task_id, run_id)
                return
            except Exception as error:
                tool_error_recoveries += 1
                self.run_store.record_validation_error(
                    run_id,
                    RunValidationError(
                        stage=(
                            TaskStage.DIAGRAM_REVIEWING
                            if run.diagram_step == DiagramRunStep.REVIEW
                            else TaskStage.DIAGRAM_GENERATING
                        ),
                        raw_output=json.dumps(call, ensure_ascii=False, default=str),
                        message=str(error),
                    ),
                )
                messages.append(
                    ToolMessage(
                        content=json.dumps({"error": str(error)}, ensure_ascii=False),
                        tool_call_id=call["id"],
                        status="error",
                    )
                )
                if tool_error_recoveries > 2:
                    raise DiagramModelContractError(str(error)) from error
                messages.append(
                    SystemMessage(
                        content=render_skill_prompt(
                            self._runtime_prompts["tool_execution_recovery"],
                            {
                                "recovery_instruction": self._runtime_prompts[
                                    "transition_recovery_instruction"
                                ]
                            },
                        )
                    )
                )
                continue
            tool_error_recoveries = 0
            image_content: dict[str, Any] | None = None
            payload = result if isinstance(result, dict) else {"result": result}
            if call["name"] == SUBMIT_TIKZ_REVISION:
                remaining = self.timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    await self._time_out_diagram(task_id, run_id)
                    return
                try:
                    payload, image_content = await self._render_diagram_for_agent(
                        task_id,
                        run_id,
                        timeout=remaining,
                    )
                except TimeoutError:
                    await self._time_out_diagram(task_id, run_id)
                    return
            current_run = self.run_store.get(run_id)
            current_task = self.task_store.get(task_id)
            current_item = next(
                (
                    value
                    for value in current_task.diagram_items
                    if value.id == current_run.diagram_item_id
                ),
                None,
            )
            if current_item is None:
                raise StateConflict("Diagram run no longer has its item")
            followup_text = None
            if (
                image_content is not None
                and current_run.diagram_transport == DiagramTransport.MESSAGE_IMAGE_BRIDGE
            ):
                candidate = active_candidate(current_run, current_item)
                if candidate is None:
                    raise StateConflict("Rendered diagram has no active candidate")
                followup_text = self._diagram_bridge_followup(current_run, candidate)
            encoded = encode_diagram_tool_result(
                payload,
                transport=current_run.diagram_transport,
                image_content=image_content,
                followup_text=followup_text,
            )
            messages.append(ToolMessage(content=encoded.tool_content, tool_call_id=call["id"]))
            if encoded.followup_content is not None:
                messages.append(HumanMessage(content=encoded.followup_content))
            if current_item.active_run_id is None:
                self.run_store.finish(run_id, RunStatus.COMPLETED)
                return
        raise DiagramModelContractError("diagram agent exceeded its bounded tool rounds")

    def _record_model_usage(self, run_id: str, response: Any) -> None:
        usage = getattr(response, "usage_metadata", None) or {}
        current = self.run_store.get(run_id)
        updates: dict[str, Any] = {}
        for field in ("input_tokens", "output_tokens"):
            delta = usage.get(field)
            if isinstance(delta, int):
                updates[field] = int(getattr(current, field) or 0) + delta
        details = usage.get("input_token_details") or {}
        cache = details.get("cache_read") if isinstance(details, dict) else None
        if isinstance(cache, int):
            updates["cache_tokens"] = int(current.cache_tokens or 0) + cache
        if updates:
            self.run_store.update(run_id, **updates)

    @staticmethod
    def _error_code(error: Exception) -> str:
        explicit_code = getattr(error, "code", None)
        if isinstance(explicit_code, str) and explicit_code:
            return explicit_code
        status = provider_http_status(error)
        message = str(error).lower()
        if status in {401, 403}:
            return "provider_authorization"
        if (status == 404 and "model" in message) or (
            "not_found" in message and "model" in message
        ):
            return "provider_model_unavailable"
        if status == 429:
            return "rate_limit"
        if status is not None and 500 <= status <= 599:
            return "provider_unavailable"
        try:
            import httpx

            transport_error = isinstance(error, httpx.TransportError)
        except ImportError:
            transport_error = False
        if (
            isinstance(error, (ConnectionError, TimeoutError, asyncio.TimeoutError))
            or transport_error
        ):
            return "network_error"
        if type(error).__name__ in {"APIConnectionError", "APITimeoutError"}:
            return "network_error"
        return "runner_error"

    async def _run_async(self, task_id: str, run_id: str) -> None:
        run = self.run_store.get(run_id)
        profile = self._profile_for_run(run, "agent")
        review_profile = self._profile_for_run(run, "review")
        model = self.provider_factory().create_chat_model(profile)
        review_model = self.provider_factory().create_chat_model(review_profile)
        factory = self.provider_factory()
        dispatcher = ContractBoundToolDispatcher(
            self.tool_client_factory(),
            task_id=task_id,
            run_id=run_id,
        )
        started = time.monotonic()
        event_path = self.run_store.base_dir / f"{run_id}.events.jsonl"
        self._event(
            event_path,
            "run_started",
            {
                "provider": profile.provider,
                "model": profile.model,
                "profile_version": profile.version,
                "policy_version": run.provider_profile_snapshot.get("policy_version")
                if isinstance(run.provider_profile_snapshot, dict)
                else None,
                "stages": {
                    "agent": {
                        "provider": profile.provider,
                        "model": profile.model,
                        "version": profile.version,
                    },
                    "review": {
                        "provider": review_profile.provider,
                        "model": review_profile.model,
                        "version": review_profile.version,
                    },
                    "vision": (
                        {
                            "provider": run.provider_profile_snapshot["vision"].get("provider"),
                            "model": run.provider_profile_snapshot["vision"].get("model"),
                            "version": run.provider_profile_snapshot["vision"].get("version"),
                        }
                        if isinstance(run.provider_profile_snapshot, dict)
                        and isinstance(run.provider_profile_snapshot.get("vision"), dict)
                        else None
                    ),
                },
            },
        )
        self.run_store.start(run_id, None, f"runs/{event_path.name}")
        self._set_stage(task_id, run_id, TaskStage.STARTING, "LangChain provider started")

        try:
            from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        except ImportError as error:
            raise RuntimeError("LangChain core is not installed") from error

        task = self.task_store.get(task_id)
        task_context = {
            "task_id": task.id,
            "run_id": run_id,
            "subject": task.subject,
            "asset_path": task.asset_path,
            "question_no": task.metadata.get("question_no"),
            "source": task.metadata.get("source"),
            "notes": task.metadata.get("notes") or "",
        }
        variation_request = task.metadata.get("variation_request")
        if isinstance(variation_request, dict):
            task_context["variation_request"] = variation_request
            task_context["parent_problem"] = task.metadata.get("variation_parent_problem")
        solver_rules = render_skill_prompt(
            self._runtime_prompts["solver_system"],
            {
                "task_id": task_id,
                "run_id": run_id,
                "skill_pack": self._skill_pack,
            },
        )
        messages: list[Any] = [
            SystemMessage(content=solver_rules),
            HumanMessage(
                content=render_skill_prompt(
                    self._runtime_prompts["solver_initial_user"],
                    {
                        "task_context_json": json.dumps(
                            task_context, ensure_ascii=False, separators=(",", ":")
                        )
                    },
                )
            ),
        ]
        solver_context_ready = False
        invalid_tool_recoveries = 0
        tool_error_recoveries = 0
        verification_context = False
        for _round in range(self.max_tool_rounds):
            remaining = self.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                await self._time_out(task_id, run_id)
                return
            current_task = self.task_store.get(task_id)
            current_run = self.run_store.get(run_id)
            if (
                not verification_context
                and not solver_context_ready
                and current_task.stage == TaskStage.SOLVING
            ):
                ocr_artifact = next(
                    (artifact for artifact in current_run.artifacts if artifact.kind == "ocr"),
                    None,
                )
                solver_input = {
                    "task_context": task_context,
                    "ocr_result": ocr_artifact.parsed_output if ocr_artifact is not None else None,
                }
                messages = [
                    SystemMessage(
                        content=f"{solver_rules}\n{self._runtime_prompts['solver_ready_suffix']}"
                    ),
                    HumanMessage(
                        content=render_skill_prompt(
                            self._runtime_prompts["solver_ready_user"],
                            {
                                "solver_input_json": json.dumps(
                                    solver_input,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                )
                            },
                        )
                    ),
                ]
                solver_context_ready = True
                self._event(event_path, "solver_context_started", {"round": _round + 1})
            tool_names, constants, required_arguments, parameter_overrides = self._tool_binding_for(
                task=current_task,
                run=current_run,
                verification_context=verification_context,
            )
            allowed_schemas = {
                item["function"]["name"]: item["function"]["parameters"]
                for item in langchain_tool_schemas(
                    tool_names,
                    constants=constants,
                    required_arguments=required_arguments,
                    parameter_overrides=parameter_overrides,
                )
            }
            bound_model = factory.bind_managed_tools(
                review_model if verification_context else model,
                review_profile if verification_context else profile,
                tool_names=tool_names,
                constants=constants,
                required_arguments=required_arguments,
                parameter_overrides=parameter_overrides,
            )
            try:
                response = await asyncio.wait_for(bound_model.ainvoke(messages), timeout=remaining)
            except TimeoutError:
                await self._time_out(task_id, run_id)
                return
            usage = getattr(response, "usage_metadata", None) or {}
            metadata = getattr(response, "response_metadata", None) or {}
            cost = usage.get("cost", metadata.get("cost"))
            current_usage = self.run_store.get(run_id)
            usage_update: dict[str, Any] = {}
            for field in ("input_tokens", "output_tokens"):
                delta = usage.get(field)
                if isinstance(delta, int):
                    usage_update[field] = int(getattr(current_usage, field) or 0) + delta
            input_details = usage.get("input_token_details") or {}
            cache_delta = (
                input_details.get("cache_read") if isinstance(input_details, dict) else None
            )
            if isinstance(cache_delta, int):
                usage_update["cache_tokens"] = int(current_usage.cache_tokens or 0) + cache_delta
            if isinstance(cost, (int, float)):
                usage_update["cost"] = float(current_usage.cost or 0) + float(cost)
            if usage_update:
                self.run_store.update(run_id, **usage_update)
            self._event(
                event_path,
                "model_response",
                {
                    "stage": "review" if verification_context else "agent",
                    "round": _round + 1,
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "cost": cost,
                },
            )
            messages.append(response)
            tool_calls = list(getattr(response, "tool_calls", None) or [])
            if not tool_calls:
                invalid_calls = list(getattr(response, "invalid_tool_calls", None) or [])
                raw_calls = getattr(response, "additional_kwargs", {}).get("tool_calls", [])
                if invalid_calls and invalid_tool_recoveries < 2:
                    invalid_tool_recoveries += 1
                    invalid_call_ids, invalid_call_count = self._invalid_tool_call_ids(
                        invalid_calls,
                        raw_calls,
                    )
                    output_truncated = metadata.get("finish_reason") == "length"
                    if output_truncated:
                        messages.pop()
                        history_action = "truncated_response_removed"
                    elif invalid_call_count and len(invalid_call_ids) == invalid_call_count:
                        for call_id in invalid_call_ids:
                            messages.append(
                                ToolMessage(
                                    content=self._runtime_prompts["invalid_tool_result"],
                                    tool_call_id=call_id,
                                )
                            )
                        history_action = "tool_results"
                    else:
                        # A malformed call without an ID cannot be acknowledged under the
                        # provider protocol, so exclude the assistant response from history.
                        messages.pop()
                        history_action = "response_removed"
                    self._event(
                        event_path,
                        "invalid_tool_recovery",
                        {
                            "stage": "review" if verification_context else "agent",
                            "round": _round + 1,
                            "count": len(invalid_calls),
                            "recovery": invalid_tool_recoveries,
                            "history_action": history_action,
                        },
                    )
                    messages.append(
                        SystemMessage(
                            content=render_skill_prompt(
                                self._runtime_prompts["invalid_tool_recovery"],
                                {
                                    "truncation_instruction": (
                                        self._runtime_prompts["truncated_output_instruction"]
                                        if output_truncated
                                        else ""
                                    )
                                },
                            )
                        )
                    )
                    continue
                self._event(
                    event_path,
                    "model_no_tool_call",
                    {
                        "stage": "review" if verification_context else "agent",
                        "round": _round + 1,
                        "content_bytes": len(str(getattr(response, "content", "")).encode("utf-8")),
                        "finish_reason": metadata.get("finish_reason"),
                        "raw_tool_calls_count": len(raw_calls)
                        if isinstance(raw_calls, list)
                        else 0,
                        "invalid_tool_calls": [
                            {
                                "name": item.get("name"),
                                "args_bytes": len(str(item.get("args", "")).encode("utf-8")),
                                "error": str(item.get("error", ""))[:256],
                            }
                            for item in invalid_calls
                            if isinstance(item, dict)
                        ],
                    },
                )
                await self._not_finalized(
                    task_id, run_id, "model returned text without finalizing the task"
                )
                return
            invalid_tool_recoveries = 0
            remaining = self.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                await self._time_out(task_id, run_id)
                return
            try:
                results = await asyncio.wait_for(
                    dispatcher.call_many(
                        tool_calls,
                        allowed_parameters=allowed_schemas,
                        fixed_arguments=constants,
                    ),
                    timeout=remaining,
                )
            except TimeoutError:
                await self._time_out(task_id, run_id)
                return
            self._event(
                event_path,
                "tool_calls",
                {
                    "round": _round + 1,
                    "count": len(tool_calls),
                    "tools": [call.get("name") for call in tool_calls],
                    "calls": [self._tool_call_summary(call) for call in tool_calls],
                    "results": [self._tool_result_summary(result) for result in results],
                },
            )
            for call, result in zip(tool_calls, results, strict=True):
                content = json.dumps(
                    {"error": str(result)} if isinstance(result, Exception) else result,
                    ensure_ascii=False,
                    default=str,
                )
                messages.append(ToolMessage(content=content, tool_call_id=call["id"]))
            tool_errors = [result for result in results if isinstance(result, Exception)]
            if tool_errors and tool_error_recoveries < 2:
                tool_error_recoveries += 1
                finalizing = tool_names == frozenset({self._FINALIZE_TOOL})
                self._event(
                    event_path,
                    "tool_execution_recovery",
                    {
                        "stage": "review" if verification_context else "agent",
                        "round": _round + 1,
                        "error_count": len(tool_errors),
                        "recovery": tool_error_recoveries,
                        "binding": "finalize" if finalizing else "current_transition",
                    },
                )
                messages.append(
                    SystemMessage(
                        content=render_skill_prompt(
                            self._runtime_prompts["tool_execution_recovery"],
                            {
                                "recovery_instruction": self._runtime_prompts[
                                    "finalize_recovery_instruction"
                                    if finalizing
                                    else "transition_recovery_instruction"
                                ]
                            },
                        )
                    )
                )
            elif not tool_errors:
                tool_error_recoveries = 0
            current = self.task_store.get(task_id)
            self._observe_task(run_id, task_id)
            if current.status == TaskStatus.COMPLETED:
                self.run_store.finish(run_id, RunStatus.COMPLETED)
                return
            if current.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
                self.run_store.finish(
                    run_id,
                    RunStatus.CANCELLED
                    if current.status == TaskStatus.CANCELLED
                    else RunStatus.FAILED,
                    error_code=current.last_error_code,
                    error_message=current.last_error,
                )
                return
            stored_run = self.run_store.get(run_id)
            if not verification_context and stored_run.solution_candidate is not None:
                candidate_context = {
                    "problem": stored_run.solution_candidate.problem.model_dump(mode="json"),
                    "review_reason": stored_run.solution_candidate.review_reason,
                    "student_response_status": stored_run.solution_candidate.student_response_status,
                }
                verifier_rules = render_skill_prompt(
                    self._runtime_prompts["verifier_system"],
                    {
                        "task_id": task_id,
                        "run_id": run_id,
                        "skill_pack": self._skill_pack,
                    },
                )
                self.run_store.begin_verification(run_id)
                self._set_stage(
                    task_id, run_id, TaskStage.VERIFYING, "LangChain independent verifier started"
                )
                messages = [
                    SystemMessage(content=verifier_rules),
                    HumanMessage(
                        content=render_skill_prompt(
                            self._runtime_prompts["verifier_user"],
                            {
                                "task_context_json": json.dumps(
                                    task_context,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                                "candidate_context_json": json.dumps(
                                    candidate_context,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            },
                        )
                    ),
                ]
                verification_context = True
                self._event(event_path, "verification_started", {"round": _round + 1})
            self.run_store.heartbeat(run_id)
        await self._not_finalized(task_id, run_id, "LangChain tool loop reached its 24-round limit")

    @staticmethod
    def _tool_call_summary(call: dict[str, Any]) -> dict[str, Any]:
        """Persist stable, non-content evidence for a canonical tool request."""

        arguments = call.get("args")
        if not isinstance(arguments, dict):
            arguments = {}
        encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
        summary: dict[str, Any] = {
            "name": call.get("name"),
            "argument_keys": sorted(arguments),
            "arguments_fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16],
        }
        for key in ("stage", "dimension", "scope"):
            value = arguments.get(key)
            if isinstance(value, str):
                summary[key] = value
        branch_ids = arguments.get("branch_ids")
        if isinstance(branch_ids, list):
            summary["branch_ids_count"] = len(branch_ids)
        for key in ("problem_json", "error", "message"):
            value = arguments.get(key)
            if isinstance(value, str):
                summary[f"{key}_bytes"] = len(value.encode("utf-8"))
        return summary

    @staticmethod
    def _invalid_tool_call_ids(
        invalid_calls: list[Any],
        raw_calls: Any,
    ) -> tuple[list[str], int]:
        """Return complete call IDs for protocol-safe invalid-call acknowledgement."""

        declared_calls = raw_calls if isinstance(raw_calls, list) and raw_calls else invalid_calls
        ids: list[str] = []
        for call in declared_calls:
            call_id = call.get("id") if isinstance(call, dict) else None
            if isinstance(call_id, str) and call_id and call_id not in ids:
                ids.append(call_id)
        return ids, len(declared_calls)

    @staticmethod
    def _tool_result_summary(result: Any) -> dict[str, Any]:
        """Persist execution outcome without retaining tool output or task content."""

        if not isinstance(result, Exception):
            return {"ok": True}
        message = str(result)
        return {
            "ok": False,
            "error_type": type(result).__name__,
            "error_fingerprint": hashlib.sha256(message.encode("utf-8")).hexdigest()[:16],
            "error_bytes": len(message.encode("utf-8")),
        }

    @staticmethod
    def _event(path: Path, event: str, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        safe = {
            key: value
            for key, value in payload.items()
            if key not in {"secret", "api_key", "credential", "credential_ref"}
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"ts": datetime.now(UTC).isoformat(), "event": event, **safe},
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

    async def _time_out(self, task_id: str, run_id: str) -> None:
        message = f"LangChain exceeded {self.timeout_seconds}s timeout"
        try:
            self.task_store.transition(
                task_id,
                expected_statuses={TaskStatus.PROCESSING},
                expected_active_run_id=run_id,
                status=TaskStatus.FAILED,
                active_run_id=None,
                last_error=message,
                last_error_code="process_timeout",
            )
        except StateConflict:
            return
        self.run_store.finish(
            run_id, RunStatus.TIMED_OUT, error_code="process_timeout", error_message=message
        )

    async def _not_finalized(self, task_id: str, run_id: str, message: str) -> None:
        try:
            self.task_store.transition(
                task_id,
                expected_statuses={TaskStatus.PROCESSING},
                expected_active_run_id=run_id,
                status=TaskStatus.FAILED,
                active_run_id=None,
                last_error=message,
                last_error_code="not_finalized",
            )
        except StateConflict:
            return
        self.run_store.finish(
            run_id, RunStatus.FAILED, error_code="not_finalized", error_message=message
        )


__all__ = ["LangChainRunner"]
