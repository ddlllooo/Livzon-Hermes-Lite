# Hermes-Lite

> Lightweight trimmed Hermes Agent core, based on Hermes Agent v0.16.0.

## Overview

Hermes-Lite keeps the general agent runtime, model-provider plumbing, prompt
assembly, memory support, session recall, web research tools, and the tool
registry from Hermes Agent while removing product-specific business layers and
high-risk local automation from the default toolset.

This repository is intended as a small, web-safe agent core that can be embedded
or extended without carrying bid intelligence, tender matching, database-backed
RAG, browser automation, terminal execution, or media-generation features by
default.

## Included

- Tool-calling conversation loop
- OpenAI-compatible provider support
- Web search and page extraction tools
- Persistent memory and per-user profile helpers
- Session search, todo planning, and clarification tools
- Skill management code retained for administrator/developer opt-in use
- Tool registry with dangerous local tools blocked from auto-discovery

## Default Toolset

The default `agent` toolset exposes only these general-purpose tools:

| Tool | Purpose |
|------|---------|
| `web_search` | Search public web sources |
| `web_extract` | Extract web page content |
| `memory` | Store durable user/project preferences |
| `session_search` | Recall prior sessions |
| `todo` | Track task steps |
| `clarify` | Ask concise clarification questions |

The `skills` toolset containing `skill_manage` remains available only when
explicitly enabled by an administrator or developer.

## Removed From The Default Surface

- Tender search, tender recommendation, tender matching, tender analysis
- Six-dimension bid matching and win-probability scoring
- OceanBase-backed knowledge/RAG pipeline
- Business sample datasets and database initialization scripts
- Terminal, file mutation, code execution, process, cron, delegate, browser,
  computer-use, image/video/TTS tools from auto-discovery

## Project Layout

```text
Hermes-Lite/
├── agent/              # Core agent runtime
├── tools/              # Tool registry and retained general tools
├── hermes_cli/         # Lightweight config/auth compatibility helpers
├── providers/          # Provider extension interfaces
├── plugins/            # Minimal plugin namespace packages
├── services/           # Small retained service helpers
├── scripts/            # Utility scripts
├── toolsets.py         # Default toolset definitions
├── model_tools.py      # Tool schema loading and dispatch glue
├── run_agent.py        # Main agent entrypoint
└── config.yaml         # Local default configuration
```

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with the API key for your selected provider, then instantiate or run
the agent through `run_agent.py` / your embedding application.

## Configuration

The included `config.yaml` defaults to a custom OpenAI-compatible provider
configuration. Keep provider API keys in `.env`; do not commit secrets.

## Validation

For a quick syntax check:

```bash
python -m py_compile run_agent.py model_tools.py toolsets.py
```

## License

MIT. See [LICENSE](LICENSE).
