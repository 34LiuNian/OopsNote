# Per-agent AI config

This backend supports a multi-agent flow (ocr/solver/tagger). Each agent can use a different provider, API key, endpoint, and model.

## Enable multi-agent

Set:

- `ENABLE_MULTI_AGENT=true`

## Use a config file (recommended)

Point the backend to a TOML file:

- `AGENT_CONFIG_PATH=/abs/path/to/agent_config.toml`
	- or `AI_AGENT_CONFIG=/abs/path/to/agent_config.toml`

An example is provided at `backend/agent_config.example.toml`.

In the TOML file, configure your OpenAI-compatible gateway via `base_url`:

- `base_url = "http://127.0.0.1:23333/v1"`

Note: the OpenAI Python SDK expects `/v1` in the base URL.

## Per-agent env vars

For each agent name in `{OCR,SOLVER,TAGGER}`:

- `AGENT_<NAME>_PROVIDER` = `openai` | `stub`
- `AGENT_<NAME>_API_KEY` = provider key
- `AGENT_<NAME>_MODEL` = model name
- `AGENT_<NAME>_TEMPERATURE` = float
- `AGENT_<NAME>_BASE_URL` = **openai only** (OpenAI-compatible endpoint/proxy)

If `AGENT_<NAME>_PROVIDER` is omitted, that agent falls back to the default `ai_client` chosen from `OPENAI_API_KEY` / stub.

## OpenAI-compatible gateway (local)

**Base URL**

- `http://127.0.0.1:23333`

When configuring this project (OpenAI SDK), use:

- `http://127.0.0.1:23333/v1`

Example:

```bash
export OPENAI_BASE_URL="http://127.0.0.1:23333/v1"
```

## Config file (TOML)

Set `AGENT_CONFIG_PATH` to a TOML file. It supports a `[default]` section plus `[agents.<NAME>]` overrides.

Priority order:

1. `AGENT_<NAME>_*` env vars
2. `[agents.<NAME>]` in config file
3. `[default]` in config file
4. default `ai_client`

### Example `agent_config.toml`

```toml
[default]
provider = "openai"
api_key = "env:OPENAI_API_KEY"
base_url = "env:OPENAI_BASE_URL" # optional
model = "gpt-4o-mini"
temperature = 0.2

[agents.SOLVER]
provider = "openai"
api_key = "env:OPENAI_API_KEY"
base_url = "env:OPENAI_BASE_URL"
model = "gpt-4o-mini"
temperature = 0.2

[agents.TAGGER]
provider = "openai"
api_key = "env:OPENAI_API_KEY"
model = "gpt-4o-mini"
temperature = 0.1
```

Enable it:

```bash
export ENABLE_MULTI_AGENT=true
export AGENT_CONFIG_PATH="/abs/path/to/agent_config.toml"
```

## Default client env vars

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` (optional)
- `OPENAI_MODEL` (default `gpt-4o-mini`)
- `OPENAI_TEMPERATURE` (default `0.2`)

（已移除 Gemini：统一使用 OpenAI 协议网关）

## Example

```bash
export ENABLE_MULTI_AGENT=true

# cheap model for OCR/tagging
export AGENT_OCR_PROVIDER=openai
export AGENT_OCR_API_KEY="$OPENAI_API_KEY"
export AGENT_OCR_BASE_URL="https://api.openai.com/v1"
export AGENT_OCR_MODEL="gpt-4o-mini"

export AGENT_TAGGER_PROVIDER=openai
export AGENT_TAGGER_API_KEY="$OPENAI_API_KEY"
export AGENT_TAGGER_BASE_URL="https://api.openai.com/v1"
export AGENT_TAGGER_MODEL="gpt-4o-mini"

# strong model for solving
export AGENT_SOLVER_PROVIDER=openai
export AGENT_SOLVER_API_KEY="$OPENAI_API_KEY"
export AGENT_SOLVER_BASE_URL="$OPENAI_BASE_URL"
export AGENT_SOLVER_MODEL="gpt-4o-mini"
```

## Notes

本项目仅支持 OpenAI 协议（可接 OpenAI-compatible gateway）。
- `BASE_URL` is only supported for OpenAI-compatible providers.
