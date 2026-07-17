# Hermes-Lite

> Hermes-Lite 是基于 Hermes Agent v0.16.0 裁剪和适配后的轻量中枢 Agent。  
> 在 Dazah / Livzon Agent 场景中，它负责理解用户意图、编排工具调用、连接平台 LLM 代理，并将业务结果组织成适合前端聊天窗口展示的回复。

## 1. Hermes 的作用

Hermes-Lite 在当前平台中的定位不是业务系统本身，也不是直接访问数据库的数据服务，而是位于 Dazah 后端 Agent 网关之后的“智能编排层”。

它主要承担以下职责：

- 接收 Dazah 后端转发的用户消息、会话历史和用户上下文。
- 通过 Dazah 后端提供的 LLM 代理调用平台当前启用的大模型配置。
- 根据用户意图选择合适的工具，例如库存查询、采购申请、审批查询等。
- 通过 `dazah_tool` 调用 Dazah 后端受控的业务工具网关。
- 对读操作结果进行业务化总结和卡片式表达。
- 对写操作生成待确认项，由前端展示二次确认，用户确认后再由 Dazah 后端执行。
- 保持 Hermes 自身的工具边界，不直接绕过后端权限、审计和业务校验。

当前调用链路如下：

```text
Livzon Agent 前端悬浮助手
        |
        v
Dazah 后端 /api/v1/agent/chat 或 /api/v1/agent/chat/stream
        |
        v
Hermes-Lite /v1/chat 或 /v1/chat/stream
        |
        +-- LLM：Dazah 后端 /api/v1/agent/llm/chat/completions
        |
        +-- 工具：dazah_tool
              |
              v
           Dazah 后端 /api/v1/agent/tools/execute
              |
              v
           仓储 / 采购 / 审批 / 飞书同步等业务模块
```

## 2. 与 Dazah 平台的适配方式

### 2.1 LLM 配置读取

Hermes-Lite 不直接保存真实模型 API Key，也不直接读取数据库中的 LLM 配置。

当前设计是：

- 平台管理员在 Dazah 中维护“LLM 系统配置”。
- Dazah 后端从平台配置表中读取当前启用的模型供应商、模型名称、Base URL、API Key 等信息。
- Hermes-Lite 只访问 Dazah 后端暴露的 LLM 代理接口。
- Hermes-Lite 与 Dazah 后端之间通过 `AGENT_LLM_PROXY_TOKEN` 做服务间鉴权。

这可以保证：

- 模型密钥集中保存在 Dazah 平台侧。
- Hermes 不需要感知具体供应商密钥。
- 切换模型配置时优先由平台配置生效，不需要频繁修改 Hermes。
- 后端可以统一做模型访问审计、错误处理和配置校验。

相关环境变量：

```bash
AGENT_LLM_PROXY_TOKEN=change-me
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
DAZAH_LLM_MODEL=dazah-active-text
```

容器内运行时不要使用 `127.0.0.1` 指向 Dazah 后端。`127.0.0.1` 在容器内代表 Hermes 容器自身，应使用 Docker 网络中的服务名，例如：

```bash
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
```

### 2.2 平台工具调用

Hermes-Lite 通过 `tools/dazah_platform.py` 中的 `dazah_tool` 调用 Dazah 平台业务能力。

`dazah_tool` 不允许模型调用任意 URL，只允许向 Dazah 后端 Agent 工具网关发送受控 operation。Dazah 后端现在以 `@agent_tool` 装饰器、`ToolRegistry` 注册中心和 `ToolExecutor` 统一执行器作为权威工具来源；Hermes 侧只负责发起工具调用，不直接操作数据库，也不绕过后端权限、参数校验、确认和审计。

```text
POST {DAZAH_API_BASE_URL}/agent/tools/execute
```

Dazah 后端同时提供服务令牌保护的工具发现接口：

```text
GET {DAZAH_API_BASE_URL}/agent/tools
```

