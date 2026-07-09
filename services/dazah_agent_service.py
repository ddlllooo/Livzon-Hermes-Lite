#!/usr/bin/env python3
"""Hermes-Lite service adapter for Dazah Agent gateway."""

import json
import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from run_agent import AIAgent
from tools.dazah_platform import dazah_request_context, dazah_tool

logger = logging.getLogger(__name__)


class DazahChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class DazahChatResponse(BaseModel):
    message: str
    pending_confirmations: list[dict[str, Any]] = Field(default_factory=list)
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


app = FastAPI(title="Hermes-Lite Dazah Adapter")


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        logger.warning("Invalid integer env %s=%r, using default %s", name, raw_value, default)
        return default
    if value < minimum:
        return minimum
    if maximum is not None and value > maximum:
        return maximum
    return value


def _require_token(authorization: str | None) -> None:
    expected = os.getenv("HERMES_AGENT_TOKEN")
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Hermes token")
    if authorization.removeprefix("Bearer ").strip() != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Hermes token")


def _system_prompt(progressive_skills: list[dict[str, Any]] | None = None) -> str:
    base_prompt = (
        "你是工厂管理平台的Agent助手，服务仓储、采购、质量管理和 Livzon 助手通讯录查询。"
        "你必须通过 dazah_tool 获取平台数据或创建写操作确认项；"
        "不要编造库存、供应商、采购申请、订单、合同、质量记录、人员通讯录或飞书同步状态。"
        "用户询问质量模块、偏差、偏差报告记录、CAPA、变更、变更计划、验证、CPV、质量飞书台账或质量同步时，"
        "必须优先调用 dazah_tool 的 quality.* operation，而不是仓储飞书表目录或普通飞书同步表查询。"
        "用户说“质量模块的报告记录数据表”或“质量报告记录”时，默认指偏差报告记录，"
        "应调用 quality.list_deviation_report_records；需要详情时再根据返回记录继续查询相关偏差或同步状态。"
        "质量模块可查询偏差、CAPA、变更、变更计划、验证、CPV、飞书CAPA台账、飞书验证记录和质量同步冲突；"
        "质量写入、同步、回拉和提醒只生成确认项，删除、审批通过、驳回、飞书配置和文件导入不开放给助手。"
        "涉及今天、明天、每天几点或设置定时任务时，必须先调用 agent.get_current_time 获取当前北京时间和 cron 时区。"
        "写操作只会生成确认项，用户确认前不得声称已经执行。"
        "发送飞书消息时优先使用 identity.send_feishu_message：低价值、短消息发文本；"
        "中高价值、结构化消息发卡片；需要处理的业务消息发交互卡片。"
        "调用飞书消息工具时，收件人必须放在 body.user_ids 数组，"
        "可填本地用户UUID、飞书user_id、open_id、工号、手机号、邮箱或姓名；"
        "消息正文必须放在 body.text。"
        "发送确认前必须展示收件人、消息形态、标题/正文摘要，以及是否包含处理按钮。"
        "回答要像业务系统里的卡片式回复，禁止输出 Markdown 表格，禁止使用 |---| 这类表格语法。"
        "少量数据要完整展示为字段清晰的卡片式文本；大量数据先给摘要、前 3 条记录，并提示可继续查看更多；"
        "复杂明细要先给关键结论，再用分组列表呈现明细，不要把所有字段堆成一行。"
        "1. 严禁使用 Markdown 表格。"
        "2. 严禁使用竖线分隔符，例如：| 产品 | 规格 | 数量 |。"
        "3. 严禁用空格对齐多列数据。"
        "4. 严禁把多个字段挤在同一行。"
        "必须使用以下形式："
        "- 标题"    
        "- - 一句话总结"
        "- - 产品分组"
        "- - 每个规格独立换行展示"
        "- - 异常数据要单独标记"
        "- 如果数据超过 5 条规格，只展示前 5 条，并提示用户可以继续查看全部。"
    )
    if not progressive_skills:
        return base_prompt
    skill_blocks = []
    for skill in progressive_skills:
        name = skill.get("name") or "unknown"
        title = skill.get("title") or name
        content = skill.get("content") or ""
        if content:
            skill_blocks.append(f"## {title} ({name})\n{content}")
    if not skill_blocks:
        return base_prompt
    return (
        base_prompt
        + "\n\n# 本轮相关内置 Skill\n"
        + "以下 Skill 由 Dazah 后端按用户消息渐进式披露。若与当前请求相关，必须遵循。\n"
        + "\n\n".join(skill_blocks)
    )


