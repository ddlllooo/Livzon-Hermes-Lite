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
    "quality.add_capa_execution_track",
    "quality.auto_fill_capa_from_deviation",
    "quality.complete_capa_part",
    "quality.create_capa",
    "quality.create_change",
    "quality.create_change_action_plan",
    "quality.create_cpv_parameter",
    "quality.create_cpv_product",
    "quality.create_deviation",
    "quality.create_validation",
    "quality.get_capa",
    "quality.get_capa_statistics",
    "quality.get_change",
    "quality.get_change_statistics",
    "quality.get_cpv_product",
    "quality.get_cpv_statistics",
    "quality.get_cpv_trend",
    "quality.get_deviation",
    "quality.get_deviation_statistics",
    "quality.get_feishu_capa_ledger",
    "quality.get_feishu_capa_plan_track",
    "quality.get_feishu_validation",
    "quality.get_next_change_code",
    "quality.get_related_capas",
    "quality.get_validation",
    "quality.get_validation_statistics",
    "quality.link_capa_deviation",
    "quality.list_capa_departments",
    "quality.list_capas",
    "quality.list_change_action_plans",
    "quality.list_change_action_plans_by_change",
    "quality.list_changes",
    "quality.list_cpv_batches",
    "quality.list_cpv_cpp_batches",
    "quality.list_cpv_cqa_batches",
    "quality.list_cpv_parameters",
    "quality.list_cpv_products",
    "quality.list_deviation_report_records",
    "quality.list_deviations",
    "quality.list_feishu_capa_ledger",
    "quality.list_feishu_capa_plan_tracks",
    "quality.list_feishu_validations",
    "quality.list_quality_sync_conflicts",
    "quality.list_validation_executions",
    "quality.list_validations",
    "quality.pull_feishu_validations",
    "quality.pull_quality_records_from_feishu",
    "quality.resubmit_capa",
    "quality.resubmit_deviation",
    "quality.run_change_action_plan_reminders",
    "quality.send_change_action_plan_reminder",
    "quality.submit_capa",
    "quality.submit_deviation",
    "quality.submit_deviation_investigation",
    "quality.sync_capa_plan_track_to_feishu",
    "quality.sync_capa_to_feishu",
    "quality.sync_change_action_plan",
    "quality.sync_change_action_plans_from_feishu",
    "quality.sync_deviation_report_record_to_feishu",
    "quality.sync_deviation_to_feishu",
    "quality.update_capa",
    "quality.update_change",
    "quality.update_change_action_plan",
    "quality.update_cpv_parameter",
    "quality.update_cpv_product",
    "quality.update_deviation",
    "quality.update_validation",
    "quality.update_validation_execution",
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

FEISHU_MESSAGE_OPERATIONS = {
    "identity.send_feishu_message",
    "identity.send_feishu_text_message",
    "identity.send_feishu_card_message",
}

FEISHU_RECIPIENT_ALIASES = (
    "recipient",
    "recipients",
    "recipient_id",
    "recipient_ids",
    "recipient_user_id",
    "recipient_user_ids",
    "to",
    "to_user",
    "to_users",
    "to_user_id",
    "to_user_ids",
    "user_id",
    "feishu_id",
    "feishu_user_id",
    "feishu_user_ids",
    "feishu_open_id",
    "feishu_open_ids",
    "open_id",
    "open_ids",
    "employee_no",
    "employee_nos",
)

FEISHU_RECIPIENT_OBJECT_KEYS = (
    "id",
    "user_id",
    "feishu_id",
    "feishu_user_id",
    "feishu_open_id",
    "open_id",
    "employee_no",
    "name",
)

FEISHU_TEXT_ALIASES = (
    "content",
    "message",
    "message_content",
    "body_text",
)


def _normalize_operation(operation: str) -> str:
    return operation if operation in ALLOWED_OPERATIONS else OPERATION_ALIASES.get(operation, operation)


def _append_identifier(result: list[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            _append_identifier(result, item)
        return
    if isinstance(value, dict):
        for key in FEISHU_RECIPIENT_OBJECT_KEYS:
            nested = value.get(key)
            if nested:
                _append_identifier(result, nested)
                return
        return
    text = str(value).strip()
    if text:
        result.append(text)


def _normalize_feishu_message_body(
    operation: str,
    body: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if operation not in FEISHU_MESSAGE_OPERATIONS or body is None:
        return body

    normalized = dict(body)
    if not normalized.get("user_ids"):
        recipient_ids: list[str] = []
        for key in FEISHU_RECIPIENT_ALIASES:
            if key in normalized:
                _append_identifier(recipient_ids, normalized.get(key))
        if recipient_ids:
            normalized["user_ids"] = recipient_ids

    if not normalized.get("text"):
        for key in FEISHU_TEXT_ALIASES:
            value = normalized.get(key)
            if isinstance(value, str) and value.strip():
                normalized["text"] = value.strip()
                break

    if operation == "identity.send_feishu_card_message" and not normalized.get("markdown"):
        for key in ("text", *FEISHU_TEXT_ALIASES):
            value = normalized.get(key)
            if isinstance(value, str) and value.strip():
                normalized["markdown"] = value.strip()
                break

    return normalized


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

    if _ignored:
        body = {**(body or {}), **_ignored}
    body = _normalize_feishu_message_body(operation, body)

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
        "Call Dazah platform identity, warehouse, procurement, and quality operations through the Agent "
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
        "put recipient identifiers in body.user_ids and message content in body.text; "
        "body.user_ids accepts local UUID, Feishu user_id, Feishu open_id, employee_no, "
        "mobile, email, or name. "
        "summarize recipients, message shape, title/body summary, and whether "
        "handling buttons are included before user confirmation. Quality module "
        "tools cover deviations, CAPA, change controls, validations, CPV, and "
        "quality Feishu read/sync operations; deletion, approval/rejection, "
        "Feishu configuration, and file import operations are intentionally not "
        "exposed. Old text/card operations are compatibility-only."
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
