# Web contract

Status: active
Updated: 2026-08-15

The browser talks to FastAPI through the Next.js Better Auth BFF. FastAPI owns HTTP DTOs;
frontend components never read storage files.

## Task flow

1. `POST /upload` stores one image asset and creates one pending task.
2. `POST /tasks/{task_id}/process` admits a run into `ManagedAiRunner`.
3. `LangChainRunner` executes the immutable provider policy through restricted MCP tools.
4. Core persists OCR evidence, a solver candidate, review/finalize evidence and task state.
5. Web polls `GET /tasks/{task_id}` while a task is active.

There is no client-selectable AI runtime. Collection endpoints always return `{ "items": [] }`.

## Manual batch segmentation

The browser owns segmentation. A user draws and confirms problem regions on source pages. Each
crop becomes an independent task, so the model receives one problem image and does not decide
page segmentation.

`/batch-sessions` persists one manual-segmentation session per source SHA-256. Re-uploading the
same source resumes the session. Crop images are regenerated only when selected problems are
submitted.

## Boundaries

- Better Auth owns browser identity; the BFF signs an internal identity envelope for FastAPI.
- Core owns JSON/SQLite state and assets.
- `ManagedAiRunner` owns task lifecycle; LangChain owns only provider/tool execution.
- The restricted MCP pipeline is the only AI write boundary.
- Web owns selection, browsing, editing and review interaction.
