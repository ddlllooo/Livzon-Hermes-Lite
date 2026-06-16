"""Embedding 向量生成服务。

支持 DeepSeek / OpenAI 兼容 API，同步调用（工具 handler 内使用）。
"""

import json
import logging
from typing import List, Optional

import httpx

from services.config import get_config

logger = logging.getLogger(__name__)

# ── Provider 默认配置 ────────────────────────────────────────────────

PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-embedding",
        "dimensions": 1536,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "text-embedding-3-small",
        "dimensions": 1536,
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "embedding-3",
        "dimensions": 2048,
    },
}


class EmbeddingService:
    """Embedding 向量生成 — 同步 HTTP 调用。"""

    def __init__(self):
        self.cfg = get_config().embedding
        defaults = PROVIDER_DEFAULTS.get(self.cfg.provider, {})
        self.base_url = self.cfg.base_url or defaults.get("base_url", "")
        self.model = self.cfg.model or defaults.get("model", "")
        self.dimensions = self.cfg.dimensions or defaults.get("dimensions", 1536)
        self.api_key = self.cfg.api_key
        self.batch_size = self.cfg.batch_size or 64
        self.timeout = self.cfg.timeout or 30

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def embed(self, text: str) -> List[float]:
        """单条文本 → 向量。"""
        vectors = self.embed_batch([text])
        return vectors[0] if vectors else [0.0] * self.dimensions

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """批量文本 → 向量列表。超出 batch_size 自动分批。"""
        if not texts:
            return []
        if not self.api_key:
            logger.error("EMBEDDING_API_KEY 未配置")
            raise RuntimeError("Embedding API key 未配置")

        all_vectors: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i: i + self.batch_size]
            vectors = self._call_api(batch)
            all_vectors.extend(vectors)
        return all_vectors

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        """调用 Embedding API（OpenAI 兼容格式）。"""
        url = f"{self.base_url.rstrip('/')}/embeddings"
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float",
        }
        # 部分 provider 支持 dimensions 参数
        if self.dimensions and self.cfg.provider in ("openai", "zhipu"):
            payload["dimensions"] = self.dimensions

        try:
            resp = httpx.post(
                url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error("Embedding API HTTP 错误: %s %s", e.response.status_code, e.response.text[:200])
            raise RuntimeError(f"Embedding API 返回 {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error("Embedding API 请求失败: %s", e)
            raise RuntimeError(f"无法连接 Embedding 服务: {e}") from e

        data = resp.json()
        items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
        return [item["embedding"] for item in items]

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)


# ── 单例 ─────────────────────────────────────────────────────────────

_embedder: Optional[EmbeddingService] = None


def get_embedder() -> EmbeddingService:
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingService()
    return _embedder
