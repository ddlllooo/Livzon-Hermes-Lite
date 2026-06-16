# Hermes-Lite 引擎接入操作文档

> 版本：v0.1.0 | 更新日期：2026-06-11
> 适用：Hermes-Lite（trimmed Hermes v0.16.0 fork）

---

## 目录

- [1. 系统架构总览](#1-系统架构总览)
- [2. 环境搭建与首次部署](#2-环境搭建与首次部署)
- [3. 配置项清单（.env 文件）](#3-配置项清单env-文件)
- [4. 数据库初始化](#4-数据库初始化)
- [5. 管理员端操作](#5-管理员端操作)
  - [5.1 招标数据管理](#51-招标数据管理)
  - [5.2 企业数据管理](#52-企业数据管理)
  - [5.3 知识库文档管理](#53-知识库文档管理)
  - [5.4 系统运维](#54-系统运维)
- [6. 用户端操作（Agent 对话）](#6-用户端操作agent-对话)
- [7. 可配置项汇总（无需改代码）](#7-可配置项汇总无需改代码)
- [8. 需要改代码的场景及方案](#8-需要改代码的场景及方案)
- [9. 前端接入指南](#9-前端接入指南)
- [10. Agent 工具 API 参考](#10-agent-工具-api-参考)
- [11. 数据导入格式规范](#11-数据导入格式规范)
- [12. 故障排查](#12-故障排查)

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    Hermes-Lite 前端                         │
│              管理员后台          用户对话界面             │
└──────────┬──────────────────────────┬───────────────────┘
           │ HTTP API                 │ HTTP API
           ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                 Hermes-Lite                      │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Agent 循环（LLM 对话 + 工具调用）                │   │
│  │                                                    │   │
│  │  用户工具（6个）：                                  │   │
│  │  memory / session_search / todo / clarify           │   │
│  │  web_search / web_extract                           │   │
│  │                                                    │   │
│  │  知识库工具（1个）：                                │   │
│  │  📚 knowledge_search                                │   │
│  │                                                    │   │
│  │  招标工具（4个）：                                  │   │
│  │  🔍 tender_search   🎯 tender_recommend            │   │
│  │  📊 tender_match    📋 tender_analyze               │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  服务层                                            │   │
│  │  config.py          配置管理（.env 读取）          │   │
│  │  embedding_service   Embedding 向量生成             │   │
│  │  rerank_service      Cross-Encoder 精排             │   │
│  │  chunk_store         OceanBase 混合检索             │   │
│  │  retrieval_pipeline  四阶段检索管道                 │   │
│  │  document_ingestion  文档解析/分块/写入             │   │
│  │  tender_service      招标匹配/推荐/评分             │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  OceanBase V4.4.1+                                 │   │
│  │                                                    │   │
│  │  知识库表：              招标业务表：                │   │
│  │  parent_chunks          tenders                    │   │
│  │  child_chunks           companies                  │   │
│  │  documents              company_qualifications     │   │
│  │                         company_performance        │   │
│  │                         tender_matches             │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 核心设计原则

- **工具自注册**：`tools/*.py` 中模块级 `registry.register()` 调用，Core 自动发现，新增工具不改 Core 代码
- **配置外置**：所有可调参数通过 `.env` 环境变量或数据库，不硬编码
- **服务解耦**：业务逻辑在 `services/` 层，工具层只是薄壳调用
- **依赖注入**：`RetrievalPipeline` / `TenderService` 通过构造函数注入 `chunk_store` / `embedder` / `reranker`

---

## 2. 环境搭建与首次部署

### 2.1 系统要求

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | ≥3.11, <3.14 | |
| OceanBase | V4.4.1+ | MySQL 模式，需支持 VECTOR 类型 |
| pip | 最新 | 或用 uv |

### 2.2 安装步骤

```bash
# ① 克隆项目
cd E:\Hermes\Hermes-Lite

# ② 安装依赖
pip install -r requirements.txt

# ③ 可选：安装文档解析库（按需）
pip install pymupdf          # PDF 解析
pip install python-docx       # DOCX 解析
pip install chardet           # 编码检测

# ④ 配置 .env（见第 3 节）

# ⑤ 初始化数据库（见第 4 节）

# ⑥ 验证
python scripts/ingest_cli.py health
python scripts/tender_cli.py stats
```

### 2.3 项目目录结构

```
Hermes-Lite/
├── .env                          ← 所有配置（第 3 节）
├── requirements.txt              ← 生产依赖
├── requirements-dev.txt          ← 开发依赖
│
├── services/                     ← 业务逻辑层
│   ├── config.py                 ← 配置读取（从 .env）
│   ├── chunk_store.py            ← OceanBase 连接 + 混合检索
│   ├── embedding_service.py      ← Embedding API 调用
│   ├── rerank_service.py         ← Rerank API 调用
│   ├── retrieval_pipeline.py     ← 知识库四阶段检索管道
│   ├── document_ingestion.py     ← 文档解析/分块/写入
│   └── tender_service.py         ← 招标匹配/推荐/评分
│
├── tools/                        ← Agent 工具注册层
│   ├── registry.py               ← 工具注册中心（Core）
│   ├── knowledge_tool.py         ← knowledge_search 工具
│   └── tender_tools.py           ← tender_search/match/recommend/analyze
│
├── toolsets.py                   ← 工具集定义（哪些工具暴露给 Agent）
│
├── scripts/                      ← 运维脚本
│   ├── init_knowledge_db.sql     ← 知识库建表
│   ├── init_tender_db.sql        ← 招标系统建表
│   ├── ingest_cli.py             ← 知识库文档导入 CLI
│   └── tender_cli.py             ← 招标数据管理 CLI
│
├── data/examples/                ← 示例数据
│   ├── tenders_example.json      ← 招标数据样例
│   └── companies_example.json    ← 企业数据样例
│
├── agent/                        ← Agent 引擎核心（勿修改）
├── tools/                        ← 工具注册中心（勿修改 registry.py）
├── model_tools.py                ← 工具定义编排（勿修改）
└── run_agent.py                  ← Agent 启动入口
```

---

## 3. 配置项清单（.env 文件）

> **所有配置均通过 `.env` 文件管理，修改后重启生效，无需改代码。**

### 3.1 OceanBase 数据库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OCEANBASE_HOST` | `127.0.0.1` | 数据库地址 |
| `OCEANBASE_PORT` | `2881` | 端口（MySQL 协议） |
| `OCEANBASE_USER` | `root` | 用户名 |
| `OCEANBASE_PASSWORD` | （空） | 密码 |
| `OCEANBASE_DATABASE` | `hermes_lite` | 数据库名 |
| `OB_POOL_MIN` | `2` | 连接池最小连接数 |
| `OB_POOL_MAX` | `10` | 连接池最大连接数 |

### 3.2 Embedding 服务

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EMBEDDING_PROVIDER` | `zhipu` | 提供商：`openai` / `zhipu`/`qwen` |
| `EMBEDDING_MODEL` | `Embedding-3`/`text-embedding-v4` | 模型名 |
| `EMBEDDING_BASE_URL` | `pip install zai-sdk`/`https://dashscope.aliyuncs.com/compatible-mode/v1` | Python SDK / BASE_URL |
| `EMBEDDING_API_KEY` | （必填） | API 密钥 |
| `EMBEDDING_DIMENSIONS` | `1536` | 向量维度（需与建表一致） |
| `EMBEDDING_BATCH_SIZE` | `64`/`10` | 批量 Embedding 每批数量 |
| `EMBEDDING_TIMEOUT` | `30` | API 超时（秒） |

**切换 Embedding 提供商只需改这 4 个值：**

```bash
# Qwen
EMBEDDING_PROVIDER=Qwen
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-***

# OpenAI
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-***

# 智谱
EMBEDDING_PROVIDER=zhipu
EMBEDDING_MODEL=embedding-3
EMBEDDING_BASE_URL=https://open.bigmodel.cn/api/paas/v4
EMBEDDING_API_KEY=***
```

### 3.3 Rerank 精排服务

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RERANK_ENABLED` | `true` | 是否启用 Rerank（`false` 则跳过精排） |
| `RERANK_PROVIDER` | `BAAI`/`Qwen` | 提供商：`bge` / `jina` / `Qwen` |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3`/`Qwen3-Reranker` | 模型名 |
| `RERANK_BASE_URL` | （空，用默认） | API 地址 |
| `RERANK_API_KEY` | （空） | API 密钥（BGE 本地部署可留空） |
| `RERANK_TIMEOUT` | `30` | API 超时（秒） |

**切换 Rerank 提供商：**

```bash
# BGE（本地部署，如 Xinference / TEI）
RERANK_PROVIDER=bge
RERANK_BASE_URL=http://localhost:9997/v1
RERANK_MODEL=BAAI/bge-reranker-v2-m3

# Qwen
RERANK_PROVIDER=Qwen
RERANK_BASE_URL=https://dashscope.aliyuncs.com/compatible-api/v1
RERANK_MODEL=qwen3-vl-rerank
RERANK_API_KEY=*****

# Cohere
RERANK_PROVIDER=cohere
RERANK_MODEL=rerank-v3.5
RERANK_API_KEY=***

# 禁用 Rerank（退化为跳过精排）
RERANK_ENABLED=false
```

### 3.4 检索管道参数

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RETRIEVAL_VECTOR_TOP_K` | `20` | 向量检索候选数 |
| `RETRIEVAL_BM25_TOP_K` | `20` | BM25 检索候选数 |
| `RETRIEVAL_RRF_K` | `60` | RRF 融合常数 k（越大越平滑） |
| `RETRIEVAL_RERANK_TOP_N` | `10` | Rerank 后保留数 |
| `RETRIEVAL_FINAL_TOP_N` | `3` | 最终返回给 LLM 的父块数 |

### 3.5 完整 .env 模板

```bash
# ═══════════════════════════════════════════════
# Hermes-Lite 配置
# ═══════════════════════════════════════════════

# ── OceanBase ──────────────────────────────────
OCEANBASE_HOST=127.0.0.1
OCEANBASE_PORT=2881
OCEANBASE_USER=root
OCEANBASE_PASSWORD=your_password
OCEANBASE_DATABASE=hermes_lite
OB_POOL_MIN=2
OB_POOL_MAX=10

# ── Embedding ──────────────────────────────────
EMBEDDING_PROVIDER=qwen
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=sk-your-key
EMBEDDING_DIMENSIONS=1536
EMBEDDING_BATCH_SIZE=64
EMBEDDING_TIMEOUT=30

# ── Rerank ─────────────────────────────────────
RERANK_ENABLED=true
RERANK_PROVIDER=qwen
RERANK_MODEL=qwen3-vl-rerank
RERANK_BASE_URL=https://dashscope.aliyuncs.com/compatible-api/v1
RERANK_API_KEY=
RERANK_TIMEOUT=30

# ── 检索参数 ───────────────────────────────────
RETRIEVAL_VECTOR_TOP_K=20
RETRIEVAL_BM25_TOP_K=20
RETRIEVAL_RRF_K=60
RETRIEVAL_RERANK_TOP_N=10
RETRIEVAL_FINAL_TOP_N=3

# ── 其他已有配置 ───────────────────────────────
# TAVILY_API_KEY=tvly-***     (Web 搜索)
# LLM_API_KEY=sk-***          (主 LLM)
```

---

## 4. 数据库初始化

### 4.1 执行建表脚本

```bash
# 连接 OceanBase（MySQL 协议）
mysql -h 127.0.0.1 -P 2881 -u root -p

# 在 MySQL 命令行中执行：
source /path/to/scripts/init_knowledge_db.sql
source /path/to/scripts/init_tender_db.sql
```

或直接：

```bash
mysql -h 127.0.0.1 -P 2881 -u root -p hermes_lite < scripts/init_knowledge_db.sql
mysql -h 127.0.0.1 -P 2881 -u root -p hermes_lite < scripts/init_tender_db.sql
```

### 4.2 创建的表清单

| 表名 | 所属 | 用途 |
|------|------|------|
| `parent_chunks` | 知识库 | 父块（完整文档片段，LLM Context） |
| `child_chunks` | 知识库 | 子块（VECTOR + FULLTEXT 索引，检索单元） |
| `documents` | 知识库 | 文档元信息（可选） |
| `tenders` | 招标 | 招标项目（结构化 + 语义向量） |
| `companies` | 招标 | 企业信息 |
| `company_qualifications` | 招标 | 企业资质证书明细 |
| `company_performance` | 招标 | 企业历史中标业绩 |
| `tender_matches` | 招标 | 匹配结果缓存 |

### 4.3 验证建表

```bash
mysql -h 127.0.0.1 -P 2881 -u root -p -e "
  USE hermes_lite;
  SHOW TABLES;
  SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES
  WHERE TABLE_SCHEMA='hermes_lite';
"
```

---

## 5. 管理员端操作

### 5.1 招标数据管理

#### 批量导入招标数据

准备 JSON 文件（参考 `data/examples/tenders_example.json`），执行：

```bash
python scripts/tender_cli.py import-tenders path/to/tenders.json
```

#### 批量导入企业数据

准备 JSON 文件（参考 `data/examples/companies_example.json`），执行：

```bash
python scripts/tender_cli.py import-companies path/to/companies.json
```

> 企业数据支持嵌套导入：`qualifications_detail`（资质明细）和 `performance_history`（历史业绩）会自动关联写入。

#### 添加单条数据

```bash
# 添加单条招标
python scripts/tender_cli.py add-tender '{"title":"某项目","industry":"IT","region":"北京","budget_min":100,"budget_max":500,"deadline":"2026-08-01"}'

# 添加单家企业
python scripts/tender_cli.py add-company '{"name":"某公司","industry":"IT","region":"北京","registered_capital":5000}'
```

#### 查看统计

```bash
python scripts/tender_cli.py stats
```

输出示例：
```
Hermes-Lite 招标系统统计
==================================================
  招标项目总数:  156
  活跃招标:      42
  企业总数:      28
  资质记录:      87
  历史业绩:      134
  匹配缓存:      0

  行业分布 (Top 5):
    IT                   18 个
    医疗                  8 个
    建筑                  6 个
    教育                  5 个
    交通                  5 个
```

#### 测试推荐

```bash
python scripts/tender_cli.py recommend COM-001 --top-k 5
```

#### 测试匹配

```bash
python scripts/tender_cli.py match COM-001 ZB-2026-001
```

#### 测试搜索

```bash
python scripts/tender_cli.py search --industry IT --region 北京
python scripts/tender_cli.py search --keyword "智慧园区"
```

### 5.2 企业数据管理

#### 企业数据 JSON 格式

```json
{
  "company_id": "COM-001",
  "name": "某科技股份有限公司",
  "unified_code": "91110000MA12345678",
  "industry": "IT",
  "region": "北京",
  "registered_capital": 5000,
  "employee_count": 500,
  "revenue": 20000,
  "established_year": 2010,
  "capabilities": ["大数据平台", "Hadoop", "云计算"],
  "qualification_level": "一级",
  "certifications": ["ISO9001", "CMMI5"],
  "total_bids": 120,
  "total_wins": 45,
  "win_rate": 37.5,
  "total_win_amount": 35000,
  "qualifications_detail": [
    {
      "qual_type": "信息系统集成及服务",
      "qual_name": "信息系统集成及服务资质",
      "qual_level": "一级",
      "qual_code": "X-2020-001",
      "issue_date": "2020-01-15",
      "expire_date": "2028-01-14",
      "issue_authority": "中国电子信息行业联合会"
    }
  ],
  "performance_history": [
    {
      "project_name": "某省政务大数据平台建设",
      "project_type": "服务",
      "industry": "IT",
      "region": "北京",
      "contract_amount": 2500,
      "award_date": "2024-03-15",
      "buyer": "某省政务服务管理办公室"
    }
  ]
}
```

### 5.3 知识库文档管理

#### 导入单个文件

```bash
python scripts/ingest_cli.py import path/to/document.pdf
python scripts/ingest_cli.py import path/to/guide.md
python scripts/ingest_cli.py import path/to/manual.docx
```

#### 批量导入目录

```bash
python scripts/ingest_cli.py import path/to/docs/
```

支持格式：`.pdf` / `.docx` / `.doc` / `.md` / `.txt` / `.csv` / `.json`

#### 导入纯文本

```bash
python scripts/ingest_cli.py import --text "公司投标流程：1. 获取招标文件 2. 编制投标文件..." --source "投标流程文档"
```

#### 删除文档

```bash
python scripts/ingest_cli.py delete --source "旧文档.pdf"
```

#### 知识库统计

```bash
python scripts/ingest_cli.py stats
```

#### 测试检索

```bash
python scripts/ingest_cli.py search "投标需要哪些材料"
```

### 5.4 系统运维

#### 健康检查

```bash
python scripts/ingest_cli.py health
```

输出示例：
```
Hermes-Lite 知识库健康检查
========================================
✓ OceanBase: 已连接
  parent_chunks: 45 行
  child_chunks: 328 行
✓ Embedding: deepseek/deepseek-embedding
✓ Rerank: bge/BAAI/bge-reranker-v2-m3
```

#### 修改匹配权重（无需改代码）

> ⚠ 权重目前硬编码在 `services/tender_service.py` 的 `DEFAULT_WEIGHTS` 中。
> 如需运行时可调，通过前端 API 覆盖（见第 9 节）。

当前默认权重：

| 维度 | 权重 | 说明 |
|------|------|------|
| `industry` | 0.20 | 行业匹配 |
| `region` | 0.10 | 地域匹配 |
| `qualification` | 0.25 | 资质匹配（硬性门槛） |
| `budget` | 0.10 | 预算匹配 |
| `capability` | 0.20 | 技术能力匹配 |
| `experience` | 0.15 | 历史业绩匹配 |

---

## 6. 用户端操作（Agent 对话）

### 6.1 用户可用的工具

Agent 会根据用户问题自动选择合适的工具，用户无需知道工具名称。

| 用户说什么 | Agent 调用的工具 | 返回内容 |
|-----------|-----------------|---------|
| "最近有什么IT行业的招标？" | `tender_search` | 招标列表 |
| "推荐一些适合我们的项目" | `tender_recommend` | 推荐列表 + 匹配分析 + 建议 |
| "这个项目我们能投吗？" | `tender_match` | 六维度评分 + 中标概率 + 风险 |
| "分析一下这个标竞争大不大" | `tender_analyze` | 竞争度 + 资质门槛 + 策略 |
| "公司的投标流程是怎样的？" | `knowledge_search` | 文档检索结果 |
| "我们的退款政策是什么？" | `knowledge_search` | 文档检索结果 |
| "帮我查一下XX公司的信息" | `tender_search` | 企业搜索（通过招标搜索） |
| "这个月有哪些项目截止？" | `tender_search` | 按截止日期筛选 |

### 6.2 Agent 对话示例

**场景 1：企业负责人查看推荐项目**

```
用户：帮我看一下我们公司（COM-001）最近有哪些匹配的招标项目

Agent 调用：tender_recommend(company_id="COM-001", top_k=5)

Agent 回复：
为某科技股份有限公司推荐 5 个项目：

🟢 强烈推荐 2 个：
  1. 某市政府智慧城市大数据平台建设项目
     综合匹配分：82.5  中标概率：65.3%
     ✅ 行业高度匹配、资质完全满足、有丰富同类经验
     💡 建议积极准备投标文件，技术方案中突出大数据平台能力

  2. 某省数字政府平台升级项目
     综合匹配分：78.2  中标概率：61.8%
     ✅ 行业匹配、能力覆盖
     ⚠ 距投标截止仅 12 天，建议尽快启动

🟡 建议关注 3 个：...
```

**场景 2：评估具体项目**

```
用户：ZB-2026-001 这个智慧城市项目，我们公司（COM-001）能不能投？

Agent 调用：tender_match(company_id="COM-001", tender_id="ZB-2026-001")

Agent 回复：
📊 匹配评估结果：

六维度评分：
  行业匹配:  100.0  ✅ 行业高度匹配
  地域匹配:  100.0  ✅ 同城优势
  资质匹配:   90.0  ✅ 资质基本满足
  预算匹配:   80.0  ✅ 企业规模匹配
  能力匹配:   85.0  ✅ 技术能力覆盖
  业绩匹配:   92.0  ✅ 有丰富同类经验

综合匹配分: 90.3  中标概率: 72.1%  推荐: 🟢 strong

✅ 优势：行业高度匹配、地域优势、有3个同类项目经验
⚠ 风险：无（CMMI证书2026-05-31到期，需确认续期状态）
💡 建议：
  • 建议积极准备投标文件
  • 确认CMMI证书续期状态
  • 重点打磨技术方案，突出大数据平台建设经验
```

**场景 3：搜索招标**

```
用户：北京地区有什么IT行业的招标，预算500万以上的？

Agent 调用：tender_search(industry="IT", region="北京", budget_min=500)

Agent 回复：
找到 8 个符合条件的招标项目：

1. 某市政府智慧城市大数据平台建设项目
   采购方：某市大数据管理局 | 预算：800-1200万
   截止：2026-07-15 | 类型：公开招标

2. ...
```

---

## 7. 可配置项汇总（无需改代码）

### 7.1 通过 .env 配置（重启生效）

| 配置类别 | 变量数 | 修改方式 |
|---------|--------|---------|
| OceanBase 连接 | 7 个 | 编辑 `.env` |
| Embedding 服务 | 7 个 | 编辑 `.env`（切换提供商改 4 个值） |
| Rerank 服务 | 6 个 | 编辑 `.env`（切换提供商改 4 个值，禁用改 1 个值） |
| 检索管道参数 | 5 个 | 编辑 `.env` |
| **合计** | **25 个** | **全部在 .env 中，改完重启** |

### 7.2 通过 CLI 管理（即时生效）

| 操作 | 命令 |
|------|------|
| 导入招标数据 | `tender_cli.py import-tenders` |
| 导入企业数据 | `tender_cli.py import-companies` |
| 添加单条招标 | `tender_cli.py add-tender` |
| 添加单家企业 | `tender_cli.py add-company` |
| 导入文档到知识库 | `ingest_cli.py import` |
| 删除文档 | `ingest_cli.py delete` |
| 查看统计 | `tender_cli.py stats` / `ingest_cli.py stats` |
| 健康检查 | `ingest_cli.py health` |
| 测试推荐/匹配/搜索 | `tender_cli.py recommend/match/search` |
| 测试检索 | `ingest_cli.py search` |

### 7.3 通过数据库直接操作（即时生效）

| 操作 | SQL |
|------|-----|
| 修改招标状态 | `UPDATE tenders SET status='closed' WHERE tender_id='...'` |
| 更新企业信息 | `UPDATE companies SET revenue=30000 WHERE company_id='...'` |
| 删除过期资质 | `DELETE FROM company_qualifications WHERE expire_date < CURDATE()` |
| 清理匹配缓存 | `DELETE FROM tender_matches WHERE expires_at < NOW()` |
| 标记中标结果 | `UPDATE tenders SET status='awarded', winner='...', win_amount=...` |

---

## 8. 需要改代码的场景及方案

> 以下场景当前需要改代码，但可通过前端 API 化来消除。

| 场景 | 当前方案 | 前端化方案 |
|------|---------|-----------|
| 修改匹配权重 | 改 `tender_service.py` 的 `DEFAULT_WEIGHTS` | 前端管理面板提供权重滑块 → 存 DB → 运行时读取 |
| 新增行业分类 | 改数据中的 `industry` 字段 | 前端下拉选项管理 → 存配置表 |
| 修改推荐阈值 | 改 CLI 的 `--min-score` 参数 | 前端设置面板 → 存 `.env` 或 DB |
| 修改分块参数 | 改 CLI 的 `--parent-chars` / `--child-chars` | 前端设置面板 → 存 `.env` |
| 新增 Agent 工具 | 在 `tools/` 新增 `.py` 文件 + `registry.register()` | 插件系统（已有 MCP 支持基础） |
| 修改 Agent 系统提示 | 改 `agent/system_prompt.py` 或 skill 文件 | 前端提示词管理面板 |
| 工具集开关 | 改 `toolsets.py` | 前端工具管理面板 |

---

## 9. 前端接入指南

### 9.1 管理员后台需要的 API

以下是前端管理员后台需要实现的 API 端点，覆盖所有管理操作：

#### 9.1.1 数据管理 API

```yaml
# ── 招标管理 ──────────────────────────────────
POST   /api/admin/tenders/import          # 批量导入（JSON body）
POST   /api/admin/tenders                  # 添加单条
GET    /api/admin/tenders                  # 列表（分页 + 筛选）
GET    /api/admin/tenders/{id}             # 详情
PUT    /api/admin/tenders/{id}             # 更新
DELETE /api/admin/tenders/{id}             # 删除
PATCH  /api/admin/tenders/{id}/status      # 修改状态

# ── 企业管理 ──────────────────────────────────
POST   /api/admin/companies/import         # 批量导入
POST   /api/admin/companies                # 添加单条
GET    /api/admin/companies                # 列表
GET    /api/admin/companies/{id}           # 详情（含资质+业绩）
PUT    /api/admin/companies/{id}           # 更新
DELETE /api/admin/companies/{id}           # 删除

# ── 企业资质 ──────────────────────────────────
POST   /api/admin/companies/{id}/qualifications
PUT    /api/admin/qualifications/{id}
DELETE /api/admin/qualifications/{id}

# ── 企业业绩 ──────────────────────────────────
POST   /api/admin/companies/{id}/performance
PUT    /api/admin/performance/{id}
DELETE /api/admin/performance/{id}

# ── 知识库文档 ────────────────────────────────
POST   /api/admin/documents/upload          # 文件上传
POST   /api/admin/documents/text            # 纯文本导入
GET    /api/admin/documents                 # 文档列表
DELETE /api/admin/documents/{source}        # 删除文档
POST   /api/admin/documents/search          # 测试检索

# ── 系统管理 ──────────────────────────────────
GET    /api/admin/stats                     # 总统计
GET    /api/admin/health                    # 健康检查
GET    /api/admin/config                    # 获取当前配置
PUT    /api/admin/config                    # 更新配置（.env 热更新）
```

#### 9.1.2 前端页面建议

**管理员后台页面：**

```
管理员后台
├── 📊 仪表盘（统计概览）
│   ├── 招标总数 / 活跃数 / 本月新增
│   ├── 企业总数 / 行业分布饼图
│   └── 知识库文档数 / 子块数
│
├── 📋 招标管理
│   ├── 招标列表（表格 + 筛选：行业/地区/状态/预算/截止日）
│   ├── 新增/编辑招标（表单）
│   ├── 批量导入（JSON 上传）
│   └── 招标详情（含匹配企业列表）
│
├── 🏢 企业管理
│   ├── 企业列表
│   ├── 新增/编辑企业
│   ├── 企业详情（基本信息 + 资质 + 业绩 + 匹配招标）
│   └── 批量导入
│
├── 📚 知识库管理
│   ├── 文档列表（已导入的文档）
│   ├── 上传文档（拖拽上传 + 进度条）
│   ├── 纯文本导入
│   └── 检索测试（输入查询 → 返回结果）
│
├── ⚙️ 系统配置
│   ├── AI 服务配置（Embedding / Rerank 提供商切换）
│   ├── 检索参数（Top-K / RRF-K / 最终返回数）
│   ├── 匹配权重（六维度滑块）
│   └── 工具开关（哪些工具暴露给 Agent）
│
└── 🔧 运维
    ├── 健康检查
    ├── 操作日志
    └── 数据备份
```

### 9.2 用户端对话界面

用户端只需一个对话界面，通过 HTTP API 调用 Agent：

```yaml
POST /api/chat
Body:
  {
    "message": "推荐一些适合我们的招标项目",
    "session_id": "user-123-session-456",
    "context": {
      "company_id": "COM-001"    # 可选：前端注入当前企业上下文
    }
  }

Response:
  {
    "reply": "为某科技股份有限公司推荐 5 个项目...",
    "tool_calls": [
      {
        "tool": "tender_recommend",
        "args": {"company_id": "COM-001", "top_k": 5},
        "result": {...}
      }
    ]
  }
```

### 9.3 前端注入上下文（避免用户重复输入）

前端可在对话开始时注入企业上下文，Agent 自动使用：

```
前端注入（作为 system message 或 context 参数）：
"当前用户所属企业：company_id=COM-001，企业名称=某科技股份有限公司，
 主营行业=IT，所在地区=北京。用户提问中的'我们公司'指代此企业。"
```

这样用户说"推荐一些项目"时，Agent 自动知道是 COM-001。

---

## 10. Agent 工具 API 参考

### 10.1 knowledge_search

```json
{
  "name": "knowledge_search",
  "parameters": {
    "query": "string (required) - 检索查询",
    "top_k": "integer (1-10, default 3) - 返回父块数"
  }
}
```

**返回格式：**
```json
{
  "results": [
    {
      "parent_id": "doc_abc_p0001",
      "content": "完整文档文本...",
      "source": "投标流程手册.pdf",
      "score": 0.8523,
      "matched_children": 2
    }
  ],
  "total": 3
}
```

### 10.2 tender_search

```json
{
  "name": "tender_search",
  "parameters": {
    "keyword": "string - 关键词全文检索",
    "industry": "string - 行业筛选",
    "region": "string - 地区筛选",
    "budget_min": "number - 预算下限（万元）",
    "budget_max": "number - 预算上限（万元）",
    "tender_type": "string - 招标类型",
    "deadline_before": "string - 截止日期前（YYYY-MM-DD）",
    "status": "string - active/closed/awarded/cancelled",
    "limit": "integer (default 20)"
  }
}
```

### 10.3 tender_recommend

```json
{
  "name": "tender_recommend",
  "parameters": {
    "company_id": "string (required) - 企业ID",
    "top_k": "integer (default 5) - 推荐数",
    "min_score": "number (default 40) - 最低匹配分",
    "industry": "string - 限定行业",
    "region": "string - 限定地区"
  }
}
```

**返回格式：**
```json
{
  "company": "某科技股份有限公司",
  "summary": "推荐 5 个项目...",
  "results": [
    {
      "tender_id": "ZB-2026-001",
      "title": "智慧城市大数据平台建设",
      "total_score": 82.5,
      "win_probability": 65.3,
      "recommendation": "strong",
      "scores": {
        "industry": 100, "region": 100, "qualification": 90,
        "budget": 80, "capability": 85, "experience": 92
      },
      "match_reasons": ["行业高度匹配", "资质完全满足"],
      "risk_factors": [],
      "suggestions": ["建议积极准备投标文件", "..."]
    }
  ]
}
```

### 10.4 tender_match

```json
{
  "name": "tender_match",
  "parameters": {
    "company_id": "string (required)",
    "tender_id": "string (required)"
  }
}
```

### 10.5 tender_analyze

```json
{
  "name": "tender_analyze",
  "parameters": {
    "tender_id": "string (required)"
  }
}
```

**返回格式：**
```json
{
  "tender": { ... },
  "similar_tenders": [ ... ],
  "matched_companies": [ ... ],
  "qualification_barriers": {
    "required_qualifications": ["...", "..."],
    "barrier_level": "high",
    "description": "需要 3 项资质"
  },
  "competition_assessment": {
    "matched_companies": 12,
    "competition_level": "激烈",
    "top_competitors": [{"name": "...", "score": 85}]
  },
  "suggestions": ["🔥 竞争激烈...", "📋 资质门槛较高...", "..."]
}
```

---

## 11. 数据导入格式规范

### 11.1 招标数据 JSON 格式

```json
[
  {
    "tender_id": "ZB-2026-001",         // 必填，唯一ID
    "project_code": "XXZB-2026-001",    // 项目编号
    "title": "项目名称",                 // 必填
    "buyer": "采购方名称",
    "agency": "代理机构",
    "industry": "IT",                   // 行业分类
    "region": "北京",                   // 地区
    "tender_type": "公开招标",           // 公开招标/邀请招标/竞争性谈判/询价/单一来源
    "project_type": "服务",             // 货物/工程/服务
    "budget_min": 800,                  // 预算下限（万元）
    "budget_max": 1200,                 // 预算上限（万元）
    "publish_date": "2026-06-01",       // 发布日期
    "deadline": "2026-07-15",           // 投标截止日
    "open_date": "2026-07-16",          // 开标日期
    "requirements": {                   // 技术要求（结构化 JSON）
      "platform": "大数据平台",
      "tech_stack": ["Hadoop", "Spark"],
      "delivery": "12个月"
    },
    "eval_criteria": {                  // 评分标准
      "tech_score": 40,
      "price_score": 30
    },
    "qualifications": ["资质1", "资质2"], // 资质要求列表
    "content": "招标公告全文...",        // 完整原文（用于语义检索）
    "status": "active",                 // active/closed/awarded/cancelled
    "source_url": "https://..."         // 来源链接
  }
]
```

### 11.2 企业数据 JSON 格式

```json
[
  {
    "company_id": "COM-001",            // 必填，唯一ID
    "name": "公司全称",                  // 必填
    "unified_code": "911100...",        // 统一社会信用代码
    "legal_person": "张三",
    "industry": "IT",                   // 主营行业
    "region": "北京",                   // 注册地区
    "registered_capital": 5000,         // 注册资本（万元）
    "employee_count": 500,
    "revenue": 20000,                   // 年营收（万元）
    "established_year": 2010,
    "capabilities": ["大数据", "AI"],   // 技术能力标签
    "qualification_level": "一级",       // 最高资质等级
    "certifications": ["ISO9001"],      // 认证列表
    "total_bids": 120,                  // 累计投标数
    "total_wins": 45,                   // 累计中标数
    "win_rate": 37.5,                   // 中标率（%）
    "total_win_amount": 35000,          // 累计中标金额（万元）
    "qualifications_detail": [          // 资质明细（自动写入子表）
      {
        "qual_type": "资质类型",
        "qual_name": "资质名称",
        "qual_level": "一级",
        "qual_code": "证书编号",
        "issue_date": "2020-01-15",
        "expire_date": "2028-01-14",
        "issue_authority": "发证机关"
      }
    ],
    "performance_history": [            // 历史业绩（自动写入子表）
      {
        "project_name": "项目名称",
        "project_type": "服务",
        "industry": "IT",
        "region": "北京",
        "contract_amount": 2500,        // 合同金额（万元）
        "award_date": "2024-03-15",
        "buyer": "采购方"
      }
    ]
  }
]
```

### 11.3 知识库文档支持格式

| 格式 | 后缀 | 解析方式 | 依赖 |
|------|------|---------|------|
| PDF | `.pdf` | pymupdf（优先）/ marker-pdf | `pip install pymupdf` |
| Word | `.docx` / `.doc` | python-docx | `pip install python-docx` |
| Markdown | `.md` / `.markdown` | 按标题（#）分段 | 无 |
| 纯文本 | `.txt` / `.text` | 按段落分段 | 无 |
| CSV | `.csv` | 当纯文本 | 无 |
| JSON | `.json` / `.jsonl` | 当纯文本 | 无 |

---

## 12. 故障排查

### 12.1 常见问题

| 问题 | 排查步骤 |
|------|---------|
| 工具不可用（Agent 看不到 knowledge_search） | ① 检查 `.env` 中 `OCEANBASE_DATABASE` 和 `EMBEDDING_API_KEY` 是否配置 ② 运行 `ingest_cli.py health` |
| 检索无结果 | ① 确认数据已导入（`ingest_cli.py stats`） ② 测试检索（`ingest_cli.py search "关键词"`） ③ 检查 FULLTEXT 索引（ngram 解析器是否生效） |
| Embedding 失败 | ① 检查 `EMBEDDING_API_KEY` ② 检查 `EMBEDDING_BASE_URL` 可达 ③ 检查模型名是否正确 |
| Rerank 被跳过 | ① 检查 `RERANK_ENABLED=true` ② 检查 `RERANK_BASE_URL` 可达 ③ 检查 `RERANK_API_KEY`（如需要） |
| OceanBase 连接失败 | ① 确认 OB 服务运行中 ② 检查端口 2881 可达 ③ 检查用户名密码 ④ 确认数据库 `hermes_lite` 存在 |
| 向量索引创建失败 | 确认 OceanBase 版本 ≥ V4.4.1，且支持 VECTOR 类型 |
| 匹配评分异常 | ① 检查企业资质是否录入（`company_qualifications` 表） ② 检查企业业绩是否录入（`company_performance` 表） ③ 运行 `tender_cli.py match` 查看分维度评分 |

### 12.2 日志查看

```bash
# Agent 日志（如有）
tail -f ~/.hermes/agent.log

# 直接看 Python 输出（CLI 工具自带 INFO 日志）
python scripts/tender_cli.py stats 2>&1 | head -50
```

### 12.3 数据库直接查询

```bash
# 连接数据库
mysql -h 127.0.0.1 -P 2881 -u root -p hermes_lite

# 查看表数据量
SELECT 'tenders' AS tbl, COUNT(*) FROM tenders
UNION ALL SELECT 'companies', COUNT(*) FROM companies
UNION ALL SELECT 'parent_chunks', COUNT(*) FROM parent_chunks
UNION ALL SELECT 'child_chunks', COUNT(*) FROM child_chunks;

# 查看活跃招标
SELECT tender_id, title, industry, region, budget_max, deadline
FROM tenders WHERE status='active' ORDER BY deadline LIMIT 10;

# 查看企业资质
SELECT c.name, q.qual_name, q.qual_level, q.expire_date
FROM company_qualifications q
JOIN companies c ON q.company_id = c.company_id
WHERE q.expire_date > CURDATE();
```

---

## 附录 A：项目文件清单

```
services/__init__.py              ← 服务层入口（10行）
services/config.py                ← 配置管理（118行）
services/embedding_service.py     ← Embedding 服务（137行）
services/rerank_service.py        ← Rerank 服务（167行）
services/chunk_store.py           ← OceanBase 混合检索（380行）
services/retrieval_pipeline.py    ← 检索管道（189行）
services/document_ingestion.py    ← 文档导入（390行）
services/tender_service.py        ← 招标匹配引擎（1134行）

tools/knowledge_tool.py           ← knowledge_search 工具（120行）
tools/tender_tools.py             ← 4 个招标工具（300行）

toolsets.py                       ← 工具集定义（420行）

scripts/init_knowledge_db.sql     ← 知识库建表
scripts/init_tender_db.sql        ← 招标系统建表
scripts/ingest_cli.py             ← 知识库管理 CLI（260行）
scripts/tender_cli.py             ← 招标管理 CLI（270行）

data/examples/tenders_example.json    ← 招标样例数据
data/examples/companies_example.json  ← 企业样例数据
```

## 附录 B：六维度匹配算法详解

```
综合分 = Σ(维度分 × 权重)

维度分计算规则：
┌──────────────┬────────┬──────────────────────────────────────┐
│ 维度         │ 权重   │ 评分逻辑                              │
├──────────────┼────────┼──────────────────────────────────────┤
│ 行业匹配     │ 20%    │ 完全匹配=100，能力覆盖=80，不匹配=20  │
│ 地域匹配     │ 10%    │ 同城=100，同省=75，异地=30            │
│ 资质匹配     │ 25%    │ 全部满足=100，部分按比例，不满足≤10   │
│ 预算匹配     │ 10%    │ 营收/预算 5~30倍=100，其他按区间      │
│ 能力匹配     │ 20%    │ 需求关键词命中率 + 30 基础分           │
│ 业绩匹配     │ 15%    │ 同行业业绩数量 + 金额匹配 + 中标率     │
└──────────────┴────────┴──────────────────────────────────────┘

推荐等级：
  strong ≥ 75（且资质 ≥ 70）
  medium ≥ 55
  weak   ≥ 35
  skip   < 35

中标概率 = 综合分 × 0.6 + 中标率加成(max 15) - 资质惩罚(20)
```
