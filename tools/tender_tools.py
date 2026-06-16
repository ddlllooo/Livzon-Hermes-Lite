"""招标智能匹配工具 — 注册到 LeadFlow Agent 工具注册表。

提供四个业务工具：
  1. tender_search     — 搜索招标项目（结构化筛选 + 语义检索）
  2. tender_recommend  — 为指定企业推荐匹配的招标项目
  3. tender_match      — 评估企业与招标的匹配度（六维度评分）
  4. tender_analyze    — 深度分析招标项目（竞争度/资质门槛/策略建议）
"""

import json
import logging

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


# ── 可用性检查 ───────────────────────────────────────────────────────

def check_tender_available() -> bool:
    """检查招标系统是否可用。"""
    try:
        from services.config import get_config
        cfg = get_config()
        return bool(cfg.ob.database)
    except Exception:
        return False


# ── 获取 TenderService ───────────────────────────────────────────────

def _get_service():
    from services.tender_service import TenderService
    from services.chunk_store import get_chunk_store
    from services.embedding_service import get_embedder
    return TenderService(
        chunk_store=get_chunk_store(),
        embedder=get_embedder(),
    )


# ── Schema 定义 ──────────────────────────────────────────────────────

TENDER_SEARCH_SCHEMA = {
    "name": "tender_search",
    "description": (
        "搜索招标项目。支持按行业、地区、预算范围、招标类型、截止日期等条件筛选，"
        "也支持自然语言关键词全文检索。返回活跃招标列表。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "关键词检索（项目名称/内容全文搜索）",
            },
            "industry": {
                "type": "string",
                "description": "行业筛选（如：IT、医疗、建筑、教育、交通）",
            },
            "region": {
                "type": "string",
                "description": "地区筛选（如：北京、广东、上海）",
            },
            "budget_min": {
                "type": "number",
                "description": "预算下限（万元）",
            },
            "budget_max": {
                "type": "number",
                "description": "预算上限（万元）",
            },
            "tender_type": {
                "type": "string",
                "description": "招标类型（公开招标/邀请招标/竞争性谈判/询价）",
            },
            "deadline_before": {
                "type": "string",
                "description": "截止日期之前（格式：YYYY-MM-DD）",
            },
            "status": {
                "type": "string",
                "enum": ["active", "closed", "awarded", "cancelled"],
                "default": "active",
                "description": "招标状态，默认 active",
            },
            "limit": {
                "type": "integer",
                "description": "返回数量，默认 20",
                "default": 20,
            },
        },
        "required": [],
    },
}

TENDER_RECOMMEND_SCHEMA = {
    "name": "tender_recommend",
    "description": (
        "为指定企业推荐最匹配的招标项目。输入企业ID，系统基于六维度匹配模型"
        "（行业/地域/资质/预算/能力/业绩）从活跃招标中筛选并评分，"
        "返回推荐列表及匹配分析、中标概率、投标准备建议。"
        "当用户询问'哪些项目适合我们'、'推荐一些招标'时使用此工具。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_id": {
                "type": "string",
                "description": "企业ID",
            },
            "top_k": {
                "type": "integer",
                "description": "推荐数量，默认 5",
                "default": 5,
            },
            "min_score": {
                "type": "number",
                "description": "最低匹配分（0-100），低于此分数的不推荐，默认 40",
                "default": 40,
            },
            "industry": {
                "type": "string",
                "description": "限定行业（可选）",
            },
            "region": {
                "type": "string",
                "description": "限定地区（可选）",
            },
        },
        "required": ["company_id"],
    },
}

TENDER_MATCH_SCHEMA = {
    "name": "tender_match",
    "description": (
        "评估指定企业与指定招标项目的匹配度。返回六维度评分"
        "（行业/地域/资质/预算/能力/业绩）、综合匹配分、中标概率预测、"
        "匹配优势、风险因素、投标准备建议。"
        "当用户询问'我们能不能投这个项目'、'这个标我们中标概率多大'时使用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "company_id": {
                "type": "string",
                "description": "企业ID",
            },
            "tender_id": {
                "type": "string",
                "description": "招标项目ID",
            },
        },
        "required": ["company_id", "tender_id"],
    },
}

TENDER_ANALYZE_SCHEMA = {
    "name": "tender_analyze",
    "description": (
        "深度分析招标项目。返回招标详情、资质门槛分析、竞争度评估、"
        "已匹配企业列表、相似招标推荐、投标策略建议。"
        "当用户询问'分析一下这个项目'、'这个标竞争大吗'时使用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tender_id": {
                "type": "string",
                "description": "招标项目ID",
            },
        },
        "required": ["tender_id"],
    },
}


# ── Handler 实现 ─────────────────────────────────────────────────────