def _history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages[-20:]:
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            result.append({"role": role, "content": content})
    return result


def _looks_like_confirmation(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("id"), str)
        and isinstance(value.get("operation"), str)
        and isinstance(value.get("summary"), str)
        and isinstance(value.get("risk_level"), str)
        and isinstance(value.get("status"), str)
        and isinstance(value.get("expires_at"), str)
    )


def _collect_confirmations(value: Any, seen: set[str]) -> list[dict[str, Any]]:
    confirmations: list[dict[str, Any]] = []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return confirmations
    if isinstance(value, list):
        for item in value:
            confirmations.extend(_collect_confirmations(item, seen))
        return confirmations
    if not isinstance(value, dict):
        return confirmations

    if value.get("requires_confirmation") and _looks_like_confirmation(value.get("confirmation")):
        confirmation = value["confirmation"]
        confirmation_id = confirmation["id"]
        if confirmation_id not in seen:
            seen.add(confirmation_id)
            confirmations.append(confirmation)
    if _looks_like_confirmation(value.get("pending_confirmation")):
        confirmation = value["pending_confirmation"]
        confirmation_id = confirmation["id"]
        if confirmation_id not in seen:
            seen.add(confirmation_id)
            confirmations.append(confirmation)
    if _looks_like_confirmation(value):
        confirmation_id = value["id"]
        if confirmation_id not in seen:
            seen.add(confirmation_id)
            confirmations.append(value)

    for item in value.values():
        confirmations.extend(_collect_confirmations(item, seen))
    return confirmations


def _extract_confirmations(agent: AIAgent, result: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    confirmations: list[dict[str, Any]] = []
    for message in getattr(agent, "_session_messages", []) or []:
        confirmations.extend(_collect_confirmations(message, seen))
    if result:
        confirmations.extend(_collect_confirmations(result, seen))
    return confirmations


def _base_url() -> str:
    return os.getenv("DAZAH_API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")


def _business_scope(context: dict[str, Any]) -> list[str]:
    default_scope = ["identity", "warehouse", "procurement", "quality"]
    incoming_scope = context.get("scope")
    if not isinstance(incoming_scope, list):
        return default_scope

    merged = list(default_scope)
    for item in incoming_scope:
        if isinstance(item, str) and item and item not in merged:
            merged.append(item)
    return merged


def _quality_report_records_intent(message: str) -> bool:
    normalized = re.sub(r"\s+", "", message)
    if not normalized:
        return False
    if "偏差报告记录" in normalized or "质量报告记录" in normalized:
        return True
    return "质量模块" in normalized and ("报告记录" in normalized or "数据表" in normalized)


def _requested_page_size(message: str, default: int = 5) -> int:
    match = re.search(r"(?:前|最近)\s*(\d{1,2})\s*条", message)
    if not match:
        return default
    return max(1, min(int(match.group(1)), 20))


def _short_text(value: Any, limit: int = 120) -> str:
    if value is None or value == "":
        return "-"
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _tool_envelope_data(raw_result: str) -> dict[str, Any]:
    payload = json.loads(raw_result)
    if not isinstance(payload, dict):
        return {"ok": False, "error": "工具返回格式不是对象"}
    data = payload.get("data")
    if isinstance(data, dict) and "ok" in data:
        return data
    return payload


def _format_deviation_report_records(tool_data: dict[str, Any], page_size: int) -> str:
    if not tool_data.get("ok"):
        error = tool_data.get("error") or tool_data.get("data") or "质量工具执行失败"
        return f"质量模块报告记录查询失败：{_short_text(error, 300)}"

    records_data = tool_data.get("data")
    if not isinstance(records_data, dict):
        return "质量模块报告记录查询完成，但返回数据格式异常。"

    items = records_data.get("items")
    if not isinstance(items, list):
        items = []
    total = records_data.get("total")
    shown = min(len(items), page_size)

    lines = [
        "已通过质量模块工具 quality.list_deviation_report_records 查询偏差报告记录。",
        f"本次展示：{shown} 条" + (f"，总数：{total} 条" if isinstance(total, int) else ""),
    ]
    if not items:
        lines.append("当前没有查询到偏差报告记录。")
        return "\n".join(lines)

    for index, item in enumerate(items[:page_size], start=1):
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"- 记录 {index}：{_short_text(item.get('deviation_code'))}",
                f"  - 状态：{_short_text(item.get('report_status'))}",
                f"  - 报告时间：{_short_text(item.get('report_time'))}",
                f"  - 部门/报告人：{_short_text(item.get('department'))} / {_short_text(item.get('reporter_name'))}",
                f"  - 产品批号：{_short_text(item.get('product_batch'))}",
                f"  - 飞书同步：{_short_text(item.get('feishu_sync_status'))}",
                f"  - 描述：{_short_text(item.get('description'))}",
            ]
        )
    if isinstance(total, int) and total > shown:
        lines.append("如需继续查看，可以让我查询后续记录或按偏差编号筛选。")
    return "\n".join(lines)


