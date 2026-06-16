"""Cross-Encoder Rerank 精排服务。

支持 BGE Reranker / Jina Reranker / Cohere Rerank API。
当 RERANK_ENABLED=false 或配置不完整时，退化为跳过精排（透传）。
"""

import logging
from typing import List, Optional, Tuple

import httpx

from services.config import get_config

logger = logging.getLogger(__name__)

# ── Provider 默认配置 ────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "bge": {
        # BGE Reranker 通常本地部署（如 Xinference / TEI）
        "base_url": "http://localhost:9997/v1",
        "model": "BAAI/bge-reranker-v2-m3",
    },
    "jina": {
        "base_url": "https://api.jina.ai/v1",
        "model": "jina-reranker-v2-base-multilingual",
    },
    "cohere": {
        "base_url": "https://api.cohere.com/v2",
        "model": "rerank-v3.5",
    },
}


class RerankService:
    """Cross-Encoder 精排 — 同步 HTTP 调用。"""

    def __init__(self):
        self.cfg = get_config().rerank
        defaults = PROVIDER_DEFAULTS.get(self.cfg.provider, {})
        self.base_url = self.cfg.base_url or defaults.get("base_url", "")
        self.model = self.cfg.model or defaults.get("model", "")
        self.api_key = self.cfg.api_key
        self.timeout = self.cfg.timeout or 30

    # ── Public API ───────────────────────────────────────────────────

    def rerank(self, query: str, documents: List[str], top_n: int = 0) -> List[Tuple[int, float]]:
        """精排打分。

        返回 [(原始索引, 相关性分数), ...] 按分数降序排列。
        top_n=0 表示返回全部。
        """
        if not self.available or not documents:
            # 退化：原样返回，分数均为 1.0
            return [(i, 1.0) for i in range(len(documents))]

        try:
            if self.cfg.provider == "cohere":
                return self._rerank_cohere(query, documents, top_n)
            else:
                return self._rerank_openai_compat(query, documents, top_n)
        except Exception as e:
            logger.warning("Rerank 失败，退化为透传: %s", e)
            return [(i, 1.0) for i in range(len(documents))]

    def score(self, pairs: List[Tuple[str, str]]) -> List[float]:
        """逐对打分 — (query, document) → relevance score。

        用于需要独立打分而非排序的场景。
        """
        if not self.available or not pairs:
            return [1.0] * len(pairs)

        scores = []
        for query, doc in pairs:
            results = self.rerank(query, [doc], top_n=1)
            scores.append(results[0][1] if results else 0.0)
        return scores

    # ── OpenAI 兼容 API（BGE / Jina）────────────────────────────────

    def _rerank_openai_compat(
        self, query: str, documents: List[str], top_n: int
    ) -> List[Tuple[int, float]]:
        """OpenAI 兼容 Rerank API（Xinference / TEI / Jina）。"""
        url = f"{self.base_url.rstrip('/')}/rerank"
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n or len(documents),
            "return_documents": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            results.append((idx, float(score)))
        return results

    # ── Cohere Rerank API ────────────────────────────────────────────

    def _rerank_cohere(
        self, query: str, documents: List[str], top_n: int
    ) -> List[Tuple[int, float]]:
        """Cohere Rerank v2 API。"""
        url = f"{self.base_url.rstrip('/')}/rerank"
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n or len(documents),
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get("results", []):
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            results.append((idx, float(score)))
        return results

    @property
    def available(self) -> bool:
        if not self.cfg.enabled:
            return False
        return bool(self.base_url and self.model)


# ── 单例 ─────────────────────────────────────────────────────────────

_reranker: Optional[RerankService] = None


def get_reranker() -> RerankService:
    global _reranker
    if _reranker is None:
        _reranker = RerankService()
    return _reranker
