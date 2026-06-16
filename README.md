# Hermes-Lite

> Enterprise AI Agent framework for bid intelligence & knowledge retrieval, trimmed from [Hermes Agent v0.16.0](https://github.com/NousResearch/hermes-agent) by Nous Research.

## 概述

Hermes-Lite 是从 Hermes Agent v0.16.0 裁剪而来的精简版 Agent 引擎，专为**企业招标智能匹配**和**知识库检索问答**设计。保留了核心 Agent 循环、工具框架和技能系统，新增了 OceanBase 原生混合检索管道和六维度招标匹配引擎。

### 核心特性

- **Tool-Calling Agent Loop** — 核心对话循环，支持并行/串行工具调用
- **OceanBase 原生混合检索** — 向量语义 + BM25 关键词 + RRF 融合，单条 SQL 完成
- **六维度招标匹配** — 行业/地域/资质/预算/能力/业绩 + 中标概率预测
- **Controlled Tool Exposure** — 普通用户默认仅暴露业务查询/分析工具，管理员可按需启用扩展工具集
- **Memory System** — 跨会话持久化记忆
- **Multi-Provider Support** — 兼容 OpenAI API（DeepSeek、OpenRouter、智谱等）

## 目录结构

```
Hermes-Lite/
├── agent/                          # Agent 核心引擎（勿修改）
│   ├── conversation_loop.py        # 核心对话循环
│   ├── agent_init.py               # Agent 初始化
│   ├── context_compressor.py       # 上下文压缩
│   ├── prompt_builder.py           # 系统提示词构建
│   └── ...
├── tools/                          # 工具框架
│   ├── registry.py                 # 工具注册中心（自发现机制）
│   ├── knowledge_tool.py           # 📚 knowledge_search（知识库检索）
│   ├── tender_tools.py             # 🔍📊📋🎯 招标四工具
│   ├── memory_tool.py              # 跨会话记忆
│   ├── session_search_tool.py      # 对话历史搜索
│   ├── todo_tool.py                # 任务规划
│   ├── clarify_tool.py             # 意图澄清
│   ├── web_tools.py                # 网络搜索/提取
│   └── skill_manager_tool.py       # 技能管理（管理员/开发显式启用）
├── services/                       # 业务逻辑层
│   ├── config.py                   # 配置管理（.env 读取）
│   ├── chunk_store.py              # OceanBase 混合检索
│   ├── embedding_service.py        # Embedding 向量生成
│   ├── rerank_service.py           # Cross-Encoder 精排
│   ├── retrieval_pipeline.py       # 四阶段检索管道
│   ├── document_ingestion.py       # 文档解析/分块/写入
│   └── tender_service.py           # 招标匹配/推荐/评分引擎
├── scripts/                        # 运维脚本
│   ├── init_knowledge_db.sql       # 知识库建表
│   ├── init_tender_db.sql          # 招标系统建表
│   ├── ingest_cli.py               # 知识库管理 CLI
│   └── tender_cli.py               # 招标数据管理 CLI
├── data/examples/                  # 示例数据
│   ├── tenders_example.json        # 招标数据样例
│   └── companies_example.json      # 企业数据样例
├── docs/
│   └── INTEGRATION.md              # 接入操作文档（完整）
├── toolsets.py                     # 工具集配置
├── model_tools.py                  # 工具定义加载
├── requirements.txt                # 生产依赖
└── requirements-dev.txt            # 开发依赖
```

## 工具清单

### 保留的 Core 工具（6 个）

| 工具 | 文件 | 功能 |
|------|------|------|
| `memory` | `memory_tool.py` | 跨会话持久化记忆 |
| `session_search` | `session_search_tool.py` | 对话历史搜索 |
| `todo` | `todo_tool.py` | 任务规划跟踪 |
| `clarify` | `clarify_tool.py` | 用户意图澄清 |
| `web_search` | `web_tools.py` | 网络搜索 |
| `web_extract` | `web_tools.py` | 网页内容提取 |

### 新增业务工具（5 个）

| 工具 | 文件 | 功能 | 参数 |
|------|------|------|------|
| 📚 `knowledge_search` | `knowledge_tool.py` | 知识库混合检索 | `query`, `top_k` |
| 🔍 `tender_search` | `tender_tools.py` | 招标项目搜索 | `keyword`, `industry`, `region`, `budget_min/max`, `deadline_before`, `status` |
| 🎯 `tender_recommend` | `tender_tools.py` | 为企业推荐招标 | `company_id`, `top_k`, `min_score`, `industry`, `region` |
| 📊 `tender_match` | `tender_tools.py` | 企业-招标匹配评分 | `company_id`, `tender_id` |
| 📋 `tender_analyze` | `tender_tools.py` | 招标深度分析 | `tender_id` |

### 移除的工具

| 工具 | 移除原因 |
|------|---------|
| `read_file`, `write_file`, `patch`, `search_files` | 文件操作 — Web 应用不需要 |
| `terminal`, `process` | 命令行执行 — Web 应用不需要 |
| `delegate_task` | 子代理委派 — MVP 阶段不需要 |
| `cronjob` | 定时任务 — Web 应用不需要 |
| `browser_*` | 浏览器自动化 — Web 应用不需要 |
| `image_*`, `video_*`, `text_to_speech` | 多媒体工具 — Web 应用不需要 |

## 工具集配置

| 工具集 | 包含工具 | 说明 |
|--------|---------|------|
| `web` | `web_search`, `web_extract` | 网络研究 |
| `memory` | `memory` | 持久化记忆 |
| `session_search` | `session_search` | 对话历史 |
| `todo` | `todo` | 任务规划 |
| `clarify` | `clarify` | 意图澄清 |
| `skills` | `skill_manage` | 技能管理（管理员/开发显式启用） |
| `knowledge` | `knowledge_search` | 知识库检索 |
| `tender` | `tender_search`, `tender_recommend`, `tender_match`, `tender_analyze` | 招标智能匹配 |
| `agent` | 默认 11 个工具（不含 `skill_manage`） | Hermes-Lite 普通用户完整工具集 |

## 检索管道架构

```
用户 Query
    │
    ▼
┌─────────────────────────────────────────────────┐
│  ① OceanBase 原生混合检索（单条 SQL）             │
│   向量路：Query → Embedding → COSINE_DISTANCE    │
│   关键词路：Query → MATCH AGAINST → BM25          │
│   RRF 融合：1/(k+rank) 加权 → ~30 候选子块       │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  ② Rerank 精排（Cross-Encoder）                   │
│   逐个 (Query, Child_Chunk) → 相关性打分          │
│   → Top-10 子块                                   │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  ③ parent_id 反查 + 去重聚合                      │
│   子块 → parent_id → 分数叠加 → Top-3 父块       │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│  ④ 父块完整文本 → LLM Context → 生成回答          │
└─────────────────────────────────────────────────┘
```

## 招标匹配引擎

### 六维度匹配模型

| 维度 | 权重 | 评分逻辑 |
|------|------|----------|
| 行业匹配 | 20% | 主营行业完全匹配 100、能力覆盖 80、不匹配 20 |
| 资质匹配 | 25% | 硬性门槛，全部满足 100、部分满足按比例、不满足 ≤10 |
| 能力匹配 | 20% | 技术要求关键词与企业能力标签匹配度 |
| 业绩匹配 | 15% | 同行业历史中标数量、金额、中标率 |
| 地域匹配 | 10% | 同城 100、同省 75、异地 30 |
| 预算匹配 | 10% | 企业营收与项目预算的最佳比例区间 |

### 推荐等级

| 等级 | 条件 | 含义 |
|------|------|------|
| 🟢 strong | 综合分 ≥ 75 且资质 ≥ 70 | 强烈推荐投标 |
| 🟡 medium | 综合分 ≥ 55 | 建议关注 |
| 🟠 weak | 综合分 ≥ 35 | 需进一步评估 |
| ⚪ skip | 综合分 < 35 | 建议跳过 |

## 数据库表

### 知识库表

| 表名 | 用途 | 关键索引 |
|------|------|---------|
| `parent_chunks` | 父块（LLM Context） | PK: parent_id |
| `child_chunks` | 子块（检索单元） | VECTOR(1536) HNSW + FULLTEXT(ngram) |
| `documents` | 文档元信息 | PK: doc_id |

### 招标业务表

| 表名 | 用途 | 关键索引 |
|------|------|---------|
| `tenders` | 招标项目 | VECTOR(1536) HNSW + FULLTEXT(ngram) + 行业/地区/状态/截止日 |
| `companies` | 企业信息 | VECTOR(1536) HNSW + FULLTEXT(ngram) + UNIQUE(信用代码) |
| `company_qualifications` | 资质明细 | 企业ID + 资质类型/等级 |
| `company_performance` | 历史业绩 | 企业ID + 行业/中标日期 |
| `tender_matches` | 匹配缓存 | UNIQUE(tender_id, company_id) + 综合分排序 |

## 快速开始

### 1. 安装

```bash
pip install -r requirements.txt

# 可选：文档解析
pip install pymupdf python-docx chardet
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，填写 OceanBase / Embedding / Rerank 配置
```

### 3. 初始化数据库

```bash
mysql -h 127.0.0.1 -P 2881 -u root -p hermes_lite < scripts/init_knowledge_db.sql
mysql -h 127.0.0.1 -P 2881 -u root -p hermes_lite < scripts/init_tender_db.sql
```

### 4. 导入数据

```bash
# 招标数据
python scripts/tender_cli.py import-tenders data/examples/tenders_example.json

# 企业数据
python scripts/tender_cli.py import-companies data/examples/companies_example.json

# 知识库文档
python scripts/ingest_cli.py import path/to/docs/
```

### 5. 验证

```bash
python scripts/ingest_cli.py health     # 健康检查
python scripts/tender_cli.py stats      # 数据统计
python scripts/tender_cli.py recommend COM-001  # 测试推荐
```

### 6. 对话

```python
from run_agent import AIAgent

agent = AIAgent(
    model="deepseek-v4-pro",
    api_key="your-api-key",
    base_url="https://api.deepseek.com/v1",
    max_iterations=15,
)

# Agent 自动选择工具回答
response = agent.chat("推荐一些适合我们公司的招标项目")
print(response)
```

## 配置项

所有配置通过 `.env` 文件管理，详见 [INTEGRATION.md](docs/INTEGRATION.md)。

| 类别 | 变量数 | 说明 |
|------|--------|------|
| OceanBase 连接 | 7 | 数据库地址/端口/凭证/连接池 |
| Embedding 服务 | 7 | 提供商/模型/API Key/维度/批量/超时 |
| Rerank 服务 | 6 | 提供商/模型/API Key/开关/超时 |
| 检索管道参数 | 5 | 向量/BM25 Top-K / RRF-K / Rerank-N / 最终-N |

## 依赖

### 生产依赖

```
openai==2.24.0
python-dotenv==1.2.2
pyyaml==6.0.3
pydantic==2.13.4
httpx[socks]==0.28.1
requests==2.33.0
rich==14.3.3
jinja2==3.1.6
tenacity==9.1.4
psutil==7.2.2
pymysql>=1.1.0                  # OceanBase MySQL 协议
```

### 可选依赖

```
pymupdf>=1.25.0                 # PDF 解析
python-docx>=1.1.0              # DOCX 解析
chardet>=5.0.0                  # 文本编码检测
```

### 开发依赖

```
pytest==9.0.2
pytest-asyncio==1.3.0
ruff==0.15.10
```

## 技能系统

### SKILL.md 格式

```yaml
---
name: bid-analysis
description: 招标分析技能
platforms: [windows, linux]
metadata:
  hermes:
    tags: [bid, analysis]
    requires_tools:
      - tender_search
      - tender_match
    requires_toolsets:
      - tender
---

# 招标分析

技能内容...
```

### 管理 API

技能管理工具不在默认 `agent` 工具集中暴露；仅在管理员或开发集成场景中显式启用 `skills` 工具集。

## 版本信息

| 项目 | 值 |
|------|-----|
| Hermes-Lite | 0.2.0 |
| 基于 | Hermes Agent v0.16.0 |
| 裁剪日期 | 2026-06-06 |
| 业务功能新增 | 2026-06-11 |

## 裁剪统计

| 指标 | 原版 Hermes | 裁剪后 | 新增业务层 |
|------|-------------|--------|-----------|
| 文件数 | 5,295 | ~170 | +14 |
| 代码行数 | 1,015,271 | ~64,000 | +~3,500 |
| 工具数 | 40+ | 7 | +5 |
| 数据库表 | 2 | 2 | +8 |

## 许可证

MIT License (继承自 Hermes Agent)
