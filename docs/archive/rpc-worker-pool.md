# Legacy managed RPC worker pool

## Decision

This architecture remains only for explicitly enabled Pi diagnostics during the
LangChain evaluation window. Upstream Pi and pi_agent_rust use one managed
scheduling and JSONL transport implementation with independent runtime adapters.

```text
REST enqueue
  -> persisted QUEUED TaskRun
  -> fixed ManagedTaskDispatcher
  -> bounded RpcWorkerPool
       -> RustPiRuntimeAdapter -> .pi-rust/ -> long-lived Rust process
       -> PiRuntimeAdapter     -> .pi/      -> long-lived upstream Pi process
  -> one shared loopback HTTP MCP server
  -> Core stores
```

Each process handles one prompt at a time. High concurrency comes from a small
number of long-lived processes, not concurrent prompts inside one RPC session.
Before every task the leased worker must successfully complete `new_session`.
This preserves task isolation while amortizing runtime initialization.

This pool is not the default model path and is scheduled for deletion after the
isolated 30-task LangChain gate. It must not own lifecycle state or become a
fallback from a LangChain run.

## Backpressure and durability

- `OOPSNOTE_RPC_MAX_WORKERS` is the hard in-process concurrency bound.
- The dispatcher has the same fixed thread count; HTTP requests never create
  an unbounded background thread.
- `TaskRun` is persisted before it is scheduled. The memory queue is only an
  accelerator and is not the source of truth.
- `QUEUED` runs are rescheduled after application restart.
- A `RUNNING` run cannot resume because its subprocess and RPC session are
  gone. Startup closes it as retryable `worker_lost`; any retry receives a new
  run id and a clean session.
- Cancellation sends `abort` only to the worker leased by that task and keeps a
  healthy long-lived process available for reuse.
- Timeout, failed session reset, or process exit invalidates only that worker.

## Shared MCP

All workers connect to one application-owned HTTP MCP server bound to an
ephemeral `127.0.0.1` port. A random bearer token is generated for each API
process and is never stored in a tracked file. Upstream Pi receives it through
its MCP adapter environment. pi_agent_rust filters custom extension environment
variables, so its explicit project bridge receives the ephemeral URL and token
through registered runtime flags.

This removes the previous per-worker Python MCP subprocess and its independent
cache/write races. Core file stores use process-wide locks where API and MCP
store instances can target the same JSON file.

## Capacity guidance

Start with three workers on the current workstation. Increase only after
measuring:

1. peak RSS of all Rust/Pi processes;
2. cold-start CPU and disk contention;
3. provider in-flight request and rate limits;
4. p95 queue wait versus task execution time;
5. MCP/store write contention and timeout rate.

The queue can accept more work than the pool can execute, but it does not make
unbounded concurrency safe. For multi-process or multi-host deployment, replace
the in-process dispatcher with a database-backed lease queue before scaling;
the current JSON stores and process-local locks deliberately target one local
API process.