该接口返回后端当前已注册、授权、开放给 Agent 的工具元数据，包括：

- `name`：工具名称，例如 `procurement.list_suppliers`
- `summary`：工具说明
- `input_schema`：Pydantic 输入参数 schema
- `risk_level`：风险等级，`low` / `medium` / `high`
- `write`：是否写操作
- `required_roles`：所需用户角色
- `workflow_allowed`：是否允许进入 Agent 工作流
- `human_decision_required`：是否必须人工责任判断
- `method` / `path`：兼容旧能力说明的 HTTP 元数据

相关环境变量：

```bash
DAZAH_API_BASE_URL=http://app:8000/api/v1
DAZAH_AGENT_TOOL_TOKEN=change-me
```

所有业务权限、参数校验、写操作确认、审计记录、数据库事务和飞书凭证都保留在 Dazah 后端，Hermes 只负责发起受控工具调用。

后端工具调用的执行边界为：

```text
Hermes-Lite dazah_tool
  -> Dazah /api/v1/agent/tools/execute
  -> ToolRegistry 查找 @agent_tool 注册工具
  -> ToolExecutor 校验服务令牌、用户、权限、参数、风险
  -> 写操作生成 confirmation / 读操作直接执行
  -> 调用业务模块 Service
  -> 写入 agent_tool_calls 与 audit.logs
```

### 2.3 聊天接口

Hermes-Lite 为 Dazah Agent 网关提供两个接口：

| 接口 | 说明 |
| --- | --- |
| `GET /health` | 健康检查 |
| `POST /v1/chat` | 普通非流式对话 |
| `POST /v1/chat/stream` | SSE 流式对话 |

`/v1/chat/stream` 用于 Livzon Agent 前端逐字输出回复内容。Dazah 前端可通过后端代理接口消费 SSE，用户点击“停止”时由前端中断当前流式请求。

## 3. 兼容性说明

Hermes-Lite 保留 Hermes Agent 的核心运行能力，但对默认功能面做了收敛，以便更安全地嵌入业务系统。

### 3.1 保留能力

- Tool-calling 对话循环。
- OpenAI-compatible Chat Completions 调用方式。
- Prompt 组装和会话历史注入。
- Memory、session search、todo、clarify 等轻量 Agent 工具。
- Web search 与 web extract。
- Tool registry 和 toolset 机制。
- Dazah 平台工具集 `dazah`。
- 普通响应和 SSE 流式响应。

### 3.2 默认不启用的能力

以下能力虽然在工程中可能存在兼容代码或历史模块，但当前 Dazah Agent 服务默认不启用：

- 终端命令执行。
- 本地文件读写。
- 浏览器自动化。
- 代码执行。
- 多媒体生成。
- 未经 Dazah 后端网关授权的数据库直连。
- 任意第三方 URL 工具调用。

这样做的目的是降低业务系统内嵌 Agent 的执行风险。需要新增高权限能力时，应先在 Dazah 后端建立受控 Service、权限校验、审计和确认机制，再通过 `@agent_tool` 注册为受控工具，最后同步 Hermes 工具 schema。

### 3.3 模型接口兼容

Hermes-Lite 当前主要使用 OpenAI-compatible Chat Completions 接口。实际模型供应商由 Dazah 平台 LLM 系统配置决定。

适配时需要关注：

- `/models` 接口是否可用。
- `/chat/completions` 是否支持流式输出。
- usage 字段可能存在 `prompt_tokens` / `completion_tokens` 或其他供应商差异。
- 工具调用格式是否符合 OpenAI tool calling 语义。
- 模型是否稳定支持中文业务指令和结构化 JSON 参数生成。

## 4. 当前启用的工具集

Hermes-Lite 的工具集定义位于 `toolsets.py`。

当前 Dazah Agent 服务在 `services/dazah_agent_service.py` 中启用：

```python
enabled_toolsets=["agent", "dazah"]
```

