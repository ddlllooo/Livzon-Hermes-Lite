"""知识库检索工具 — 注册到 LeadFlow Agent 工具注册表。

Agent 通过 knowledge_search 工具从企业知识库中检索相关文档。
底层使用 OceanBase 原生混合检索（Vector + BM25）+ Rerank 精排。

自动发现：registry.register() 在模块顶层调用，
          Core 的 discover_builtin_tools() 会自动导入本模块。
"""

import json
import logging

from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)


# ── 可用性检查 ───────────────────────────────────────────────────────

def check_knowledge_available() -> bool:
    """检查知识库检索是否可用（OceanBase 连接 + Embedding 配置）。"""
    try:
        from services.config import get_config
        cfg = get_config()
        # 至少需要 OceanBase DSN + Embedding API Key
        if not cfg.ob.database:
            return False
        if not cfg.embedding.api_key:
            return False
        return True
    except Exception:
        return False


# ── 工具 Schema ──────────────────────────────────────────────────────

KNOWLEDGE_SEARCH_SCHEMA = {
    "name": "knowledge_search",
    "description": (
        "从企业知识库中检索与查询最相关的文档片段。"
        "内部使用 OceanBase 原生混合检索（向量语义 + BM25关键词）+ Cross-Encoder Rerank 精排，"
        "返回父块完整文本作为 LLM 上下文。"
        "适用场景：查找公司内部文档、产品信息、业务规则、历史数据、"
        "合同条款、政策法规等结构化/非结构化知识。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索查询，用自然语言描述需要查找的内容。建议使用具体、明确的表述。",
            },
            "top_k": {
                "type": "integer",
                "description": "返回的父块数量，默认 3，最大 10。",
                "default": 3,
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
}


# ── 工具 Handler ─────────────────────────────────────────────────────

def _knowledge_search_handler(args: dict, **kwargs) -> str:
    """执行知识库检索。同步调用。"""
    query = (args.get("query") or "").strip()
    if not query:
        return tool_error("query 不能为空")

    top_k = args.get("top_k", 3)
    if not isinstance(top_k, int) or top_k < 1:
        top_k = 3
    top_k = min(top_k, 10)

    try:
        from services.retrieval_pipeline import RetrievalPipeline
        from services.chunk_store import get_chunk_store
        from services.embedding_service import get_embedder
        from services.rerank_service import get_reranker

        pipeline = RetrievalPipeline(
            chunk_store=get_chunk_store(),
            embedder=get_embedder(),
            reranker=get_reranker(),
            config={"final_top_n": top_k},
        )
        results = pipeline.search(query)

        if not results:
            return json.dumps({
                "results": [],
                "total": 0,
                "message": "未找到与查询相关的知识库内容",
            }, ensure_ascii=False)

        formatted = []
        for r in results:
            formatted.append({
                "parent_id": r.parent_id,
                "content": r.content,
                "source": r.source,
                "score": r.score,
                "matched_children": r.matched_children,
            })

        return json.dumps({
            "results": formatted,
            "total": len(formatted),
        }, ensure_ascii=False)

    except ImportError as e:
        logger.error("知识库依赖缺失: %s", e)
        return tool_error(f"知识库服务依赖未安装: {e}")
    except RuntimeError as e:
        logger.error("知识库运行时错误: %s", e)
        return tool_error(f"知识库服务错误: {e}")
    except Exception as e:
        logger.exception("知识库检索异常: %s", e)
        return tool_error(f"检索失败: {e}")


# ── 注册（模块级，AST 自动发现）──────────────────────────────────────

registry.register(
    name="knowledge_search",
    toolset="knowledge",
    schema=KNOWLEDGE_SEARCH_SCHEMA,
    handler=_knowledge_search_handler,
    check_fn=check_knowledge_available,
    description="企业知识库混合检索（OceanBase Vector + BM25 + Rerank）",
    emoji="📚",
    max_result_size_chars=200_000,
)
