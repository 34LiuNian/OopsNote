from __future__ import annotations

from pathlib import Path
from typing import Any

from .agents.agent_flow import AgentOrchestrator, LLMAgent, PromptTemplate
from .agents.extractor import LLMOcrExtractor, OcrExtractor, OcrRouter
from .agents.pipeline import AgentPipeline, PipelineDependencies
from .agents.stages import Archiver, HandwrittenExtractor, ProblemRebuilder, SolutionWriter, TaggingProfiler
from .clients import OpenAIClient, StubAIClient, build_client_for_agent
from .config import AppConfig
from .llm_schemas import SolverOutput, TaggerOutput
from .repository import ArchiveStore, FileTaskRepository, InMemoryTaskRepository
from .services.agent_settings import AgentSettingsService
from .services.tasks_service import TasksService
from .storage import LocalAssetStore
from .tags import tag_store


def build_repository(*, config: AppConfig):
    if config.running_under_pytest or (not config.persist_tasks):
        return InMemoryTaskRepository()
    return FileTaskRepository(base_dir=Path(config.tasks_dir) if config.tasks_dir else None)


def build_agent_settings_service() -> AgentSettingsService:
    from .agent_settings import AgentEnableSettingsStore, AgentModelSettingsStore, AgentThinkingSettingsStore

    agent_model_store = AgentModelSettingsStore()
    agent_enable_store = AgentEnableSettingsStore()
    agent_thinking_store = AgentThinkingSettingsStore()
    return AgentSettingsService(
        model_store=agent_model_store,
        enable_store=agent_enable_store,
        thinking_store=agent_thinking_store,
    )


def build_ai_client(*, config: AppConfig):
    if config.openai_api_key:
        return OpenAIClient(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url,
            model=config.openai_model,
            temperature=config.openai_temperature,
        )
    return StubAIClient()


def build_pipeline(
    *,
    ai_client,
    agent_config_bundle: Any,
    agent_settings_service: AgentSettingsService,
    archive_store: ArchiveStore,
) -> AgentPipeline:
    prompt_dir = Path(__file__).parent / "agents" / "prompts"

    def _load_prompt(name: str) -> PromptTemplate:
        return PromptTemplate.from_file(prompt_dir / f"{name}.txt")

    solver_client = build_client_for_agent("SOLVER", ai_client, bundle=agent_config_bundle)
    tagger_client = build_client_for_agent("TAGGER", ai_client, bundle=agent_config_bundle)

    agent_orchestrator = AgentOrchestrator(
        solver=LLMAgent(
            "solver",
            solver_client,
            _load_prompt("solver"),
            ("answer", "explanation", "short_answer"),
            response_model=SolverOutput,
            model_resolver=agent_settings_service.resolve_saved_model,
        ),
        tagger=LLMAgent(
            "tagger",
            tagger_client,
            _load_prompt("tagger"),
            ("knowledge_points", "question_type", "skills", "error_hypothesis", "recommended_actions"),
            response_model=TaggerOutput,
            model_resolver=agent_settings_service.resolve_saved_model,
        ),
        is_enabled=agent_settings_service.is_agent_enabled,
        thinking_resolver=agent_settings_service.is_agent_thinking,
    )

    rebuilder = ProblemRebuilder()
    extractor = HandwrittenExtractor(rebuilder=rebuilder)
    ocr_client = build_client_for_agent("OCR", ai_client, bundle=agent_config_bundle)
    ocr_extractor = OcrRouter(
        base_extractor=OcrExtractor(),
        llm_extractor=LLMOcrExtractor(ocr_client),
        model_resolver=agent_settings_service.resolve_saved_model,
    )

    return AgentPipeline(
        PipelineDependencies(
            extractor=extractor,
            solution_writer=SolutionWriter(ai_client),
            tagger=TaggingProfiler(ai_client),
            archiver=Archiver(),
            archive_store=archive_store,
            ocr_extractor=ocr_extractor,
        ),
        orchestrator=agent_orchestrator,
    )


def build_tasks_service(*, repository, pipeline: AgentPipeline, asset_store: LocalAssetStore) -> TasksService:
    return TasksService(
        repository=repository,
        pipeline=pipeline,
        asset_store=asset_store,
        tag_store=tag_store,
    )