主要工具如下：

| 工具集 | 工具 | 用途 |
| --- | --- | --- |
| `agent` | `memory` | 保存稳定的用户或项目偏好 |
| `agent` | `session_search` | 检索历史会话 |
| `agent` | `todo` | 任务拆解与步骤管理 |
| `agent` | `clarify` | 在意图不明确时提出澄清问题 |
| `agent` | `web_search` | 搜索公开网页 |
| `agent` | `web_extract` | 提取网页内容 |
| `dazah` | `dazah_tool` | 调用 Dazah 平台仓储、采购、质量管理和通讯录等业务工具 |

## 5. 当前 Dazah 后端注册工具

以下工具由 Dazah 后端通过 `@agent_tool` 注册并由 `ToolRegistry` 统一管理。Hermes-Lite 的 `dazah_tool` 调用这些 operation 时，后端会再次校验工具是否注册、用户是否有权限、参数是否符合 InputSchema，以及该操作是否需要确认或必须人工判断。

Hermes-Lite 中 `tools/dazah_platform.py` 的 `ALLOWED_OPERATIONS` 仍保留为本地防御层和模型 tool schema 枚举，实际授权以 Dazah 后端 `GET /api/v1/agent/tools` 与 `POST /api/v1/agent/tools/execute` 为准。新增工具后，应同步后端注册表与 Hermes 本地 schema，避免模型选择未暴露的 operation。

### 5.1 仓储模块

| 操作 | 说明 |
| --- | --- |
| `identity.get_department_tree` | 查询 Livzon 助手已同步的飞书部门树 |
| `identity.search_personnel` | 查询 Livzon 助手已同步的飞书人员、手机号、邮箱和部门关系 |
| `identity.check_feishu_permissions` | 诊断 Livzon 助手飞书通讯录权限（管理员） |
| `identity.send_feishu_message` | 按 Livzon 规则发送文本、卡片或交互卡片，执行前必须确认收件人、消息形态和内容摘要 |
| `identity.send_feishu_text_message` | 兼容旧文本消息工具，优先使用统一发送工具 |
| `identity.send_feishu_card_message` | 兼容旧卡片消息工具，优先使用统一发送工具 |
| `warehouse.list_raw_materials` | 查询原辅料库存 |
| `warehouse.list_packaging_materials` | 查询包材库存 |
| `warehouse.list_products` | 查询成品库存 |
| `warehouse.list_feishu_tables` | 查询飞书表配置 |
| `warehouse.get_feishu_table_records` | 查询指定飞书表记录 |
| `warehouse.get_feishu_domain_records` | 查询指定业务域飞书数据 |
| `warehouse.get_feishu_ws_status` | 查询飞书同步状态 |
| `warehouse.refresh_feishu_tables` | 刷新飞书表配置 |
| `warehouse.set_feishu_tables_enabled` | 批量启停飞书表同步 |
| `warehouse.set_feishu_table_enabled` | 启停单个飞书表同步 |
| `warehouse.sync_feishu_table` | 同步指定飞书表 |
| `warehouse.restart_feishu_ws` | 重启飞书 WebSocket 同步 |

### 5.2 采购模块

| 操作 | 说明 |
| --- | --- |
| `procurement.list_invoice_records` | 查询发票识别记录 |
| `procurement.list_suppliers` | 查询供应商清单 |
| `procurement.list_purchase_requests` | 查询采购申请列表 |
| `procurement.get_purchase_request` | 查询采购申请详情 |
| `procurement.create_purchase_request` | 创建采购申请 |
| `procurement.update_purchase_request` | 更新采购申请 |
| `procurement.submit_purchase_request` | 提交采购申请 |
| `procurement.approve_purchase_request` | 审批通过采购申请 |
| `procurement.reject_purchase_request` | 驳回采购申请 |
| `procurement.list_purchase_orders` | 查询采购订单 |
| `procurement.export_purchase_orders` | 导出采购订单 |
| `procurement.list_contract_templates` | 获取四类合同模板、字段清单、必填项和模板文件信息 |
| `procurement.get_contract_template` | 获取指定合同模板、字段清单、必填项和模板文件信息 |
| `procurement.generate_contract` | 生成采购合同 |

