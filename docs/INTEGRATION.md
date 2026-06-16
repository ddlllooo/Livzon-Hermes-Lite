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

Fill the provider API key values in `.env`.

## Configuration

- `config.yaml` contains the default provider and runtime settings.
- `.env` contains secrets and deployment-specific API keys.
- Runtime state such as sessions, memories, and caches should stay local and is
  ignored by git.

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
