# ADR 0001: pi_agent_rust is the default RPC runtime

Date: 2026-07-24
Status: superseded by ADR 0002

ADR 0002 replaced the default-runtime decision on 2026-08-03. This document
remains only as the RustPi baseline and diagnostic-backend history; it is no
longer an active source of runtime-selection policy.

## Decision

Use pi_agent_rust v0.1.22 JSONL RPC as the default OopsNote AI runtime. Keep upstream Pi as an explicit diagnostic fallback and Hermes only as a time-limited migration fallback until the documented production thresholds are met. OMP has no remaining adapter, project configuration, binary, cache, or ignored project directory.

Three bounded long-lived Rust processes each handle one task at a time. Every task starts with `new_session`; built-in tools, automatic extensions, and discovered skills are disabled. One explicit bridge exposes exactly OCR plus seven restricted Python pipeline tools. Shared timeout, cancellation, heartbeat, retry and finalize checks stay in `ManagedAiRunner`.

## Consequences

- Runtime migration can be evaluated separately from OCR and solution quality.
- Runtime failure never switches to Pi or Hermes inside the same run.
- Skills remain repository-owned and are embedded into each managed prompt.
- Python MCP remains after Hermes removal.
- Hermes-specific code must receive no new product features.
