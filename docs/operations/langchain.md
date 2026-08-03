# LangChain local operations

## Credential and profile setup

The SecretStore adapter is platform-specific: Windows uses Credential Manager;
the production Linux container uses an encrypted named volume protected by a
read-only Docker secret. Initialize that master key once before the first build:

```bash
.venv/bin/python scripts/setup/init_secret_store.py
```

The generated file is ignored by Git. Back it up separately from the encrypted
vault: losing it makes the vault unrecoverable. Never print or place its value
in Compose environment variables.

Import legacy model and OCR credentials once. The command returns profile
metadata only, never secret values or credential references.

```powershell
.\.venv\Scripts\python.exe scripts\migrate_local_secrets.py `
  --settings storage\app-settings.json `
  --pi-auth .pi\agent\auth.json `
  --ocr-config .pi\extensions.json
```

Create the provider profile through `POST /settings/provider-profiles` with
non-secret metadata and a `secret`. The server writes the secret under a fresh
Credential Manager reference, validates one explicit provider call, then
atomically writes the profile and selects it. Responses expose only profile
metadata and `has_secret`. Rotate an existing key with:

```text
POST /settings/provider-profiles/{profile_id}/secret
```

The old reference is retained while an active queued/running run snapshot uses
it. Do not use `.pi/auth.json`, `.pi/extensions.json`, environment variables,
`storage/`, task JSON, or run logs as a LangChain credential source.

For OCR, select the vault-backed OCR profile by setting the non-secret
`ocr_profile_id` through `POST /settings/ocr-profile`; select the text model
through `POST /settings/provider-profiles/{profile_id}/activate`. Their model
and endpoint metadata are used by the existing restricted `ocr_image` MCP tool.

## Execution and evidence

`langchain` is the default backend. A run uses one profile snapshot and cannot
fall back to Pi, Hermes, another provider, or another model. The runner writes
redacted event observations to `storage/runs/{run_id}.events.jsonl`; they record
provider/model/profile version, tool names, round count, duration from TaskRun,
and reported token usage, never secret values or credential references.

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

Until then, `backend=pi` and `backend=hermes` are manual diagnostic choices.
They are available only when explicitly listed in
`OOPSNOTE_ENABLED_AI_BACKENDS`, for example `langchain,pi`; production should
normally leave the value unset so only `langchain` is admitted.

Build the cohort evidence without mutating the evaluation storage:

```powershell
.\.venv\Scripts\python.exe scripts\benchmarks\langchain_production_report.py `
  --storage E:/works/2026/OopsNote/storage-langchain-eval `
  --profile-id deepseek-primary --profile-version 3 `
  --output-dir E:/works/2026/OopsNote/storage-langchain-eval/report
```

The report intentionally exits nonzero until every deletion gate is supported
by recorded evidence. It does not treat missing quality, cancellation,
duplicate-finalize, baseline-P95, or cost-approval data as a pass.