读操作可直接返回结果。写操作应由 Dazah 后端生成 pending confirmation，前端展示二次确认，用户确认后再执行。

合同生成建议流程：

1. 用户询问“有哪些合同模板/某类合同需要填什么字段”时，优先调用 `procurement.list_contract_templates` 或 `procurement.get_contract_template`。
2. 用户要求生成合同时，先根据模板字段收集 `category`、`contract_number`、`contract_date`、`seller.*` 和至少一条 `items` 明细；`items` 每条至少需要 `name`、`quantity`、`unit_price`。
3. 用户明确说“示例/样例/模板演示”时，可以调用 `procurement.generate_contract` 生成示例合同；Dazah 后端会按合同分类匹配对应 Word 模板。

### 5.3 质量模块

质量模块工具覆盖偏差、CAPA、变更、验证、CPV 和质量飞书只读/同步能力。查询类工具直接执行；创建、更新、提交、同步、回拉和提醒类工具由 Dazah 后端生成 pending confirmation，用户确认后才执行。

质量模块明确不向 Hermes-Lite 暴露删除、批量删除、审批通过、驳回、部门主管确认、QA 批准、执行完成确认、效果评价确认、飞书配置管理、字段映射管理和文件导入上传接口。

| 操作 | 说明 |
| --- | --- |
| `quality.list_deviations` | 查询偏差列表 |
| `quality.get_deviation` | 查询偏差详情 |
| `quality.list_deviation_report_records` | 查询偏差报告记录 |
| `quality.get_related_capas` | 查询偏差关联CAPA |
| `quality.get_deviation_statistics` | 查询偏差统计 |
| `quality.create_deviation` | 创建偏差 |
| `quality.update_deviation` | 更新偏差 |
| `quality.submit_deviation` | 提交偏差启动流程 |
| `quality.submit_deviation_investigation` | 提交偏差调查报告 |
| `quality.resubmit_deviation` | 重新提交偏差 |
| `quality.list_capas` | 查询CAPA列表 |
| `quality.get_capa` | 查询CAPA详情 |
| `quality.list_capa_departments` | 查询CAPA部门 |
| `quality.auto_fill_capa_from_deviation` | 从偏差生成CAPA表单建议 |
| `quality.get_capa_statistics` | 查询CAPA统计 |
| `quality.create_capa` | 创建CAPA |
| `quality.update_capa` | 更新CAPA |
| `quality.submit_capa` | 提交CAPA |
| `quality.resubmit_capa` | 重新提交CAPA |
| `quality.link_capa_deviation` | 关联偏差到CAPA |
| `quality.complete_capa_part` | 完成CAPA部分内容 |
| `quality.add_capa_execution_track` | 添加CAPA执行记录 |
| `quality.list_changes` | 查询变更列表 |
| `quality.get_change` | 查询变更详情 |
| `quality.get_next_change_code` | 获取下一个变更控制号 |
| `quality.get_change_statistics` | 查询变更统计 |
| `quality.create_change` | 创建变更 |
| `quality.update_change` | 更新变更 |
| `quality.list_change_action_plans` | 查询变更计划列表 |
| `quality.list_change_action_plans_by_change` | 查询指定变更下的变更计划 |
| `quality.create_change_action_plan` | 创建变更计划 |
| `quality.update_change_action_plan` | 更新变更计划 |
| `quality.sync_change_action_plan` | 同步变更计划到飞书 |
| `quality.sync_change_action_plans_from_feishu` | 从飞书同步变更计划 |
| `quality.run_change_action_plan_reminders` | 执行变更计划提醒 |
| `quality.send_change_action_plan_reminder` | 发送单条变更计划提醒 |
| `quality.list_validations` | 查询验证列表 |
| `quality.get_validation` | 查询验证详情 |
| `quality.get_validation_statistics` | 查询验证统计 |
| `quality.list_validation_executions` | 查询验证执行列表 |
| `quality.create_validation` | 创建验证记录 |
| `quality.update_validation` | 更新验证记录 |
| `quality.update_validation_execution` | 更新验证执行记录 |
| `quality.list_cpv_products` | 查询CPV产品 |
| `quality.get_cpv_product` | 查询CPV产品详情 |
| `quality.create_cpv_product` | 创建CPV产品 |
| `quality.update_cpv_product` | 更新CPV产品 |
| `quality.list_cpv_parameters` | 查询CPV参数 |
| `quality.create_cpv_parameter` | 创建CPV参数 |
| `quality.update_cpv_parameter` | 更新CPV参数 |
| `quality.list_cpv_batches` | 查询CPV批次 |
| `quality.list_cpv_cpp_batches` | 查询CPP宽表批次 |
| `quality.list_cpv_cqa_batches` | 查询CQA宽表批次 |
| `quality.get_cpv_statistics` | 查询CPV统计数据 |
| `quality.get_cpv_trend` | 查询CPV趋势数据 |
| `quality.list_quality_sync_conflicts` | 查询质量飞书同步冲突 |
| `quality.pull_quality_records_from_feishu` | 从飞书回拉质量数据 |
| `quality.sync_deviation_to_feishu` | 同步偏差到飞书 |
| `quality.sync_deviation_report_record_to_feishu` | 同步偏差报告记录到飞书 |
| `quality.sync_capa_to_feishu` | 同步CAPA到飞书 |
| `quality.sync_capa_plan_track_to_feishu` | 同步CAPA计划跟踪到飞书 |
| `quality.list_feishu_capa_ledger` | 查询飞书CAPA台账 |
| `quality.get_feishu_capa_ledger` | 查询飞书CAPA台账详情 |
| `quality.list_feishu_capa_plan_tracks` | 查询飞书CAPA计划跟踪 |
| `quality.get_feishu_capa_plan_track` | 查询飞书CAPA计划跟踪详情 |
| `quality.list_feishu_validations` | 查询飞书验证记录 |
| `quality.get_feishu_validation` | 查询飞书验证记录详情 |
| `quality.pull_feishu_validations` | 从飞书回拉验证记录 |

