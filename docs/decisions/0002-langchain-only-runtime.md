# ADR 0002: LangChain is the only managed model runtime

Date: 2026-08-15
Status: accepted

## Decision

`ManagedAiRunner` remains the sole owner of task/run state, timeouts, cancellation, stale
recovery, retry classification and terminal transitions. `LangChainRunner` is the only model
adapter and owns explicit provider invocation plus the bounded 24-round restricted MCP loop.

Provider channels and the four-stage model policy are non-secret AppSettings metadata. Each
admitted problem run stores immutable `vision`, `agent`, and `review` snapshots; each diagram
run stores its `diagram` snapshot. Credentials resolve only through SecretStore. OCR resolves
the Vision model from the current run snapshot and has no independent configuration path.

The API does not expose runtime selection. Persisted historical backend fields are evidence,
not dispatch inputs.

## Consequences

- MCP `tool_contracts.json` is the only tool-schema source.
- `skills/` is the only skill source.
- Solver and reviewer have separate LangChain contexts within one TaskRun.
- A valid MCP `finalize_task` is the only problem-run success condition.
- Provider SDK retries are disabled; the shared lifecycle owns bounded fresh-run retries.
- The administrator provider API is the only channel and credential management boundary.
- Adding another runtime requires a new ADR and a demonstrated product boundary; it must not
  be introduced as fallback or compatibility behavior.
