import asyncio
import json

from tools import dazah_platform


def test_dazah_tool_preserves_extra_feishu_message_arguments(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "requires_confirmation": True}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url, json, headers):
            recorded["url"] = url
            recorded["json"] = json
            recorded["headers"] = headers
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setenv("DAZAH_API_BASE_URL", "http://dazah.test/api/v1")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)

    raw_result = asyncio.run(
        dazah_platform.dazah_tool(
            "identity.send_feishu_message",
            feishu_user_id="danhao",
            message="偏差记录",
            reason="发送偏差记录",
        )
    )

    assert json.loads(raw_result)["ok"] is True
    payload = recorded["json"]
    assert payload["operation"] == "identity.send_feishu_message"
    assert payload["body"]["feishu_user_id"] == "danhao"
    assert payload["body"]["message"] == "偏差记录"
    assert payload["body"]["user_ids"] == ["danhao"]
    assert payload["body"]["text"] == "偏差记录"


def test_dazah_tool_normalizes_legacy_feishu_message_body(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "requires_confirmation": True}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url, json, headers):
            recorded["json"] = json
            return FakeResponse()

    monkeypatch.setenv("DAZAH_AGENT_TOOL_TOKEN", "test-token")
    monkeypatch.setattr(dazah_platform.httpx, "AsyncClient", FakeAsyncClient)

    asyncio.run(
        dazah_platform.dazah_tool(
            "identity.send_feishu_message",
            body={
                "user_id": "ou_f062239403858caa9066c43d1dbc2ff7",
                "message_type": "text",
                "content": "偏差记录",
            },
        )
    )

    payload = recorded["json"]
    assert payload["body"]["user_ids"] == ["ou_f062239403858caa9066c43d1dbc2ff7"]
    assert payload["body"]["text"] == "偏差记录"