### 5.4 Livzon Task 工具

| 操作 | 说明 |
| --- | --- |
| `agent.get_current_time` | 获取当前北京时间、UTC 时间和 cron 时区 |
| `agent.get_my_access_scope` | 查询当前用户的 Livzon 有效模块、可调用工具和可编排工具 |
| `agent.create_automation` | 直接创建不含时间触发的自动化流程，由后端生成定义并返回待确认项 |
| `agent.create_scheduled_task` | 直接创建含 Cron 时间触发的定时任务，由后端生成定义并返回待确认项 |
| `agent.list_automations` | 查询本人、共享或管理员脱敏平台范围的自动化 |
| `agent.get_automation` | 查看自动化摘要和触发器 |
| `agent.list_automation_audit` | 查看自动化版本、修改摘要和变更字段 |
| `agent.update_automation` | 更新自动化定义，返回待确认项 |
| `agent.set_automation_enabled` | 启用或暂停自动化，返回待确认项 |
| `agent.archive_automation` | 归档自动化，返回待确认项 |
| `agent.simulate_automation` | 预览 cron、时区、并发策略与未来执行时间，不执行业务动作 |
| `agent.list_scheduled_triggers` | 查询已配置的计划触发器 |
| `agent.list_automation_runs` | 查询自动化运行记录 |
| `agent.get_automation_run` | 查看运行、步骤和结构化时间线 |
| `agent.list_push_deliveries` | 查询当前用户的自动化飞书投递状态 |
| `agent.get_push_delivery` | 查看当前用户的一条飞书投递详情 |
| `agent.list_domain_events` | 按 correlation ID 追踪跨模块事件链路 |
| `agent.list_automation_capability_impacts` | 扫描受弃用或不兼容能力影响的自动化 |
| `agent.complete_manual_task` | 完成人工待办并恢复等待中的自动化运行 |