async def _try_direct_quality_response(payload: DazahChatRequest) -> DazahChatResponse | None:
    if not _quality_report_records_intent(payload.message):
        return None

    page_size = _requested_page_size(payload.message)
    params = {"page": 1, "page_size": page_size}
    raw_result = await dazah_tool(
        "quality.list_deviation_report_records",
        params=params,
        reason="查询质量模块偏差报告记录",
    )
    tool_data = _tool_envelope_data(raw_result)
    return DazahChatResponse(
        message=_format_deviation_report_records(tool_data, page_size),
        pending_confirmations=_collect_confirmations(tool_data, set()),
        tool_trace=[
            {
                "tool": "dazah_tool",
                "operation": "quality.list_deviation_report_records",
                "params": params,
                "ok": bool(tool_data.get("ok")),
            }
        ],
    )


async def _check_dazah_llm_proxy() -> str | None:
    token = os.getenv("AGENT_LLM_PROXY_TOKEN", "")
    base_url = os.getenv("DAZAH_LLM_BASE_URL", "http://127.0.0.1:8000/api/v1/agent/llm").rstrip("/")
    if not token:
        return "AGENT_LLM_PROXY_TOKEN 未配置"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception as exc:
        return f"Dazah LLM 代理不可达：{type(exc).__name__}: {exc}"
    if response.status_code >= 400:
        return f"Dazah LLM 代理返回 {response.status_code}: {response.text[:500]}"
    return None


