# Pi local operations

## Local configuration

1. Install pinned adapter dependencies:

   ```powershell
   npm install --prefix .pi
   ```

2. Copy `.pi/runtime.json.example` to the ignored `.pi/runtime.json` and set the absolute Pi command.
3. Copy `.pi/extensions.json.example` to the ignored `.pi/extensions.json`; store the DashScope key and OCR model there.
4. Configure DeepSeek through Pi's local auth store.
5. Sync repository skills and validate:

   ```powershell
   .\.venv\Scripts\python.exe scripts\setup\setup_pi.py --sync
   ```

API keys are not committed and environment variables are not the default local secret mechanism.

## Smoke and benchmark

```powershell
.\.venv\Scripts\python.exe scripts\benchmarks\pi_math_smoke.py
.\.venv\Scripts\python.exe scripts\benchmarks\pi_math_benchmark.py
```

Reports are written to `storage/pi-benchmark/<timestamp>.md` and `.json`.

## API debugging

```powershell
.\.venv\Scripts\python.exe -m uvicorn oopsnote.api.main:app --reload
```

Flow:

1. `POST /upload`
2. `POST /tasks/{task_id}/process?backend=pi`
3. `GET /tasks/{task_id}` and `GET /tasks/{task_id}/runs`
4. Optional `POST /tasks/{task_id}/cancel`
5. Retry only with `POST /tasks/{task_id}/retry?backend=pi`

Inspect `storage/runs/{run_id}.json`, `.log`, and `.rpc.jsonl`. Never edit task JSON while a run is active.

## Failure interpretation

- `not_finalized`: Pi exited or settled without a valid MCP finalize.
- `process_timeout`: managed timeout terminated the process.
- `stale_heartbeat`: startup recovery found an abandoned run.
- provider/network/429/503: eligible for a fresh Pi retry, capped at two.
- validation or unreadable image errors: do not retry blindly.
