# Hermes-Lite Integration Guide

> Applies to Hermes-Lite, a lightweight trimmed fork of Hermes Agent v0.16.0.

## Architecture

Hermes-Lite provides a compact agent runtime with a conservative default tool
surface:

```text
Application / Web API
        |
        v
Hermes-Lite Agent Core
        |
        +-- conversation loop
        +-- provider resolution
        +-- prompt assembly
        +-- memory/session helpers
        +-- tool registry
        |
        +-- default tools:
            web_search / web_extract / memory / session_search / todo / clarify
```

## Installation

```bash
pip install -r requirements.txt
cp .env.example .env
```

For standalone development, fill the provider API key values in `.env`. For
Dazah central-agent deployment, do not store real model-provider API keys in
Hermes-Lite; use the Dazah LLM proxy token described below.

## Configuration

- `config.yaml` contains the default provider and runtime settings.
- `.env` contains secrets and deployment-specific API keys.
- Runtime state such as sessions, memories, and caches should stay local and is
  ignored by git.

## Dazah Central Agent Adapter

Dazah uses Hermes-Lite as an independent orchestration service behind the Dazah
backend Agent gateway:

```text
Dazah frontend floating assistant
        |
        v
Dazah backend /api/v1/agent/chat
        |
        v
Hermes-Lite services.dazah_agent_service:/v1/chat
        |
        +-- LLM: Dazah /api/v1/agent/llm/chat/completions
        +-- Tools: Dazah /api/v1/agent/tools/execute
```

Required Hermes-Lite `.env` values:

```bash
HERMES_AGENT_TOKEN=change-me
AGENT_LLM_PROXY_TOKEN=change-me
DAZAH_API_BASE_URL=http://127.0.0.1:8000/api/v1
DAZAH_AGENT_TOOL_TOKEN=change-me
DAZAH_LLM_BASE_URL=http://127.0.0.1:8000/api/v1/agent/llm
DAZAH_LLM_MODEL=dazah-active-text
```

Run the adapter:

```bash
uvicorn services.dazah_agent_service:app --host 0.0.0.0 --port 8100
```

Run the adapter with Docker:

```bash
docker build -t hermes-lite:prod .
docker run --rm -p 8100:8100 --env-file .env hermes-lite:prod
```

For local Dazah development, after the Dazah backend compose stack has created
the `dazah-backend_default` network, run:

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

The development compose file mounts the repository into `/app` and starts
Uvicorn with `--reload`, so Python source edits are picked up automatically
after the first image build. Rebuild only when dependencies, Dockerfile, or
entrypoint files change.

When running inside the Dazah production compose network, use service names
instead of localhost:

```bash
DAZAH_API_BASE_URL=http://backend:8000/api/v1
DAZAH_LLM_BASE_URL=http://backend:8000/api/v1/agent/llm
```

Security boundaries:

- Hermes-Lite only stores service-to-service tokens, not model-provider keys.
- The active text model is resolved by Dazah backend from the platform LLM
  configuration table on every request.
- The `dazah` toolset only calls the Dazah Agent tool gateway.
- Identity/warehouse/procurement/quality operation whitelisting, write
  confirmations, business permissions, audit records, Feishu credentials, and
  transaction execution stay in the Dazah backend.

## Toolsets

| Toolset | Tools | Notes |
|---------|-------|-------|
| `agent` | `web_search`, `web_extract`, `memory`, `session_search`, `todo`, `clarify` | Default lightweight surface |
| `web` | `web_search`, `web_extract` | Public web research |
| `memory` | `memory` | Durable preferences and facts |
| `session_search` | `session_search` | Past session recall |
| `todo` | `todo` | Task planning |
| `clarify` | `clarify` | Clarifying questions |
| `skills` | `skill_manage` | Administrator/developer opt-in only |
| `dazah` | `dazah_tool` | Dazah identity/warehouse/procurement/quality gateway only |

## Removed Business Extensions

Hermes-Lite intentionally does not ship tender/bid-intelligence extensions:

- no tender search or recommendation tools
- no company-to-tender matching tools
- no six-dimension scoring model
- no win-probability prediction
- no OceanBase-backed RAG schema or ingestion CLI
- no business sample datasets

These can be added later as separate plugins or application-layer services if a
deployment needs them.

## Operational Notes

- Keep `.env`, memory files, and local runtime state out of version control.
- Enable administrator-only tools explicitly instead of adding them to the
  default `agent` toolset.
- Treat browser, terminal, file mutation, code execution, process, cron, and
  delegate tools as non-default capabilities.

## Smoke Check

```bash
python -m py_compile run_agent.py model_tools.py toolsets.py
```
