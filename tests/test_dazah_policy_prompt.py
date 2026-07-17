from pathlib import Path


SERVICE_SOURCE = Path(__file__).resolve().parents[1] / "services" / "dazah_agent_service.py"


def test_prompt_narrows_human_decision_policy_to_responsibility_actions() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")

    assert "高风险拒绝仅限审批决定、批准、驳回、拒绝、关键连接重启" in source
    assert "点击‘确认执行’" in source
    assert "都不属于高风险拒绝范围" in source
    assert "应调用相应工具生成待确认项" in source
    assert "供前端确认执行卡片展示；不得先用普通回复询问是否发送" in source
