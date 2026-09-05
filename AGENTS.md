# OopsNote project instructions

## Current architecture

OopsNote is a local-first question-management application with one AI runtime and one
production authentication system:

```text
Web / Better Auth BFF / REST
    -> ManagedAiRunner
       -> LangChainRunner
    -> shared restricted Python MCP
    -> Core stores / assets / Obsidian sync
```

- LangChain is the only AI runtime. Do not add runtime selection, compatibility backends,
  subprocess agents, or fallback to another runtime.
- Better Auth is the production identity source. `local` remains an explicit loopback-only
  development mode. Do not add external identity-provider compatibility paths.
- `ManagedAiRunner` is the only lifecycle owner. LangChain owns provider invocation and the
  bounded restricted MCP loop, never task lifecycle state.
- The only AI-side capabilities are `ocr_image` and the restricted OopsNote MCP pipeline.
- `skills/` is the only skill source and is read directly by LangChain. Do not generate a
  second skill tree.
- OopsMark v1 is the canonical content format. Read `docs/oopsmark-v1.md` before changing
  parsing, AI output, Web rendering, Obsidian output, or paper export.
- Retired runtime and authentication history is not an implementation reference. See
  `docs/archive/retired-runtime-history.md` only when investigating old persisted evidence.

## Source layout

```text
oopsnote/core/       storage models, stores, tags, search, assets
oopsnote/content/    OopsMark parsing, validation, adapters
oopsnote/ai/         managed lifecycle and the LangChain runtime
oopsnote/api/        FastAPI composition and route modules
oopsnote/mcp/        Python MCP tools and pipeline write boundary
oopsnote/obsidian/   JSON to Obsidian synchronization
oopsnote/paper/      paper templates and export support
frontend/            Next.js Web application and Better Auth BFF
skills/              editable OopsNote skill sources
scripts/             active setup, benchmark, migration, and deployment tools
tests/               Python regression suite
storage/             local runtime data; never treat as generated trash
vaults/              user-owned source and Obsidian data; never delete
```

## Development rules

- Preserve existing worktree changes and user data.
- Use the project interpreter: `.venv\Scripts\python.exe`.
- On Windows, give pytest a workspace-local `--basetemp` path.
- Keep REST, MCP, Core, and frontend responsibilities separate.
- Do not store API keys in tracked files or environment variables. Use SecretStore: Windows
  Credential Manager locally or the encrypted Linux/container vault with a file-mounted
  master key.
- OCR must resolve the Vision model from the immutable LangChain run snapshot. It must not
  read a second credential/configuration source.
- Keep timeout, heartbeat, cancellation, stale recovery, retry policy, and finalize checks in
  the shared managed lifecycle.
- A retry is always a fresh LangChain run with the original provider policy snapshot. Retry
  only classified transient failures.
- Task and run evidence remains local under `storage/`.

## Production build and release policy

- Do not run a production frontend build, Docker build, Compose recreation, or production
  publish unless the user explicitly requests it for the current task.
- When explicitly requested, use the production Compose file and rebuild only affected
  services; do not recreate databases or unrelated infrastructure.
- After an explicitly requested recreation, verify container health, the public health
  endpoint, and the changed route or workflow.

## Durable fix requirements

Use `skills/prevent-patchwork-technical-debt/SKILL.md` when it exists and the task concerns a
bug fix, fallback, retry, compatibility layer, or reliability change.

- State the intended invariant and identify the earliest layer that violates it.
- Fix the invariant in its owning layer; do not hide an upstream defect with downstream
  retries, duplicated state, silent coercion, or catch-all fallback behavior.
- Keep one authoritative source for each contract and piece of state.
- Prefer removing invalid states and redundant branches over adding special cases.
- Classify failures before retrying. Surface deterministic contract, validation,
  authorization, and state errors directly.
- Preserve failure evidence and explicit terminal states.
- Test the invariant and failure transition, including interruption, repetition/idempotency,
  boundary inputs, and stale/partial state where relevant.
- Before declaring a fix complete, report whether it removes the root cause, what new states
  or branches it adds, and what technical debt remains.

## Verification

```powershell
$env:PYTEST_ADDOPTS='--basetemp=D:/works/2026/OopsNote/.pytest-tmp'
.\.venv\Scripts\python.exe -m pytest -q
uv run ruff check .
uv run ruff format --check .
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

Do not claim browser E2E, credentialed model behavior, or paper compilation from static checks
alone.

## Debug process hygiene

- Any process started for debugging (dev servers, watchers, REPLs, benchmark
  runs, port probes) must be stopped before the task ends. Do not leave a
  managed or background process running "for later" unless the user explicitly
  asked to keep it alive.
- Prefer session-managed processes (hub `start`) so they can be stopped
  reliably; when killing user-started processes, confirm the exact PID and
  command line first.
- After stopping, verify the port is released (`netstat`) and no orphaned
  child process (e.g. `next start-server`) still holds it.

## Frontend information architecture

Read `DESIGN.md` and `docs/frontend-interaction.md` before changing problem-edit
layout, paper knowledge filters, tagging, or any surface that mixes glanceable
review with a long-running tool.

- Before changing visual style or micro-interaction (spacing, chips, hover,
  expand, subject pickers), ask detailed questions and wait for an explicit
  choice. Do not iterate by guessing.
- Decide layout from use frequency, not from a desire to show everything at once.
  Proofreading is the default stacked page; deep diagram work is an explicit mode;
  catalog trees and other tall tools open in a bounded overlay or sidebar.
- Keep one job per path. Do not reuse a primary save button for two write
  semantics (problem-text drafts are explicit; diagram settings persist immediately).
- Match the control to the data. Knowledge points are catalog leaves, not free
  tags. Printed `chapter` is source-paper location, not the knowledge-tree grouping.
  Error causes and custom notes are secondary and stay collapsed when empty.
- Reuse `frontend/components/knowledge-tree/` for catalog selection. Paper filters
  and library filters use cascade selection (parents select the whole branch).
  Problem edit uses leaf-only selection in a dialog. Leaf identity comes from the
  unfiltered catalog tree, not from a search-pruned node.
- Auto-expand only the ancestor chain of selected leaves. Do not expand by depth.
  Non-selectable nodes must not reserve a checkbox column.
- Do not distinguish leaf vs parent with type size. Chevron and checkbox already
  encode role; depth is encoded by indent.
- Align subject at `TaskRecord` (`effective_subject()`). Frontend consumers read
  the projected `subject`; they must not re-merge `task.subject || problem.subject`.

## Frontend Button Icon Contract

- The shared `frontend/components/ui/primitives.tsx` `Button` owns icon-and-label alignment.
- Buttons with a leading icon must declare it with `leadingVisual`; trailing icons must use
  `trailingVisual`.
- Do not render icon components directly beside button text as `Button` children.
- Icon-only actions must use `IconButton` with an accessible `aria-label`.
- New or changed frontend buttons must preserve a visible icon-label gap and shared vertical
  alignment.
