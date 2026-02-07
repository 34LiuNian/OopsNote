from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
import urllib.parse
import sys
import time
import uuid
import logging
import asyncio
import threading
from datetime import datetime, timezone
import queue

from pathlib import Path

try:
    from dotenv import load_dotenv

    # Avoid making pytest runs depend on local developer secrets/config.
    # You can still force-enable dotenv in tests by unsetting PYTEST_CURRENT_TEST.
    if "PYTEST_CURRENT_TEST" not in os.environ and os.getenv("AI_MISTAKE_ORGANIZER_DISABLE_DOTENV") != "true":
        _backend_root = Path(__file__).resolve().parents[1]
        load_dotenv(_backend_root / ".env")
except Exception:
    # Optional dependency; backend still works if env vars are provided by the process.
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from pathlib import Path

from .agents.agent_flow import AgentOrchestrator, LLMAgent, PromptTemplate
from .agents.extractor import LLMOcrExtractor, OcrExtractor, OcrRouter
from .agents.pipeline import AgentPipeline, PipelineDependencies
from .agents.stages import Archiver, HandwrittenExtractor, MultiProblemDetector, ProblemRebuilder, SolutionWriter, TaggingProfiler
from .agent_settings import (
    AgentEnableSettings,
    AgentEnableSettingsStore,
    AgentModelSettings,
    AgentModelSettingsStore,
    AgentThinkingSettings,
    AgentThinkingSettingsStore,
)
from .clients import (
    OpenAIClient,
    StubAIClient,
    build_client_for_agent,
    load_agent_config_bundle,
)
from .llm_schemas import SolverOutput, TaggerOutput
from .models import (
    AgentModelsResponse,
    AgentModelsUpdateRequest,
    AgentEnabledResponse,
    AgentEnabledUpdateRequest,
    AgentThinkingResponse,
    AgentThinkingUpdateRequest,
    ModelsResponse,
    ModelSummary,
    OverrideProblemRequest,
    ProblemsResponse,
    ProblemSummary,
    RetagRequest,
    TasksResponse,
    TaskSummary,
    TaskCreateRequest,
    TaskResponse,
    TaskStatus,
    UploadRequest,
)
from .tags import (
    TagCreateRequest,
    TagDimension,
    TagDimensionsResponse,
    TagDimensionsUpdateRequest,
    TagsResponse,
    tag_store,
)
from .repository import ArchiveStore, FileTaskRepository, InMemoryTaskRepository
from .storage import LocalAssetStore
from .request_context import reset_request_id, set_request_id
from .trace import trace_event
from .app_state import BackendState
from .api.health import router as health_router
from .api.tags import router as tags_router
from .api.agent_settings import router as agent_settings_router
from .api.tasks import router as tasks_router
from .api.problems import router as problems_router
from .api.models import router as models_router
from .api.latex import router as latex_router
from .services.agent_settings import AgentSettingsService
from .services.tasks_service import TasksService
from .services.models_service import ModelsService

logger = logging.getLogger(__name__)

# Uvicorn's --log-level primarily affects uvicorn.* loggers.
# Make sure our app logs (including INFO) are emitted when debugging.
_app_log_level = os.getenv("APP_LOG_LEVEL")
if os.getenv("AI_DEBUG_LLM", "false").lower() == "true" and not _app_log_level:
    _app_log_level = "INFO"
if _app_log_level:
    logging.getLogger().setLevel(getattr(logging, _app_log_level.upper(), logging.INFO))


class _DropHealthAccessLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        # Uvicorn access log format includes: "GET /health HTTP/1.1"
        if " /health " in message:
            return False
        # Avoid log spam from frontend polling and SSE progress streams.
        if "GET /tasks?active_only=true" in message:
            return False
        if " /tasks/" in message and " /events " in message:
            return False
        if "OPTIONS /tasks/" in message and " /process?background=true" in message:
            return False
        return True


# Avoid log spam from frontend/backend connectivity checks.
logging.getLogger("uvicorn.access").addFilter(_DropHealthAccessLogs())


