import json

import pytest

from services import dazah_agent_service as service


MESSAGE = """请向但昊发送一张飞书交互卡片。
标题：Livzon 回调闭环最终验收
正文：这是一条飞书卡片回调最终验收消息，请完成操作。
按钮：
1. 开始处理
2. 标记完成

此操作需要先生成确认卡片，等待我点击“确认执行”后再发送。不要直接执行。"""


def test_structured_feishu_card_parses_supported_business_actions() -> None:
    request = service._structured_feishu_send_request(MESSAGE)

    assert request is not None
    assert request["recipient"] == "但昊"
    assert request["body"]["message_form"] == "interactive_card"
    assert request["body"]["requires_business_action"] is True
    assert [item["action_key"] for item in request["body"]["actions"]] == [
        "start_processing",
        "mark_done",
    ]


def test_unverified_confirmation_claims_are_blocked() -> None:
    result = service._verified_agent_message("已执行确认操作：发送消息", [], [])

    assert result == "没有查询到后端真实确认记录，本次未执行任何操作。请重新提交完整的收件人和消息内容。"


def test_explicit_send_command_requires_real_confirmation_without_extra_question() -> None:
    instruction = service._write_confirmation_routing_instruction(
        "请汇总2026年6月采购清单，然后发送给但昊"
    )

    assert "必须立即调用 identity.send_feishu_message" in instruction
    assert "不得再询问‘是否发送’" in instruction


def test_send_status_query_does_not_enter_write_confirmation_route() -> None:
    instruction = service._write_confirmation_routing_instruction("查询昨天的飞书发送状态")

    assert instruction == ""


def test_only_pending_confirmations_are_collected() -> None:
    base = {
        "id": "7ff93cb9-1e5b-4e2c-aa43-9572f9a99bdd",
        "operation": "identity.send_feishu_message",
        "summary": "发送交互卡片",
        "risk_level": "medium",
        "expires_at": "2026-07-16T16:00:00+08:00",
    }

    assert service._collect_confirmations({**base, "status": "pending"}, set())
    assert service._collect_confirmations({**base, "status": "executed"}, set()) == []
    assert service._collect_confirmations({**base, "status": "expired"}, set()) == []


def test_real_confirmation_replaces_redundant_send_question() -> None:
    confirmation = {
        "id": "7ff93cb9-1e5b-4e2c-aa43-9572f9a99bdd",
        "operation": "identity.send_feishu_message",
        "summary": "发送交互卡片",
        "risk_level": "medium",
        "status": "pending",
        "expires_at": "2026-07-16T16:00:00+08:00",
    }

    message = service._verified_agent_message(
        "采购清单已汇总。请确认是否发送？",
        [confirmation],
        [],
    )

    assert "是否发送" not in message
    assert "点击“确认执行”" in message


@pytest.mark.asyncio
async def test_direct_route_returns_only_real_gateway_confirmation(monkeypatch) -> None:
    confirmation = {
        "id": "7ff93cb9-1e5b-4e2c-aa43-9572f9a99bdd",
        "operation": "identity.send_feishu_message",
        "summary": "发送交互卡片",
        "risk_level": "medium",
        "status": "pending",
        "expires_at": "2026-07-16T16:00:00+08:00",
    }

    async def fake_dazah_tool(operation, *, body, reason):
        assert operation == "identity.send_feishu_message"
        assert body["user_ids"] == ["但昊"]
        assert reason
        return json.dumps(
            {
                "data": {
                    "ok": True,
                    "requires_confirmation": True,
                    "confirmation": confirmation,
                }
            }
        )

    monkeypatch.setattr(service, "dazah_tool", fake_dazah_tool)
    response = await service._try_direct_feishu_send_response(
        service.DazahChatRequest(session_id="test-session", message=MESSAGE)
    )

    assert response is not None
    assert response.pending_confirmations == [confirmation]
    assert response.tool_trace[0]["confirmation_created"] is True
    assert confirmation["id"] in response.message
