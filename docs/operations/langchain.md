# LangChain local operations

## Credential and channel setup

The SecretStore adapter is platform-specific: Windows uses Credential Manager;
the production Linux container uses an encrypted named volume protected by a
read-only Docker secret. Initialize that master key once before the first build:

```bash
.venv/bin/python scripts/setup/init_secret_store.py
```

The generated file is ignored by Git. Back it up separately from the encrypted
vault: losing it makes the vault unrecoverable. Never print or place its value
in Compose environment variables.

Legacy profile-shaped settings are retired at application startup. Existing
queued or running snapshots keep their opaque credential reference until they
finish; the retired metadata and unused secrets are then removed.

Create non-secret channel metadata through `POST /settings/ai/channels`, then
set or rotate its credential inline with:

```text
POST /settings/ai/channels/{channel_id}/credential
```

The server writes the submitted secret under a fresh vault reference, validates
the provider model catalogue, and atomically switches the channel version and
its discovered model list. Responses expose only channel metadata, models,
`has_secret`, and discovery results. Failed validation leaves the previous
channel and credential unchanged. Newly discovered capabilities are closed by
default and must be confirmed by an administrator through the model list.

The old reference is retained while an active queued/running run snapshot uses
it. Do not use `.pi/auth.json`, `.pi/extensions.json`, environment variables,
`storage/`, task JSON, or run logs as a LangChain credential source.

Configure the three global model stages through `PUT /settings/ai/policy`:
`vision` (Vision), `agent` (Tool Calling), and `review` (Tool Calling). A run
freezes all three channel/model selections. The restricted `ocr_image` MCP
tool resolves the Vision model from that immutable run snapshot.

## Execution and evidence

`langchain` is the default backend. A run uses one policy snapshot and cannot
fall back to Pi, Hermes, another provider, or another model. The runner writes
redacted event observations to `storage/runs/{run_id}.events.jsonl`; they record
provider/model/policy version, tool names, round count, duration from TaskRun,
and reported token usage, never secret values or credential references.

Before building the production `backend` or `frontend` image from a checkout,
synchronize the complete source build context. The script intentionally excludes
runtime data, vaults, secrets, `node_modules`, and `.next`:

```sh
./scripts/deploy/sync_production_context.sh
```

Run the real evaluation with a separate storage root. Never shadow-run a
production task id, because both runs could attempt a pipeline finalize.

```powershell
$env:OOPSNOTE_STORAGE_DIR='E:/works/2026/OopsNote/storage-langchain-eval'
$env:OOPSNOTE_AI_BACKEND='langchain'
.\.venv\Scripts\python.exe -m uvicorn oopsnote.api.main:app
```

Use 30 de-identified real task images and retain the isolated TaskRun JSON and
event files. The RustPi backend may be removed only after evidence shows:

- 30 tasks without loss, duplicate finalize, or un-cancellable runs;
- completion rate at least 95%;
- quality decrease no more than two percentage points;
- P95 no worse than 20%;
- a separately decided measured cost threshold, based on provider usage rather
  than RustPi cache tokens.

Until then, Pi and Hermes are deployment-level diagnostic choices. They are
available only when explicitly listed in
`OOPSNOTE_ENABLED_AI_BACKENDS`, for example `langchain,pi`; production should
normally leave the value unset so only `langchain` is admitted.

Generate an intentionally incomplete evidence manifest from the persisted
cohort. The command writes task IDs only; every `null` review field must be
filled from the fixed RustPi baseline and human quality review. Record
cancellation fault-injection tasks with a source beginning
`langchain-cancellation-` so they remain available for run-ID verification but
do not enter the 30-task quality denominator.

```powershell
.\.venv\Scripts\python.exe scripts\benchmarks\langchain_production_report.py `
  --storage E:/works/2026/OopsNote/storage-langchain-eval `
  --policy-version 1 `
  --write-evidence-template E:/works/2026/OopsNote/storage-langchain-eval/evidence.json
```

The version 2 manifest requires one exact frozen three-stage strategy, a quality
result for the LangChain and RustPi baseline output of every cohort task, the RustPi baseline P95, at least one
persisted cancelled run trial, and a measured-cost approval containing limit,
currency, approver and timestamp. It deliberately cannot carry a claimed
finalize count: the report derives successful finalize cardinality from the
canonical `verifier_submission` RunStore artifacts.

After review, build the immutable report without mutating evaluation storage:

```powershell
.\.venv\Scripts\python.exe scripts\benchmarks\langchain_production_report.py `
  --storage E:/works/2026/OopsNote/storage-langchain-eval `
  --evidence E:/works/2026/OopsNote/storage-langchain-eval/evidence.json `
  --output-dir E:/works/2026/OopsNote/storage-langchain-eval/report
```

The report intentionally exits nonzero until every deletion gate is supported
by recorded evidence. It rejects strategy/version mismatches, missing cohort
runs, duplicate task/run references, non-cancelled trial run IDs, incomplete
cost coverage and unfilled or malformed evidence rather than treating them as a
pass.