class _TaskEventBroker:
    """In-memory pub/sub for per-task SSE events.

    This enables true streaming (push) from background worker threads to async SSE handlers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[queue.Queue[tuple[str, dict[str, object]]]]] = {}

    def subscribe(self, task_id: str) -> queue.Queue[tuple[str, dict[str, object]]]:
        q: queue.Queue[tuple[str, dict[str, object]]] = queue.Queue(maxsize=1000)
        with self._lock:
            self._subscribers.setdefault(task_id, set()).add(q)
        return q

    def unsubscribe(self, task_id: str, q: queue.Queue[tuple[str, dict[str, object]]]) -> None:
        with self._lock:
            subs = self._subscribers.get(task_id)
            if not subs:
                return
            subs.discard(q)
            if not subs:
                self._subscribers.pop(task_id, None)

    def publish(self, task_id: str, event: str, payload: dict[str, object]) -> None:
        with self._lock:
            subs = list(self._subscribers.get(task_id, set()))

        for q in subs:
            try:
                q.put_nowait((event, payload))
            except Exception:
                # Drop on overload; streaming must not block the worker.
                pass


_event_broker = _TaskEventBroker()


class _TaskCancelled(Exception):
    pass


_task_stream_lock = threading.Lock()
_task_stream_cache: dict[str, str] = {}


def _task_stream_dir() -> Path:
    configured = os.getenv("TASK_STREAM_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "storage" / "task_streams"


def _task_stream_path(task_id: str) -> Path:
    out_dir = _task_stream_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{task_id}.txt"


def _read_text_tail(path: Path, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return ""
    except Exception:
        return ""

    # UTF-8 worst-case is 4 bytes/char; read a bit extra to avoid truncation.
    max_bytes = max_chars * 4
    start = max(0, size - max_bytes)
    try:
        with path.open("rb") as f:
            if start:
                f.seek(start)
            data = f.read()
        text = data.decode("utf-8", errors="ignore")
        return text[-max_chars:] if len(text) > max_chars else text
    except Exception:
        return ""

_task_cancel_lock = threading.Lock()
_task_cancelled: set[str] = set()


def _is_task_cancelled(task_id: str) -> bool:
    with _task_cancel_lock:
        return task_id in _task_cancelled


def _append_task_stream(task_id: str, delta: str) -> None:
    if not delta:
        return
    max_chars = _int_env("TASK_STREAM_CACHE_MAX_CHARS", 200_000)
    with _task_stream_lock:
        prev = _task_stream_cache.get(task_id, "")
        next_text = prev + delta
        if max_chars > 0 and len(next_text) > max_chars:
            next_text = next_text[-max_chars:]
        _task_stream_cache[task_id] = next_text

        # Best-effort persistence so refresh/restart can recover history.
        try:
            _task_stream_path(task_id).open("a", encoding="utf-8").write(delta)
        except Exception:
            pass


def _get_task_stream(task_id: str) -> str:
    with _task_stream_lock:
        cached = _task_stream_cache.get(task_id)
        if cached is not None:
            return cached

        # On cold start / after restart: lazy-load from persisted file.
        max_chars = _int_env("TASK_STREAM_CACHE_MAX_CHARS", 200_000)
        text = _read_text_tail(_task_stream_path(task_id), max_chars)
        _task_stream_cache[task_id] = text
        return text


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default

app = FastAPI(title="AI Mistake Organizer Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _request_logging_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = set_request_id(rid)
    started = time.perf_counter()
    # Avoid log/trace spam from health checks.
    is_health = request.url.path == "/health"
    if not is_health:
        logger.info("HTTP in rid=%s %s %s", rid, request.method, request.url.path)
        trace_event(
            "http_in",
            method=request.method,
            path=request.url.path,
            query=str(request.url.query),
            user_agent=request.headers.get("user-agent"),
            origin=request.headers.get("origin"),
        )
    try:
        response = await call_next(request)
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        status = getattr(locals().get("response"), "status_code", "-")
        if not is_health:
            logger.info("HTTP out rid=%s status=%s ms=%.1f", rid, status, elapsed_ms)
            trace_event("http_out", status=status, ms=elapsed_ms)
        reset_request_id(token)

    response.headers["x-request-id"] = rid
    return response

_persist_tasks = os.getenv("PERSIST_TASKS", "true").lower() == "true"
_tasks_dir = os.getenv("TASKS_DIR")

repository = (
    InMemoryTaskRepository()
    if ("pytest" in sys.modules) or ("PYTEST_CURRENT_TEST" in os.environ) or (not _persist_tasks)
    else FileTaskRepository(base_dir=Path(_tasks_dir) if _tasks_dir else None)
)
archive_store = ArchiveStore()
asset_store = LocalAssetStore()
agent_model_store = AgentModelSettingsStore()
agent_enable_store = AgentEnableSettingsStore()
agent_thinking_store = AgentThinkingSettingsStore()
agent_settings_service = AgentSettingsService(
    model_store=agent_model_store,
    enable_store=agent_enable_store,
    thinking_store=agent_thinking_store,
)
_models_cache: list[dict[str, object]] | None = None
_ai_gateway_status: dict[str, object] = {"checked": False}


def _models_cache_getter() -> list[dict[str, object]] | None:
    return _models_cache


def _models_cache_setter(value: list[dict[str, object]] | None) -> None:
    global _models_cache
    _models_cache = value


def _resolve_saved_model(agent: str) -> str | None:
    # Backwards-compatible helper for places that still reference this symbol.
    return agent_settings_service.resolve_saved_model(agent)

# Keep automated tests deterministic (avoid calling external gateways).
# Note: during pytest collection, PYTEST_CURRENT_TEST may not be set yet.
_running_under_pytest = ("pytest" in sys.modules) or ("PYTEST_CURRENT_TEST" in os.environ)

openai_api_key = None if _running_under_pytest else os.getenv("OPENAI_API_KEY")
agent_orchestrator: AgentOrchestrator | None = None

agent_config_path = os.getenv("AGENT_CONFIG_PATH") or os.getenv("AI_AGENT_CONFIG")
agent_config_bundle = load_agent_config_bundle(agent_config_path)

if openai_api_key:
    ai_client = OpenAIClient(
        api_key=openai_api_key,
        base_url=os.getenv("OPENAI_BASE_URL"),
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=_float_env("OPENAI_TEMPERATURE", 0.2),
    )
else:
    ai_client = StubAIClient()

models_service = ModelsService(
    guess_config=lambda: _guess_openai_gateway_config(),
    fetch_models=lambda base_url, api_key, authorization, auth_header_name, timeout_seconds: _fetch_openai_models(
        base_url,
        api_key,
        authorization,
        auth_header_name,
        timeout_seconds,
    ),
    cache_getter=_models_cache_getter,
    cache_setter=_models_cache_setter,
)

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
        model_resolver=_resolve_saved_model,
    ),
    tagger=LLMAgent(
        "tagger",
        tagger_client,
        _load_prompt("tagger"),
        ("knowledge_points", "question_type", "skills", "error_hypothesis", "recommended_actions"),
        response_model=TaggerOutput,
        model_resolver=_resolve_saved_model,
    ),
    is_enabled=agent_settings_service.is_agent_enabled,
    thinking_resolver=agent_settings_service.is_agent_thinking,
)
detector = MultiProblemDetector()
rebuilder = ProblemRebuilder()
extractor = HandwrittenExtractor(detector=detector, rebuilder=rebuilder)
ocr_client = build_client_for_agent("OCR", ai_client, bundle=agent_config_bundle)
ocr_extractor = OcrRouter(
    base_extractor=OcrExtractor(),
    llm_extractor=LLMOcrExtractor(ocr_client),
    model_resolver=agent_settings_service.resolve_saved_model,
)
pipeline = AgentPipeline(
    PipelineDependencies(
        extractor=extractor,
        detector=detector,
        rebuilder=rebuilder,
        solution_writer=SolutionWriter(ai_client),
        tagger=TaggingProfiler(ai_client),
        archiver=Archiver(),
        archive_store=archive_store,
        ocr_extractor=ocr_extractor,
    ),
    orchestrator=agent_orchestrator,
)

tasks_service = TasksService(
    repository=repository,
    pipeline=pipeline,
    asset_store=asset_store,
    tag_store=tag_store,
)

# Attach shared dependencies for routers (helps decouple route modules from globals).
app.state.oops = BackendState(
    repository=repository,
    ai_gateway_status=_ai_gateway_status,
    agent_settings=agent_settings_service,
    tasks=tasks_service,
    models=models_service,
)
app.include_router(health_router)
app.include_router(tags_router)
app.include_router(agent_settings_router)
app.include_router(tasks_router)
app.include_router(problems_router)
app.include_router(models_router)
app.include_router(latex_router)


def _probe_openai_gateway(base_url: str, timeout_seconds: float = 1.2) -> tuple[bool, str]:
    """Best-effort reachability probe.

    Treat any HTTP response (including 401/403/404) as "reachable".
    Only connection/timeout errors count as unreachable.
    """

    url = base_url.rstrip("/") + "/models"
    request = urllib.request.Request(url, headers={"Content-Type": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return True, f"http_{response.status}"
    except urllib.error.HTTPError as exc:
        # Gateway is up; auth/config might be wrong.
        return True, f"http_{exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
def _collect_openai_gateway_urls() -> list[tuple[str, str]]:
    """Collect configured OpenAI-compatible base URLs from env + agent config.

    Returns a list of (label, base_url).
    """

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(label: str, value: str | None) -> None:
        if not value:
            return
        url = str(value).strip()
        if not url:
            return
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return
        norm = url.rstrip("/")
        if norm in seen:
            return
        seen.add(norm)
        candidates.append((label, norm))

    _add("env:OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL"))
    for name in ["SOLVER", "TAGGER", "OCR"]:
        _add(f"env:AGENT_{name}_BASE_URL", os.getenv(f"AGENT_{name}_BASE_URL"))

    try:
        default_cfg = agent_config_bundle.default if agent_config_bundle else None
        if default_cfg and default_cfg.provider == "openai":
            _add("toml:default.base_url", default_cfg.base_url)
    except Exception:
        pass

    try:
        agents_cfg = agent_config_bundle.agents if agent_config_bundle else None
        if agents_cfg:
            for name, cfg in agents_cfg.items():
                if cfg and cfg.provider == "openai":
                    _add(f"toml:agents.{name}.base_url", cfg.base_url)
    except Exception:
        pass

    return candidates


"""Tasks endpoints were moved to backend/app/api/tasks.py."""


_processing_lock = threading.Lock()
_processing_inflight: set[str] = set()

_task_queue_maxsize = _int_env("TASK_QUEUE_MAXSIZE", 1000)
_task_queue: queue.Queue[str] = (
    queue.Queue(maxsize=_task_queue_maxsize) if _task_queue_maxsize > 0 else queue.Queue()
)

_workers_lock = threading.Lock()
_worker_threads: list[threading.Thread] = []


def _in_tests() -> bool:
    return ("pytest" in sys.modules) or ("PYTEST_CURRENT_TEST" in os.environ)


def _task_worker_loop() -> None:
    while True:
        try:
            task_id = _task_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        try:
            if _is_task_cancelled(task_id):
                try:
                    repository.mark_failed(task_id, "cancelled")
                    repository.patch_task(task_id, stage="cancelled", stage_message="已作废")
                except Exception:
                    pass
                continue
            _process_task(task_id)
        except HTTPException:
            # _process_task already persisted failure state.
            pass
        except Exception:
            logger.exception("Unexpected worker error task_id=%s", task_id)
        finally:
            with _processing_lock:
                _processing_inflight.discard(task_id)
            try:
                _task_queue.task_done()
            except Exception:
                pass


def _ensure_task_workers_started() -> None:
    if _in_tests():
        return
    with _workers_lock:
        if _worker_threads:
            return

        worker_count = max(1, _int_env("TASK_WORKERS", 2))
        for i in range(worker_count):
            thread = threading.Thread(
                target=_task_worker_loop,
                name=f"task-worker-{i + 1}",
                daemon=True,
            )
            _worker_threads.append(thread)
            thread.start()


def _start_processing_in_thread(task_id: str) -> None:
    _ensure_task_workers_started()

    # Validate task exists early so we don't leak inflight entries.
    try:
        repository.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with _processing_lock:
        if task_id in _processing_inflight:
            return
        _processing_inflight.add(task_id)

    try:
        _task_queue.put_nowait(task_id)
    except queue.Full as exc:
        with _processing_lock:
            _processing_inflight.discard(task_id)
        raise HTTPException(status_code=429, detail="Task queue is full") from exc

    # Best-effort: publish queued snapshot so clients show immediate feedback.
    try:
        repository.patch_task(task_id, stage="queued", stage_message="已加入队列，等待处理")
        task = repository.get(task_id)
        _event_broker.publish(
            task_id,
            "progress",
            {
                "task_id": task_id,
                "status": str(task.status),
                "stage": "queued",
                "message": "已加入队列，等待处理",
            },
        )
    except Exception:
        pass


@app.on_event("startup")
def _start_task_workers() -> None:
    tasks_service.ensure_workers_started()


"""Per-problem endpoints and /problems were moved to backend/app/api/*.py."""


def _get_problem(task, problem_id: str):
    for problem in task.problems:
        if problem.problem_id == problem_id:
            return problem
    raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found in task {task.id}")


def _retag_single(task, problem, force: bool = False) -> None:
    if problem.locked_tags and not force:
        return
    solutions = {s.problem_id: s for s in task.solutions}
    solution = solutions.get(problem.problem_id)
    tagger = pipeline.deps.tagger
    tags = tagger.run(task.payload, [problem], [solution] if solution else [])
    # replace tag for this problem
    task.tags = [t for t in task.tags if t.problem_id != problem.problem_id] + tags


def _update_problem(task, updated_problem):
    task.problems = [updated_problem if p.problem_id == updated_problem.problem_id else p for p in task.problems]


def _guess_openai_gateway_config() -> tuple[str | None, str | None, str | None, str]:
    """Pick a base_url+api_key for OpenAI-compatible gateway model listing.

    Priority:
      1) agent TOML default if provider=openai
      2) env OPENAI_BASE_URL + OPENAI_API_KEY
    """

    base_url: str | None = None
    api_key: str | None = None
    authorization: str | None = None
    auth_header_name: str = "Authorization"

    try:
        default_cfg = agent_config_bundle.default if agent_config_bundle else None
        if default_cfg and default_cfg.provider == "openai":
            base_url = default_cfg.base_url
            api_key = default_cfg.api_key
    except Exception:
        pass

    base_url = base_url or os.getenv("OPENAI_BASE_URL")
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    authorization = os.getenv("OPENAI_AUTHORIZATION") or os.getenv("OPENAI_AUTH_HEADER_VALUE")
    auth_header_name = os.getenv("OPENAI_AUTH_HEADER_NAME") or "Authorization"

    if authorization and not api_key:
        # Best-effort extraction for OpenAI SDK usage.
        prefix = "Bearer "
        api_key = authorization[len(prefix) :].strip() if authorization.startswith(prefix) else authorization.strip()

    return base_url, api_key, authorization, auth_header_name


def _fetch_openai_models(
    base_url: str,
    api_key: str | None,
    authorization: str | None,
    auth_header_name: str = "Authorization",
    timeout_seconds: float = 5.0,
) -> list[dict[str, object]]:
    url = base_url.rstrip("/") + "/models"

    headers = {
        "Content-Type": "application/json",
    }
    if authorization:
        headers[auth_header_name] = authorization
    elif api_key:
        headers[auth_header_name] = f"Bearer {api_key}"

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        raise HTTPException(status_code=exc.code, detail=body or str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach gateway: {exc}") from exc

    payload = json.loads(body)
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(data, list):
        return []
    items: list[dict[str, object]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "id": item.get("id"),
                "provider": item.get("provider"),
                "provider_type": item.get("provider_type"),
            }
        )
    return items


@app.on_event("startup")
def _prefetch_models_cache() -> None:
    """Best-effort prefetch of gateway model list.

    This keeps Settings UI snappy and matches the expectation that the backend
    can fetch model list on startup when credentials are available.
    """

    try:
        models_service.prefetch_cache()
    except Exception:
        pass


@app.on_event("startup")
def _check_ai_gateway_on_startup() -> None:
    """Warn early if an OpenAI-compatible gateway looks misconfigured/offline."""

    global _ai_gateway_status

    if _running_under_pytest:
        _ai_gateway_status = {"checked": False, "skipped": "pytest"}
        return

    require_gateway = os.getenv("AI_REQUIRE_GATEWAY", "false").lower() == "true"
    urls = _collect_openai_gateway_urls()
    if not urls:
        _ai_gateway_status = {"checked": True, "configured": False}
        return

    results: list[dict[str, object]] = []
    any_down = False
    for label, base_url in urls:
        ok, detail = _probe_openai_gateway(base_url)
        results.append({"label": label, "base_url": base_url, "ok": ok, "detail": detail})
        if not ok:
            any_down = True

    _ai_gateway_status = {
        "checked": True,
        "configured": True,
        "ok": not any_down,
        "targets": results,
        "require_gateway": require_gateway,
    }

    if any_down:
        logger.warning(
            "OpenAI-compatible gateway not reachable at startup; tasks may fallback or fail. "
            "Set AI_REQUIRE_GATEWAY=true to fail fast. targets=%s",
            results,
        )
        if require_gateway:
            raise RuntimeError("AI_REQUIRE_GATEWAY=true but gateway probe failed")


def _process_task(task_id: str):
    try:
        if _is_task_cancelled(task_id):
            repository.mark_failed(task_id, "cancelled")
            repository.patch_task(task_id, stage="cancelled", stage_message="已作废")
            return repository.get(task_id)

        repository.mark_processing(task_id)
        repository.patch_task(task_id, stage="starting", stage_message="开始处理")
        _event_broker.publish(
            task_id,
            "progress",
            {
                "task_id": task_id,
                "status": "processing",
                "stage": "starting",
                "message": "开始处理",
            },
        )
        task = repository.get(task_id)
        def _progress(stage: str, message: str | None) -> None:
            if _is_task_cancelled(task_id):
                raise _TaskCancelled()
            repository.patch_task(task_id, stage=stage, stage_message=message)
            _event_broker.publish(
                task_id,
                "progress",
                {
                    "task_id": task_id,
                    "status": repository.get(task_id).status,
                    "stage": stage,
                    "message": message,
                },
            )

        def _llm_delta(problem_id: str, kind: str, delta: str) -> None:
            if not delta:
                return
            if _is_task_cancelled(task_id):
                raise _TaskCancelled()

            _append_task_stream(task_id, delta)
            _event_broker.publish(
                task_id,
                "llm_delta",
                {
                    "task_id": task_id,
                    "problem_id": problem_id,
                    "kind": kind,
                    "delta": delta,
                },
            )

        result = pipeline.run(
            task_id,
            task.payload,
            task.asset,
            on_progress=_progress,
            on_llm_delta=_llm_delta,
        )

        # Merge manual tags/attributes into the pipeline output (manual-first), and
        # keep the tag registry growing best-effort.
        manual_knowledge = [str(t).strip() for t in (task.payload.knowledge_tags or []) if str(t).strip()]
        manual_error = [str(t).strip() for t in (task.payload.error_tags or []) if str(t).strip()]
        manual_source = (task.payload.source or "").strip()

        def _merge_unique(prefix: list[str], tail: list[str]) -> list[str]:
            out: list[str] = []
            seen: set[str] = set()
            for item in [*prefix, *tail]:
                s = str(item).strip()
                if not s:
                    continue
                key = s.casefold()
                if key in seen:
                    continue
                seen.add(key)
                out.append(s)
            return out

        if manual_source:
            result = result.model_copy(
                update={
                    "problems": [
                        p.model_copy(update={"source": p.source or manual_source}) for p in result.problems
                    ]
                }
            )

        if manual_knowledge or manual_error:
            patched_tags = []
            for t in result.tags:
                patched_tags.append(
                    t.model_copy(
                        update={
                            "knowledge_points": _merge_unique(manual_knowledge, t.knowledge_points),
                            "error_hypothesis": _merge_unique(manual_error, t.error_hypothesis),
                        }
                    )
                )
            result = result.model_copy(update={"tags": patched_tags})

        try:
            tag_store.ensure(TagDimension.KNOWLEDGE, manual_knowledge)
            tag_store.ensure(TagDimension.ERROR, manual_error)
            if manual_source:
                tag_store.ensure(TagDimension.META, [manual_source])
            # Learn from agent outputs (keep it conservative for error tags).
            discovered_knowledge: list[str] = []
            discovered_error: list[str] = []
            for t in result.tags:
                discovered_knowledge.extend(t.knowledge_points or [])
                for e in (t.error_hypothesis or []):
                    s = str(e).strip()
                    if not s or len(s) > 40 or "\n" in s:
                        continue
                    discovered_error.append(s)
            tag_store.ensure(TagDimension.KNOWLEDGE, discovered_knowledge)
            tag_store.ensure(TagDimension.ERROR, discovered_error)
        except Exception:
            pass

        updated = repository.save_pipeline_result(task_id, result)
        repository.patch_task(task_id, stage="done", stage_message="完成")
        _event_broker.publish(
            task_id,
            "progress",
            {
                "task_id": task_id,
                "status": "completed",
                "stage": "done",
                "message": "完成",
            },
        )
        return updated
    except _TaskCancelled:
        repository.mark_failed(task_id, "cancelled")
        try:
            repository.patch_task(task_id, stage="cancelled", stage_message="已作废")
        except Exception:
            pass
        try:
            _event_broker.publish(
                task_id,
                "progress",
                {
                    "task_id": task_id,
                    "status": "failed",
                    "stage": "cancelled",
                    "message": "已作废",
                },
            )
        except Exception:
            pass
        return repository.get(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected runtime errors
        repository.mark_failed(task_id, str(exc))
        try:
            repository.patch_task(task_id, stage="failed", stage_message=str(exc))
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc)) from exc
