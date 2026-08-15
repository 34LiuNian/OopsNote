# LangChain operations

## Credential and channel setup

The SecretStore adapter is platform-specific: Windows uses Credential Manager; production
Linux containers use an encrypted named volume protected by a read-only Docker secret.
Initialize the master key once before the first container start:

```bash
.venv/bin/python scripts/setup/init_secret_store.py
```

Back up the generated key separately from the encrypted vault. Never print it or place it in
Compose environment variables.

Create non-secret channel metadata through `POST /settings/ai/channels`, then set or rotate a
credential through:

```text
POST /settings/ai/channels/{channel_id}/credential
```

The server writes the submitted secret under a fresh vault reference, validates the provider
model catalogue, and atomically switches the channel version and discovered model list.
Responses expose only channel metadata, models, `has_secret`, and discovery results.

Configure the ordinary stages and diagram stage through `PUT /settings/ai/policy`:
`vision` (Vision), `agent` (Tool Calling), `review` (Tool Calling), and `diagram` (Vision).
Problem runs freeze the first three selections; diagram runs freeze only `diagram`. OCR always
uses the problem run's immutable Vision snapshot.

## Execution and evidence

LangChain is the only backend and requires no runtime-selection environment variable. A run
uses one immutable policy snapshot and never changes provider or model. Redacted observations
are written to `storage/runs/{run_id}.events.jsonl`; they record provider/model/policy version,
tool names, round count, duration and reported token usage, never secret values or credential
references.

For an isolated real-model evaluation, use a separate storage root. Never shadow-run a
production task id because both runs could attempt a pipeline finalize.

```powershell
$env:OOPSNOTE_STORAGE_DIR='D:/works/2026/OopsNote/storage-langchain-eval'
.\.venv\Scripts\python.exe -m uvicorn oopsnote.api.main:app
```

Generate and review an evidence report from that isolated cohort:

```powershell
.\.venv\Scripts\python.exe scripts\benchmarks\langchain_production_report.py `
  --storage D:/works/2026/OopsNote/storage-langchain-eval `
  --policy-version 1 `
  --write-evidence-template D:/works/2026/OopsNote/storage-langchain-eval/evidence.json
```

The report validates the fixed policy cohort, persisted cancellation evidence, successful
finalize cardinality, quality review and measured cost. It is a LangChain production-quality
report, not a runtime migration or deletion gate.

## Deployment context

Before explicitly requested production builds, synchronize source inputs without copying
runtime data, vaults, secrets, `node_modules`, or `.next`:

```sh
./scripts/deploy/sync_production_context.sh
```
