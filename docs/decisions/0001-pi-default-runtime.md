# ADR 0001: Pi is the default AI runtime

Date: 2026-07-22
Status: accepted, migration observation in progress

## Decision

Use Pi JSONL RPC as the default OopsNote AI runtime. Keep Hermes only as a time-limited fallback until the documented production thresholds are met.

Each task starts an isolated Pi process with no shared session and no builtin tools. OopsNote reuses the restricted Python MCP through pinned `pi-mcp-adapter`; OCR remains a project Extension. Shared timeout, cancellation, heartbeat, retry and finalize checks stay in `ManagedAiRunner`.

## Consequences

- Runtime migration can be evaluated separately from OCR and solution quality.
- Pi failure never switches to Hermes inside the same run.
- Skills remain repository-owned and are synced into `.pi/skills/`.
- Python MCP remains after Hermes removal.
- Hermes-specific code must receive no new product features.
