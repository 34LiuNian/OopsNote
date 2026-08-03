# pi_agent_rust local operations

## Pinned runtime

- Version: `0.1.22`
- Commit: `92e5884a87b8eae140ace667c29ca2ed79410e3d`
- Windows x64 ZIP SHA-256: `6486c6fe78c484b8be61360e9c96f91426efc2b9bb493696fab3ccd088e43ba3`
- Extracted EXE SHA-256: `e898f4732ce139ea5cfaf41bb41ab792a58007ab626a657cd830c407a8d4ec51`

Install, copy compatible local auth into an independent agent directory, and validate:

```powershell
.\.venv\Scripts\python.exe scripts\setup\setup_pi_rust.py --install --sync
```

The binary, auth, sessions, and `runtime.json` are ignored under `.pi-rust/`.
OCR continues to read the ignored `.pi/extensions.json`; no API key is tracked.

## Restricted execution

The command disables built-in tools, automatic extensions, skill discovery,
prompt templates, themes, and migrations. It explicitly loads only
`.pi-rust/extensions/oopsnote_mcp.js`. The bridge registers exactly:

- `ocr_image`
- `mcp__oopsnote_pipeline_get_task`
- `mcp__oopsnote_pipeline_get_asset_path`
- `mcp__oopsnote_pipeline_list_tags`
- `mcp__oopsnote_pipeline_create_tag`
- `mcp__oopsnote_pipeline_report_task_stage`
- `mcp__oopsnote_pipeline_submit_solution_candidate`
- `mcp__oopsnote_pipeline_finalize_task`
- `mcp__oopsnote_pipeline_fail_task`

The bridge uses the existing FastMCP Streamable HTTP endpoint directly. This is
intentional: v0.1.22 exposes MCP registration metadata, but its bundled
`@modelcontextprotocol/sdk` client compatibility module is an empty stub and
cannot execute the existing JavaScript MCP adapter.

## Verified baseline (2026-07-24)

- One real curated math crop: completed, answer `C`, 11/11 tool calls succeeded.
- Managed duration: `53.594s`; previous upstream Pi baseline for the same case:
  `62.16s` (one-sample indication, not a distribution claim).
- Tokens: input `14,919`, output `4,774`, cache read `76,416`.
- Three simultaneous real RPC prompts: all completed their MCP call and
  `agent_end`; individual `3.045-3.325s`, wall time `3.360s`.

Run the repeatable checks:

```powershell
.\.venv\Scripts\python.exe scripts\benchmarks\pi_math_smoke.py --runtime pi-rust
.\.venv\Scripts\python.exe scripts\benchmarks\pi_math_benchmark.py --runtime pi-rust
```

## Runtime selection

FastAPI defaults to `pi-rust`. Set `OOPSNOTE_RPC_RUNTIME=pi` only for explicit
upstream-Pi diagnostics. A failed run is retried fresh on the same runtime and
never changes runtime or backend inside the run.
