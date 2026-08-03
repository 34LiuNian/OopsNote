# ADR 0002: LangChain is the default managed model runtime

Date: 2026-08-03
Status: accepted; production evaluation required before Pi removal

## Decision

`ManagedAiRunner` remains the sole owner of task/run state, timeouts,
cancellation, stale recovery, retry classification and terminal transitions.
`LangChainRunner` is the default model adapter and owns only explicit provider
invocation plus the bounded 24-round restricted MCP tool loop. It does not use
LangGraph persistence, `create_agent`, provider fallback, dynamic routing, or
provider-native tools.

Provider profiles are non-secret AppSettings metadata. Each admitted run stores
an immutable profile snapshot; credentials are resolved only through the local
SecretStore. Windows uses Credential Manager. Linux and containers use an
encrypted file vault whose master key is supplied as a read-only mounted file;
the key value is never an application environment variable. OCR uses the same
vault configuration for the LangChain path, with no legacy-file fallback.

Pi and Hermes remain explicit diagnostic/migration backends only. A run never
changes backend. RustPi deletion requires the documented isolated 30-task
evaluation gate, not merely unit-test success.

## Consequences

- MCP `tool_contracts.json` is the only tool-schema source.
- Solver and verifier have separate LangChain contexts within the same TaskRun.
- A valid MCP `finalize_task` is the only success condition.
- 401/403, model/configuration and validation failures are terminal; only
  classified transport/429/5xx failures may create a fresh managed retry.
- Provider SDK retries are disabled; shared lifecycle retry policy remains the
  only retry authority and retains the original run's profile snapshot.
- RustPi removal is a separate, irreversible step gated by isolated real-task
  evidence. Hermes retirement remains a later independent decision.