Livzon Task 规则由 Dazah 后端 `ToolRegistry` 和 `ToolExecutor` 控制：

- 对话层只保留“自动化流程”和“定时任务”两类，不再暴露旧工作流操作。
- 不含时间语义时调用 `agent.create_automation`；出现日期、星期、时刻、间隔或重复语义时调用 `agent.create_scheduled_task`。
- 创建定时任务时，`requirement` 必须保留用户完整原始需求；需要通过飞书发送查询数据、汇总、统计、清单、报表或记录时，`actions` 必须先执行对应查询，再执行 `identity.send_feishu_message`。
- 后端会在每次定时运行时把前序查询结果合并到飞书正文；仅发送固定寒暄或“请查收”的数据任务会被拒绝创建。
- 后端负责生成、编译和校验节点定义，LLM 不拼装底层 `notify`、`condition` 或触发器结构。
- 审批、驳回、批准、重启等人工责任判断操作不得被加入自动化。
- 用户模块授权只能由平台管理员在权限管理界面配置。Hermes 只能通过 `agent.get_my_access_scope` 读取并解释当前有效范围，不得代用户修改权限。
- 创建、修改、启停和归档均由后端确认链路控制。管理员平台查询仅获取脱敏载荷，不能借治理身份读取业务明细。

## 6. 如何与新的业务模块适配

新增一个业务模块时，建议按以下顺序适配。

### 6.1 在 Dazah 后端建立业务 Service

先在 Dazah 后端业务模块中提供明确的 Service 方法，不建议让 Hermes 直接访问数据库，也不建议让工具 handler 直接操作 ORM model。

后端需要负责：

- 登录用户和租户上下文识别。
- 模块权限校验。
- 参数校验和字段归一化。
- 数据库事务。
- 写操作二次确认。
- 审计日志。
- 错误信息结构化。

### 6.2 编写 InputSchema 并注册 @agent_tool

在业务模块内创建或更新 `agent_tools.py`，定义 Pydantic v2 InputSchema，并使用 `@agent_tool` 注册 operation。

推荐目录：

```text
app/modules/<module>/agent_tools.py
```

示例：

```python
from pydantic import BaseModel

from app.modules.agent.tools import ToolContext, agent_tool


class QualityInspectionListInput(BaseModel):
    status: str | None = None
    keyword: str | None = None
    page: int = 1
    page_size: int = 20


@agent_tool(
    name="quality.list_inspections",
    summary="查询质量检查记录",
    input_model=QualityInspectionListInput,
    write=False,
    risk_level="medium",
    workflow_allowed=True,
    method="GET",
    path="/quality/inspections",
)
async def list_quality_inspections(
    context: ToolContext,
    data: QualityInspectionListInput,
) -> dict:
    ...
```

工具 handler 应调用本模块 Service 或 public API，不直接操作数据库，不直接调用其他模块内部实现。

### 6.3 命名 operation

建议 operation 命名采用：

```text
模块名.动作名_资源名
```

示例：

```text
warehouse.list_raw_materials
procurement.create_purchase_request
quality.list_inspections
```

### 6.4 触发后端工具注册

在 Dazah 后端 `app/modules/agent/tool_registration.py` 中导入新模块的 `agent_tools.py`，保证 FastAPI 启动时触发装饰器注册。

示例：

```python
import app.modules.quality.agent_tools  # noqa: F401
```

注册成功后，Dazah 后端会通过以下接口暴露工具元数据：

