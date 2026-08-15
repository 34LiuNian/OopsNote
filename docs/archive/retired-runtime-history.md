# Retired runtime and authentication history

Status: archived, not an implementation reference
Retired: 2026-08-15

Earlier OopsNote iterations evaluated subprocess-based AI agents, an RPC adapter, and an
external identity provider. Those implementations, setup scripts, local hidden directories,
deployment mounts, benchmarks, and compatibility tests have been removed.

Persisted historical run records may still contain the old backend or runtime names. They are
immutable local evidence only. Current code must not dispatch, retry, recover, configure, or
benchmark through those values.

The active contracts are:

- LangChain is the only AI runtime.
- Better Auth is the only production identity source.
- `local` is the only non-production authentication mode and is restricted to loopback.
- `skills/` is read directly and is the only skill tree.
- OCR resolves its provider model only from the immutable LangChain run snapshot.

Git history is the source for retired implementation details. Do not restore an old runtime or
authentication path as a compatibility fix.