def _tender_search_handler(args: dict, **kwargs) -> str:
    try:
        svc = _get_service()
        results = svc.search_tenders(
            keyword=args.get("keyword", ""),
            industry=args.get("industry", ""),
            region=args.get("region", ""),
            budget_min=args.get("budget_min", 0),
            budget_max=args.get("budget_max", 0),
            tender_type=args.get("tender_type", ""),
            deadline_before=args.get("deadline_before", ""),
            status=args.get("status", "active"),
            limit=args.get("limit", 20),
        )
        if not results:
            return json.dumps({"results": [], "total": 0,
                               "message": "未找到符合条件的招标项目"}, ensure_ascii=False)
        return json.dumps({"results": results, "total": len(results)},
                          ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("招标搜索失败: %s", e)
        return tool_error(f"搜索失败: {e}")


def _tender_recommend_handler(args: dict, **kwargs) -> str:
    try:
        svc = _get_service()
        rec = svc.recommend_for_company(
            company_id=args["company_id"],
            top_k=args.get("top_k", 5),
            min_score=args.get("min_score", 40),
            industry=args.get("industry", ""),
            region=args.get("region", ""),
        )
        results = []
        for m in rec.recommendations:
            results.append({
                "tender_id": m.tender_id,
                "title": m.tender_title,
                "total_score": m.total_score,
                "win_probability": m.win_probability,
                "recommendation": m.recommendation,
                "scores": {
                    "industry": m.industry_score,
                    "region": m.region_score,
                    "qualification": m.qual_score,
                    "budget": m.budget_score,
                    "capability": m.capability_score,
                    "experience": m.experience_score,
                },
                "match_reasons": m.match_reasons,
                "risk_factors": m.risk_factors,
                "suggestions": m.suggestions,
            })
        return json.dumps({
            "company": rec.company_name,
            "summary": rec.summary,
            "results": results,
            "total": len(results),
        }, ensure_ascii=False, default=str)
    except ValueError as e:
        return tool_error(str(e))
    except Exception as e:
        logger.exception("招标推荐失败: %s", e)
        return tool_error(f"推荐失败: {e}")


def _tender_match_handler(args: dict, **kwargs) -> str:
    try:
        svc = _get_service()
        m = svc.match(
            company_id=args["company_id"],
            tender_id=args["tender_id"],
        )
        return json.dumps({
            "tender": {"id": m.tender_id, "title": m.tender_title},
            "company": {"id": m.company_id, "name": m.company_name},
            "scores": {
                "industry": m.industry_score,
                "region": m.region_score,
                "qualification": m.qual_score,
                "budget": m.budget_score,
                "capability": m.capability_score,
                "experience": m.experience_score,
            },
            "total_score": m.total_score,
            "win_probability": m.win_probability,
            "recommendation": m.recommendation,
            "match_reasons": m.match_reasons,
            "risk_factors": m.risk_factors,
            "suggestions": m.suggestions,
        }, ensure_ascii=False, default=str)
    except ValueError as e:
        return tool_error(str(e))
    except Exception as e:
        logger.exception("匹配评估失败: %s", e)
        return tool_error(f"匹配失败: {e}")


def _tender_analyze_handler(args: dict, **kwargs) -> str:
    try:
        svc = _get_service()
        analysis = svc.analyze_tender(tender_id=args["tender_id"])
        return json.dumps(analysis, ensure_ascii=False, default=str)
    except ValueError as e:
        return tool_error(str(e))
    except Exception as e:
        logger.exception("招标分析失败: %s", e)
        return tool_error(f"分析失败: {e}")


# ── 注册（模块级，AST 自动发现）──────────────────────────────────────

registry.register(
    name="tender_search",
    toolset="tender",
    schema=TENDER_SEARCH_SCHEMA,
    handler=_tender_search_handler,
    check_fn=check_tender_available,
    description="搜索招标项目（多条件筛选+全文检索）",
    emoji="🔍",
    max_result_size_chars=100_000,
)

registry.register(
    name="tender_recommend",
    toolset="tender",
    schema=TENDER_RECOMMEND_SCHEMA,
    handler=_tender_recommend_handler,
    check_fn=check_tender_available,
    description="为企业推荐匹配招标（六维度匹配+中标概率）",
    emoji="🎯",
    max_result_size_chars=100_000,
)

registry.register(
    name="tender_match",
    toolset="tender",
    schema=TENDER_MATCH_SCHEMA,
    handler=_tender_match_handler,
    check_fn=check_tender_available,
    description="企业-招标匹配评估（六维度评分+风险分析）",
    emoji="📊",
    max_result_size_chars=50_000,
)

registry.register(
    name="tender_analyze",
    toolset="tender",
    schema=TENDER_ANALYZE_SCHEMA,
    handler=_tender_analyze_handler,
    check_fn=check_tender_available,
    description="招标深度分析（竞争度/资质门槛/策略建议）",
    emoji="📋",
    max_result_size_chars=80_000,
)