```text
GET /api/v1/agent/tools
```

### 6.5 同步 Hermes-Lite 本地 schema

Hermes-Lite 当前仍在 `tools/dazah_platform.py` 中保留 `ALLOWED_OPERATIONS`，用于模型工具 schema 枚举和本地防御层。新增后端工具后，需要同步：

- `ALLOWED_OPERATIONS`
- `DAZAH_TOOL_SCHEMA["parameters"]["properties"]["operation"]["enum"]`
- 如有必要，更新 README 工具清单和系统提示词

后续如果 Hermes 改为启动时动态读取 `GET /api/v1/agent/tools`，则 `ALLOWED_OPERATIONS` 可以降级为离线兜底缓存。

### 6.6 更新工具 schema 描述

如果新模块需要特定参数，应补充工具输入模型和 `input_schema` 描述，帮助模型生成更准确的结构化参数。参数校验最终由 Dazah 后端 Pydantic InputSchema 负责。

### 6.7 更新系统提示词

在 `services/dazah_agent_service.py` 的 `_system_prompt()` 中补充模块边界和回复规范。

当前提示词要求：

- 不编造平台数据。
- 必须通过 `dazah_tool` 查询平台业务数据。
- 写操作只能生成确认项。
- 禁止输出 Markdown 表格。
- 少量数据卡片式展示。
- 大量数据摘要 + 前几条 + 继续查看提示。
- 复杂明细分组展示。

新增模块时，应让模型清楚该模块支持哪些查询、哪些写操作需要确认、哪些字段必须重点展示。

### 6.8 前端展示适配

如果新模块返回复杂数据，优先让 LLM 组织成业务卡片式回复。对于稳定结构的数据，也可以在前端增加专用渲染组件。

建议：

- 少量数据：完整卡片。
- 大量数据：摘要 + 前 3 条 + “查看更多”。
- 复杂明细：折叠展示。
- 异常数据：单独标记。
- 避免 Markdown 表格。

### 6.9 验证用例

每个新模块至少验证以下场景：

- 普通查询。
- 带筛选条件查询。
- 空结果。
- 参数缺失。
- 无权限。
- 写操作生成确认项。
- 用户确认后执行成功。
- 用户取消确认。
- 工具返回错误时的前端展示。
- 流式输出中断。

## 7. 数据查询方式

Hermes-Lite 不直接查询数据库。

数据查询统一走：

```text
Hermes-Lite
  -> dazah_tool
  -> Dazah 后端 Agent 工具网关
  -> Dazah 后端业务模块
  -> PostgreSQL / 飞书同步数据 / 业务服务
```

这样可以确保：

- 数据权限仍由 Dazah 后端控制。
- 数据库表结构不会暴露给 LLM。
- 业务规则集中在后端。
- 写操作可被确认和审计。
- 后续新增模块时不会破坏 Agent 的安全边界。

## 8. 字段筛选适配建议

针对查询类工具，建议统一支持 `filters` 参数。

建议格式：

```json
{
  "filters": [
    {
      "field": "quantity",
      "op": "gte",
      "value": 100
    }
  ],
  "page": 1,
  "page_size": 20
}
```

建议操作符：

| 操作符 | 含义 |
| --- | --- |
| `eq` | 等于 |
| `ne` | 不等于 |
| `gt` | 大于 |
| `gte` | 大于等于 |
| `lt` | 小于 |
| `lte` | 小于等于 |
| `contains` | 包含 |
| `in` | 在指定集合中 |
| `between` | 区间范围 |

建议由 Dazah 后端负责字段白名单、类型转换和 SQL 条件构造，Hermes 只负责根据用户自然语言生成结构化筛选参数。

## 9. 本地运行

安装依赖：

```bash
pip install -r requirements.txt
cp .env.example .env
```

本地启动 Hermes 适配服务：

```bash
uvicorn services.dazah_agent_service:app --host 0.0.0.0 --port 8100
```

