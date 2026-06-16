# Hermes-Lite

Language: [English](#english) | [简体中文](#简体中文)

## English

> Lightweight trimmed Hermes Agent core, based on Hermes Agent v0.16.0.

### Overview

Hermes-Lite keeps the general agent runtime, model-provider plumbing, prompt
assembly, memory support, session recall, web research tools, and the tool
registry from Hermes Agent while removing high-risk local automation from 
the default toolset.

This repository is intended as a small, web-safe agent core that can be embedded
or extended without database-backedRAG, browser automation, terminal execution, 
or media-generation features by default.

### Included

- Tool-calling conversation loop
- OpenAI-compatible provider support
- Web search and page extraction tools
- Persistent memory and per-user profile helpers
- Session search, todo planning, and clarification tools
- Skill management code retained for administrator/developer opt-in use
- Tool registry with dangerous local tools blocked from auto-discovery

### Default Toolset

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


### Project Layout

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

### Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with the API key for your selected provider, then instantiate or run
the agent through `run_agent.py` / your embedding application.

### Configuration

The included `config.yaml` defaults to a custom OpenAI-compatible provider
configuration. Keep provider API keys in `.env`; do not commit secrets.

### Validation

For a quick syntax check:

```bash
python -m py_compile run_agent.py model_tools.py toolsets.py
```

### License

MIT. See [LICENSE](LICENSE).

## 简体中文

> 基于 Hermes Agent v0.16.0 的轻量裁剪版 Agent 核心。

### 概述

Hermes-Lite 保留 Hermes Agent 的通用 Agent 运行时、模型提供商接入、提示词组装、记忆支持、会话召回、Web 研究工具和工具注册机制，同时从默认工具集中移除了高风险本地自动化能力。

这个仓库面向需要嵌入或二次扩展的轻量、Web 安全 Agent 核心；默认不包含数据库 RAG、浏览器自动化、终端执行或媒体生成能力。

### 包含内容

- Tool-calling 对话循环
- OpenAI 兼容模型提供商支持
- Web 搜索与网页内容提取工具
- 持久化记忆与 per-user 用户画像辅助能力
- 会话搜索、待办规划和澄清问题工具
- 保留技能管理代码，但仅供管理员/开发者显式启用
- 工具注册中心默认阻止危险本地工具自动发现

### 默认工具集

默认 `agent` 工具集只暴露以下通用工具：

| 工具 | 用途 |
|------|------|
| `web_search` | 搜索公开网页来源 |
| `web_extract` | 提取网页内容 |
| `memory` | 保存稳定的用户/项目偏好 |
| `session_search` | 召回历史会话 |
| `todo` | 跟踪任务步骤 |
| `clarify` | 提出简洁的澄清问题 |

包含 `skill_manage` 的 `skills` 工具集仅在管理员或开发者显式启用时可用。


### 项目结构

```text
Hermes-Lite/
├── agent/              # Agent 核心运行时
├── tools/              # 工具注册中心和保留的通用工具
├── hermes_cli/         # 轻量配置/认证兼容辅助模块
├── providers/          # 模型提供商扩展接口
├── plugins/            # 最小插件命名空间包
├── services/           # 保留的小型服务辅助模块
├── scripts/            # 工具脚本
├── toolsets.py         # 默认工具集定义
├── model_tools.py      # 工具 schema 加载与分发胶水层
├── run_agent.py        # Agent 主入口
└── config.yaml         # 本地默认配置
```

### 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 中填写所选模型提供商的 API key，然后通过 `run_agent.py` 或你的宿主应用实例化/运行 Agent。

### 配置

仓库中的 `config.yaml` 默认使用自定义 OpenAI 兼容提供商配置。API key 应放在 `.env` 中，不要提交密钥。

### 验证

快速语法检查：

```bash
python -m py_compile run_agent.py model_tools.py toolsets.py
```

### 许可证

MIT。详见 [LICENSE](LICENSE)。
