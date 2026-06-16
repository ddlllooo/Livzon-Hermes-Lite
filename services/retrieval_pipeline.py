"""LeadFlow 检索管道 — 四阶段完整流程。

用户 Query
    │
    ▼
  ① OceanBase 原生混合检索（Vector + BM25 + RRF 融合）→ ~30 候选子块
    │
    ▼
  ② Rerank 精排（Cross-Encoder）→ Top-10 子块
    │
    ▼
  ③ parent_id 反查 + 去重聚合 → Top-3 父块
    │
    ▼
  ④ 父块完整文本 → LLM Context
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """检索结果 — 一个父块。"""
    parent_id: str
    content: str          # 父块完整文本
    score: float          # 聚合最终分数
    source: str           # 来源文档标识
    matched_children: int # 命中子块数
    metadata: dict = field(default_factory=dict)


class RetrievalPipeline:
    """完整检索管道。

    初始化时接受外部注入的依赖（不自行创建），
    与 Core 完全解耦，可独立测试。
    """

    def __init__(
        self,
        chunk_store,
        embedder,
        reranker,
        config: dict = None,
    ):
        self.store = chunk_store
        self.embedder = embedder
        self.reranker = reranker
        cfg = config or {}

        from services.config import get_config
        default = get_config().retrieval
        self.vector_top_k = cfg.get("vector_top_k", default.vector_top_k)
        self.bm25_top_k = cfg.get("bm25_top_k", default.bm25_top_k)
        self.rrf_k = cfg.get("rrf_k", default.rrf_k)
        self.rerank_top_n = cfg.get("rerank_top_n", default.rerank_top_n)
        self.final_top_n = cfg.get("final_top_n", default.final_top_n)

    def search(self, query: str) -> List[RetrievalResult]:
        """执行完整四阶段检索管道。同步调用。"""
        if not query or not query.strip():
            return []

        query = query.strip()

        # ─── ① OceanBase 原生混合检索 ──────────────────────────────
        logger.info("检索管道 query='%s'", query[:80])
        candidates = self._hybrid_search(query)
        if not candidates:
            logger.info("混合检索无结果")
            return []

        # ─── ② Rerank 精排 ────────────────────────────────────────
        reranked = self._rerank(query, candidates)

        # ─── ③ 父块反查 + 去重聚合 ────────────────────────────────
        parents = self._aggregate_parents(reranked)

        # ─── ④ 返回 Top-N 父块 ────────────────────────────────────
        results = parents[: self.final_top_n]
        logger.info(
            "检索完成: %d 子块 → %d 父块 → 返回 %d",
            len(candidates), len(parents), len(results),
        )
        return results

    # ── ① 混合检索 ──────────────────────────────────────────────────

    def _hybrid_search(self, query: str) -> List[Dict[str, Any]]:
        """OceanBase 原生混合检索（Vector + BM25 + RRF）。

        单条 SQL 完成向量检索 + BM25 检索 + RRF 融合，
        由 OceanBase 数据库层原生执行。
        """
        # 生成 query embedding
        query_vector = self.embedder.embed(query)

        # 调用 OceanBase 原生混合检索
        candidates = self.store.hybrid_search(
            query_text=query,
            query_vector=query_vector,
            top_k=30,
        )

        logger.debug("混合检索返回 %d 候选子块", len(candidates))
        return candidates

    # ── ② Rerank 精排 ───────────────────────────────────────────────

    def _rerank(
        self, query: str, candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Cross-Encoder 精排。"""
        if not self.reranker.available:
            # Rerank 未配置，按 hybrid_score 截断
            logger.debug("Rerank 不可用，按 hybrid_score 截断 Top-%d", self.rerank_top_n)
            return candidates[: self.rerank_top_n]

        documents = [c["content"] for c in candidates]
        ranked = self.reranker.rerank(query, documents, top_n=self.rerank_top_n)

        # 将 rerank 分数写回候选
        reranked = []
        for idx, score in ranked:
            item = candidates[idx]
            item["rerank_score"] = score
            reranked.append(item)

        logger.debug("Rerank 精排完成，Top-%d 子块", len(reranked))
        return reranked

    # ── ③ 父块反查 + 聚合 ──────────────────────────────────────────

    def _aggregate_parents(
        self, chunks: List[Dict[str, Any]]
    ) -> List[RetrievalResult]:
        """parent_id 反查 + 分数叠加 + 去重。

        同一父块的多个子块命中时，分数叠加。
        最终按聚合分数降序排列。
        """
        # 聚合：同一 parent_id 的子块分数叠加
        parent_agg: Dict[str, Dict[str, Any]] = {}
        for i, chunk in enumerate(chunks):
            pid = chunk["parent_id"]
            if pid not in parent_agg:
                parent_agg[pid] = {
                    "total_score": 0.0,
                    "matched_children": 0,
                    "best_rank": i,
                }
            # 使用 rerank_score（如有）或 hybrid_score
            score = chunk.get("rerank_score", chunk.get("hybrid_score", 0))
            parent_agg[pid]["total_score"] += score
            parent_agg[pid]["matched_children"] += 1

        # 按聚合分数降序
        sorted_pids = sorted(
            parent_agg.keys(),
            key=lambda pid: (parent_agg[pid]["total_score"], -parent_agg[pid]["best_rank"]),
            reverse=True,
        )

        # 批量获取父块完整文本
        parent_ids_needed = sorted_pids[: self.final_top_n]
        parents_data = self.store.get_parents_batch(parent_ids_needed)

        results = []
        for pid in parent_ids_needed:
            parent = parents_data.get(pid)
            if not parent:
                logger.warning("父块 %s 不存在", pid)
                continue
            agg = parent_agg[pid]
            results.append(RetrievalResult(
                parent_id=pid,
                content=parent["content"],
                score=round(agg["total_score"], 6),
                source=parent.get("source", ""),
                matched_children=agg["matched_children"],
                metadata=parent.get("metadata") or {},
            ))

        return results
