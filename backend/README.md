# Backend Service

This package hosts the FastAPI orchestration service for the OopsNote project.

## What it provides

- Task orchestration: upload → OCR → solve/tag → persist
- Streaming: SSE events + best-effort stream replay after refresh
- Tags: 4 dimensions (knowledge / error / meta / custom) with configurable styles
- Library aggregation: flatten all extracted problems across tasks

## Storage layout (file-based)

All data is stored under `backend/storage/` for local-first usage:

- `storage/assets/` uploaded images and cropped regions
- `storage/tasks/{task_id}.json` task payload + extracted problems + solutions + tags
- `storage/task_streams/{task_id}.txt` accumulated LLM stream text (used by stream replay)
- `storage/traces/*.jsonl` structured trace events
- `storage/settings/tags.json` tag registry
- `storage/settings/tag_dimensions.json` per-dimension label + Primer label variant

## Development

```bash
cd backend
python -m pip install -e .[dev]
uvicorn app.main:app --reload
```

Health check:

```bash
curl -s http://localhost:8000/health
```

`/health` also includes a best-effort `ai_gateway` field to surface whether the configured OpenAI-compatible gateway is reachable.

## API overview

### Tasks

- `POST /upload` create task from an uploaded image (multipart)
- `POST /tasks` create task from an existing asset URL (JSON)
- `GET /tasks` list tasks (`active_only=true` supported)
- `GET /tasks/{task_id}` task details (problems/solutions/tags)
- `POST /tasks/{task_id}/process` start processing
- `POST /tasks/{task_id}/cancel` stop + mark task as cancelled (best-effort cooperative cancellation)
- `DELETE /tasks/{task_id}` delete task

### Streaming

- `GET /tasks/{task_id}/events` SSE stream (progress + llm deltas + done)
- `GET /tasks/{task_id}/stream` replay stored stream text (for refresh/reconnect)

### Problem editing

- `PATCH /tasks/{task_id}/problems/{problem_id}/override` edit question_no/source/text/tags
- `DELETE /tasks/{task_id}/problems/{problem_id}` delete a single problem
- `POST /tasks/{task_id}/problems/{problem_id}/ocr` redo OCR for one problem
- `POST /tasks/{task_id}/problems/{problem_id}/retag` redo tagging for one problem

### Library

- `GET /problems` list all extracted problems (supports `subject` and `tag` query)

### Tags & settings

- `GET /tags` list/search tags; empty `query` returns top tags by `ref_count` (best-effort, computed from existing tasks/problems)
- `POST /tags` create/update tags (response includes `ref_count`, usually `0` for newly created tags)
- `GET /settings/tag-dimensions` read dimension styles
- `PUT /settings/tag-dimensions` update dimension styles

### Models / agent settings

- `GET /models` available models
- `GET /settings/agent-models` current per-agent model selection
- `GET /settings/agent-enabled` which agents are enabled

## Optional OpenAI integration

Set these environment variables before starting FastAPI to switch from the deterministic stub client to the real OpenAI-powered pipeline:

- `OPENAI_API_KEY` — enables the `OpenAIClient` when set.
- `OPENAI_MODEL` (default `gpt-4o-mini`) — override with `o4-mini`, `gpt-4.1-mini`, etc.
- `OPENAI_TEMPERATURE` (default `0.2`) — adjusts sampling temperature for both solver and classifier prompts.

If `OPENAI_API_KEY` is omitted the service automatically keeps using the offline `StubAIClient`, so local development and tests continue to run without external dependencies.

### Fail-fast on missing gateway

By default the backend will **not** fail startup if an OpenAI-compatible gateway is misconfigured/offline; it logs a warning and the pipeline may fallback.

To force an early failure (useful in production), set:

- `AI_REQUIRE_GATEWAY=true`

## Per-agent config

See `README_AGENT_CONFIG.md` for enabling per-agent providers/models via TOML or env vars.