async def _resolve_progressive_skills(payload: DazahChatRequest) -> list[dict[str, Any]]:
    token = os.getenv("DAZAH_AGENT_TOOL_TOKEN", "")
    if not token:
        return []
    request_payload = {
        "message": payload.message,
        "enabled_toolsets": ["agent", "dazah"],
        "business_scope": _business_scope(payload.context),
        "available_tools": ["dazah_tool", "memory", "session_search", "todo", "clarify"],
        "limit": 3,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{_base_url()}/agent/skills/resolve",
                json=request_payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            logger.warning("Dazah skill resolver returned %s: %s", response.status_code, response.text[:500])
            return []
        payload_data = response.json()
        data = payload_data.get("data") if isinstance(payload_data, dict) else None
        skills = data.get("skills") if isinstance(data, dict) else None
        return skills if isinstance(skills, list) else []
    except Exception:
        logger.exception("Dazah skill resolver failed")
        return []


def _run_agent_conversation(
    payload: DazahChatRequest,
    progressive_skills: list[dict[str, Any]] | None = None,
    stream_callback: Callable[[str | None], None] | None = None,
) -> tuple[AIAgent, dict[str, Any]]:
    agent = AIAgent(
        base_url=os.getenv("DAZAH_LLM_BASE_URL", "http://127.0.0.1:8000/api/v1/agent/llm"),
        api_key=os.getenv("AGENT_LLM_PROXY_TOKEN", ""),
        model=os.getenv("DAZAH_LLM_MODEL", "dazah-active-text"),
        api_mode="chat_completions",
        enabled_toolsets=["agent", "dazah"],
        disabled_toolsets=[],
        quiet_mode=True,
        max_iterations=_env_int("HERMES_DAZAH_MAX_TOOL_ITERATIONS", 30, minimum=1, maximum=90),
        user_id=payload.context.get("user_id"),
        thread_id=payload.session_id,
    )
    result = agent.run_conversation(
        payload.message,
        system_message=_system_prompt(progressive_skills),
        conversation_history=_history(payload.messages),
        stream_callback=stream_callback,
    )
    return agent, result


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat", response_model=DazahChatResponse)
async def chat(payload: DazahChatRequest, authorization: str | None = Header(default=None)) -> DazahChatResponse:
    _require_token(authorization)
    token = dazah_request_context.set(payload.context)
    try:
        direct_response = await _try_direct_quality_response(payload)
        if direct_response is not None:
            return direct_response

        try:
            proxy_error = await _check_dazah_llm_proxy()
            if proxy_error:
                return DazahChatResponse(
                    message=f"Livzon Agent 运行异常：{proxy_error}",
                    pending_confirmations=[],
                    tool_trace=[],
                )
            progressive_skills = await _resolve_progressive_skills(payload)
            timeout_seconds = _env_int("HERMES_DAZAH_CHAT_TIMEOUT_SECONDS", 180, minimum=30, maximum=900)
            agent, result = await asyncio.wait_for(
                asyncio.to_thread(_run_agent_conversation, payload, progressive_skills),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            logger.exception("Hermes-Lite Dazah chat timed out")
            return DazahChatResponse(
                message="Livzon Agent 运行超时：模型或工具调用响应时间过长，请稍后重试。",
                pending_confirmations=[],
                tool_trace=[],
            )
        except Exception as exc:
            logger.exception("Hermes-Lite Dazah chat failed")
            return DazahChatResponse(
                message=f"Livzon Agent 运行异常：{type(exc).__name__}: {exc}",
                pending_confirmations=[],
                tool_trace=[],
            )
        message = result.get("final_response") or "我没有生成有效回复，请稍后重试。"
        return DazahChatResponse(
            message=message,
            pending_confirmations=_extract_confirmations(agent, result),
            tool_trace=result.get("tool_trace") or [],
        )
    finally:
        dazah_request_context.reset(token)


@app.post("/v1/chat/stream")
async def chat_stream(payload: DazahChatRequest, authorization: str | None = Header(default=None)) -> StreamingResponse:
    _require_token(authorization)

    async def event_stream():
        token = dazah_request_context.set(payload.context)
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_delta(delta: str | None) -> None:
            if delta:
                loop.call_soon_threadsafe(queue.put_nowait, {"event": "delta", "data": {"text": delta}})

        try:
            direct_response = await _try_direct_quality_response(payload)
            if direct_response is not None:
                yield _sse_event(
                    "done",
                    {
                        "message": direct_response.message,
                        "pending_confirmations": direct_response.pending_confirmations,
                        "tool_trace": direct_response.tool_trace,
                    },
                )
                return

            proxy_error = await _check_dazah_llm_proxy()
            if proxy_error:
                yield _sse_event("error", {"message": f"Livzon Agent 运行异常：{proxy_error}"})
                return

            progressive_skills = await _resolve_progressive_skills(payload)
            timeout_seconds = _env_int("HERMES_DAZAH_CHAT_TIMEOUT_SECONDS", 180, minimum=30, maximum=900)
            deadline = time.monotonic() + timeout_seconds
            task = asyncio.create_task(
                asyncio.to_thread(
                    _run_agent_conversation,
                    payload,
                    progressive_skills,
                    on_delta,
                )
            )
            last_heartbeat = time.monotonic()
            while True:
                if task.done() and queue.empty():
                    break
                if time.monotonic() >= deadline:
                    task.cancel()
                    logger.warning("Hermes-Lite Dazah stream chat timed out")
                    yield _sse_event(
                        "error",
                        {"message": "Livzon Agent 运行超时：模型或工具调用响应时间过长，请稍后重试。"},
                    )
                    return
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    if now - last_heartbeat >= 10:
                        last_heartbeat = now
                        yield _sse_event("ping", {"ts": int(now)})
                    continue
                last_heartbeat = time.monotonic()
                yield _sse_event(item["event"], item["data"])

            try:
                agent, result = await asyncio.wait_for(task, timeout=timeout_seconds)
            except TimeoutError:
                logger.exception("Hermes-Lite Dazah stream chat timed out")
                yield _sse_event(
                    "error",
                    {"message": "Livzon Agent 运行超时：模型或工具调用响应时间过长，请稍后重试。"},
                )
                return
            except Exception as exc:
                logger.exception("Hermes-Lite Dazah stream chat failed")
                yield _sse_event("error", {"message": f"Livzon Agent 运行异常：{type(exc).__name__}: {exc}"})
                return

            yield _sse_event(
                "done",
                {
                    "message": result.get("final_response") or "我没有生成有效回复，请稍后重试。",
                    "pending_confirmations": _extract_confirmations(agent, result),
                    "tool_trace": result.get("tool_trace") or [],
                },
            )
        finally:
            dazah_request_context.reset(token)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
