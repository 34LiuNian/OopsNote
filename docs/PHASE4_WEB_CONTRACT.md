# Phase 4 Web Contract

The Web frontend talks to Core only through the Next.js `/api` rewrite. Core
owns the HTTP DTOs; frontend components do not read JSON storage files.

## Task Flow

1. `POST /upload` stores one image asset and creates one pending task.
2. `POST /tasks/{task_id}/process` marks that task processing and starts
   `hermes --profile oopsnote chat -s oopsnote-orchestrator` in the background.
3. Hermes uses MCP to update the same TaskRecord with OCR, solution, and tags.
4. Web polls `GET /tasks/{task_id}` while a task is active.

Collection endpoints always return an object with `items`:

- `GET /tasks`
- `GET /problems`
- `GET /tags`

## Manual Batch Segmentation

The browser owns segmentation. A user selects batch mode, draws each problem
region on a whole-page image, and confirms all regions once. Each crop becomes
an independent `POST /upload` request, so Core and Hermes always receive one
problem image and do not make page-segmentation decisions.

## Batch Session Cache

`/batch-sessions` persists one manual-segmentation session per source-file
SHA-256. The source asset, current page, subject, notes, normalized crop
rectangles, stable global question numbers, submission state, and task/problem
references are stored separately from task records. Re-uploading the same file
hash resumes that session; crop images are regenerated from the source page
and retained as the task screenshot. Batch-created tasks carry the reverse
session hash and segment ID, while single-image tasks retain a trace to their
original uploaded image. Crop images are regenerated only when the user
submits the selected problems.

## Boundary

- Core persists JSON and assets, exposes REST, and starts the documented
  Hermes hand-off.
- Hermes owns OCR, solving, and tagging through MCP.
- Web owns image selection, manual crop interaction, browsing, and editing.
- No authentication, account, or token endpoints are part of this product.
