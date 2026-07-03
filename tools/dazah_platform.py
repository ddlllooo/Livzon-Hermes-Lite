#!/usr/bin/env python3
"""Dazah platform tool gateway for Hermes-Lite.

The tool never calls arbitrary URLs. It only posts operation requests to the
Dazah Agent tool gateway, where the actual Dazah whitelist is
enforced and write operations become user confirmations.
"""

import contextvars
import json
import os
from typing import Any

import httpx

from tools.registry import registry


dazah_request_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "dazah_request_context",
    default={},
)

ALLOWED_OPERATIONS = [
    "analytics.aggregate",
    "identity.get_department_tree",
    "identity.search_personnel",
    "identity.check_feishu_permissions",
    "identity.send_feishu_message",
    "identity.send_feishu_text_message",
    "identity.send_feishu_card_message",
    "warehouse.list_raw_materials",
    "warehouse.list_packaging_materials",
    "warehouse.list_products",
    "warehouse.list_feishu_tables",
    "warehouse.get_feishu_table_records",
    "warehouse.get_feishu_domain_records",
    "warehouse.get_feishu_ws_status",
    "warehouse.refresh_feishu_tables",
    "warehouse.set_feishu_tables_enabled",
    "warehouse.set_feishu_table_enabled",
    "warehouse.sync_feishu_table",
    "warehouse.restart_feishu_ws",
    "procurement.list_invoice_records",
    "procurement.list_suppliers",
    "procurement.list_purchase_requests",
    "procurement.get_purchase_request",
    "procurement.create_purchase_request",
    "procurement.update_purchase_request",
    "procurement.submit_purchase_request",
    "procurement.approve_purchase_request",
    "procurement.reject_purchase_request",
    "procurement.list_purchase_orders",
    "procurement.export_purchase_orders",
    "procurement.list_contract_templates",
    "procurement.get_contract_template",
    "procurement.generate_contract",
    "agent.get_current_time",
    "agent.list_workflow_capabilities",
    "agent.create_workflow",
    "agent.list_workflows",
    "agent.get_workflow",
    "agent.set_workflow_enabled",
    "agent.run_workflow",
    "agent.cancel_workflow_run",
    "agent.get_workflow_run",
]


def _build_operation_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()
    for operation in ALLOWED_OPERATIONS:
        suffix = operation.rsplit(".", 1)[-1]
        if suffix in aliases:
            aliases.pop(suffix, None)
            ambiguous.add(suffix)
        elif suffix not in ambiguous:
            aliases[suffix] = operation
    return aliases


OPERATION_ALIASES = _build_operation_aliases()


def _normalize_operation(operation: str) -> str:
    return operation if operation in ALLOWED_OPERATIONS else OPERATION_ALIASES.get(operation, operation)


def _base_url() -> str:
    return os.getenv("DAZAH_API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")


def check_dazah_requirements() -> bool:
    return bool(os.getenv("DAZAH_AGENT_TOOL_TOKEN"))


async def dazah_tool(
    operation: str | dict[str, Any],
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    reason: str | None = None,
    **_ignored: Any,
) -> str:
    if isinstance(operation, dict):
        payload = operation
        operation = str(payload.get("operation", ""))
        params = payload.get("params") if params is None else params
        body = payload.get("body") if body is None else body
        context = payload.get("context") if context is None else context
        reason = payload.get("reason") if reason is None else reason
    operation = _normalize_operation(operation)
    if operation not in ALLOWED_OPERATIONS:
        return json.dumps(
            {"ok": False, "error": "operation is not allowed", "operation": operation},
            ensure_ascii=False,
        )
    token = os.getenv("DAZAH_AGENT_TOOL_TOKEN")
    if not token:
        return json.dumps(
            {"ok": False, "error": "DAZAH_AGENT_TOOL_TOKEN is not configured"},
            ensure_ascii=False,
        )

    merged_context = {**dazah_request_context.get({}), **(context or {})}
    payload = {
        "operation": operation,
        "params": params or {},
        "body": body,
        "context": merged_context,
        "reason": reason,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{_base_url()}/agent/tools/execute", json=payload, headers=headers)
        if response.status_code >= 400:
            return json.dumps(
                {
                    "ok": False,
                    "operation": operation,
                    "status_code": response.status_code,
                    "error": response.text[:1000],
                },
                ensure_ascii=False,
            )
        return json.dumps(response.json(), ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {"ok": False, "operation": operation, "error": str(exc)},
            ensure_ascii=False,
        )


DAZAH_TOOL_SCHEMA = {
    "name": "dazah_tool",
    "description": (
        "Call Dazah platform identity, warehouse, and procurement operations through the Agent "
        "tool gateway. For full-dataset counts, TopN, distributions, distinct "
        "counts, or grouped statistics, prefer analytics.aggregate instead of "
        "paging through list operations. Read operations execute immediately. "
        "Write operations return a pending confirmation for the frontend to "
        "display; never claim a write operation has executed until the gateway "
        "result says it has. Before creating or adjusting daily scheduled tasks, "
        "call agent.get_current_time to get the current Asia/Shanghai time and "
        "cron timezone; do not guess today's date or current time. "
        "For Feishu outbound messages, prefer identity.send_feishu_message. "
        "Use low value short unstructured notifications as text; use medium/high "
        "value or structured summaries as cards; use requires_business_action=true "
        "for business messages that need handling, which sends callback interactive "
        "cards. First identify recipients via identity.search_personnel and "
        "summarize recipients, message shape, title/body summary, and whether "
        "handling buttons are included before user confirmation. Old text/card "
        "operations are compatibility-only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ALLOWED_OPERATIONS,
                "description": "Whitelisted Dazah operation name.",
            },
            "params": {
                "type": "object",
                "description": "Query and path parameters, for example table_id, request_id, category, page, page_size.",
            },
            "body": {
                "type": "object",
                "description": "JSON request body for create/update/submit/approve/generate operations.",
            },
            "context": {
                "type": "object",
                "description": "Optional extra context. Session and user context is added automatically by Hermes service.",
            },
            "reason": {
                "type": "string",
                "description": "Short user-facing reason/summary for write confirmations.",
            },
        },
        "required": ["operation"],
    },
}


registry.register(
    name="dazah_tool",
    toolset="dazah",
    schema=DAZAH_TOOL_SCHEMA,
    handler=dazah_tool,
    check_fn=check_dazah_requirements,
    requires_env=["DAZAH_AGENT_TOOL_TOKEN"],
    is_async=True,
    description="Dazah platform tool gateway",
    emoji="",
)
