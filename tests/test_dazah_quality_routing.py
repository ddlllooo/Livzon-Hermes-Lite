from pathlib import Path


SERVICE_SOURCE = Path(__file__).resolve().parents[1] / "services" / "dazah_agent_service.py"


def test_dazah_prompt_routes_quality_requests_to_quality_tools() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")

    assert "服务仓储、采购、质量管理和 Livzon 助手通讯录查询" in source
    assert "必须优先调用 dazah_tool 的 quality.* operation" in source
    assert "quality.list_deviation_report_records" in source


def test_skill_resolver_default_scope_includes_quality() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")

    assert 'default_scope = ["identity", "warehouse", "procurement", "quality"]' in source
    assert '"business_scope": _business_scope(payload.context)' in source


def test_quality_report_records_use_direct_router() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")

    assert "def _quality_report_records_intent" in source
    assert "def _try_direct_quality_response" in source
    assert '"quality.list_deviation_report_records"' in source
    assert "direct_response = await _try_direct_quality_response(payload)" in source