Docker 开发环境启动：

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

健康检查：

```bash
curl http://127.0.0.1:8100/health
```

预期返回：

```json
{
  "status": "ok"
}
```

Dazah 后端工具发现检查：

```bash
curl -H "Authorization: Bearer $DAZAH_AGENT_TOOL_TOKEN" \
  "$DAZAH_API_BASE_URL/agent/tools"
```

该接口应返回后端当前注册的 Agent 工具列表。Hermes 本地 `ALLOWED_OPERATIONS` 应与该列表保持同步。

## 10. 环境变量

| 变量 | 说明 |
| --- | --- |
| `HERMES_AGENT_TOKEN` | Dazah 后端调用 Hermes 的服务令牌 |
| `AGENT_LLM_PROXY_TOKEN` | Hermes 调用 Dazah LLM 代理的服务令牌 |
| `DAZAH_LLM_BASE_URL` | Dazah LLM 代理地址 |
| `DAZAH_LLM_MODEL` | Hermes 请求时使用的模型名称，通常为 `dazah-active-text` |
| `DAZAH_API_BASE_URL` | Dazah 后端 API 地址 |
| `DAZAH_AGENT_TOOL_TOKEN` | Hermes 调用 Dazah 工具网关的服务令牌 |
| `HERMES_DAZAH_CHAT_TIMEOUT_SECONDS` | Hermes 对话超时时间，默认 180 秒 |
| `HERMES_DAZAH_MAX_TOOL_ITERATIONS` | 单轮 Livzon Agent 最大模型/工具迭代次数，默认 30，最高 90 |

示例：

```bash
HERMES_AGENT_TOKEN=change-me
AGENT_LLM_PROXY_TOKEN=change-me
DAZAH_API_BASE_URL=http://app:8000/api/v1
DAZAH_AGENT_TOOL_TOKEN=change-me
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
DAZAH_LLM_MODEL=dazah-active-text
HERMES_DAZAH_CHAT_TIMEOUT_SECONDS=180
HERMES_DAZAH_MAX_TOOL_ITERATIONS=30
```

## 11. 项目结构

```text
Hermes-Lite/
├── agent/                    # Agent 核心运行时
├── tools/                    # 工具注册中心和平台工具
│   └── dazah_platform.py     # Dazah 平台工具网关
├── services/
│   └── dazah_agent_service.py # Dazah Agent 适配服务
├── hermes_cli/               # 轻量配置和认证兼容辅助模块
├── providers/                # 模型提供商扩展接口
├── plugins/                  # 最小插件命名空间包
├── scripts/                  # 工具脚本
├── toolsets.py               # 工具集定义
├── model_tools.py            # 工具 schema 加载与分发逻辑
├── run_agent.py              # Agent 主入口
├── config.yaml               # 默认配置
└── docs/INTEGRATION.md       # 补充集成说明
```

## 12. 验证命令

语法检查：

```bash
python -m py_compile run_agent.py model_tools.py toolsets.py services/dazah_agent_service.py tools/dazah_platform.py
```

容器内检查：

```bash
docker exec hermes-lite python -m py_compile /app/services/dazah_agent_service.py /app/tools/dazah_platform.py
```

健康检查：

```bash
docker exec hermes-lite python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=10).read().decode())"
```

## 13. 安全边界

Hermes-Lite 在 Dazah 平台中的安全原则：

- 不直接保存真实模型供应商密钥。
- 不直接连接业务数据库。
- 不绕过 Dazah 后端权限体系。
- 不直接执行写操作，写操作必须进入确认流程。
- 不默认启用终端、文件、浏览器、代码执行等高风险工具。
- 不允许 LLM 调用任意 URL 执行业务操作。
- 所有业务操作必须先注册到 Dazah 后端 `ToolRegistry`。
- 所有工具调用都应可审计、可追踪、可失败恢复。

## 14. License

MIT. See [LICENSE](LICENSE).
