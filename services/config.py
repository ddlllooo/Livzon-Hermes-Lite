"""Hermes-Lite 检索管道配置 — 从环境变量 / .env 读取。"""

import os
from dataclasses import dataclass, field
from typing import Optional


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


# ── OceanBase ────────────────────────────────────────────────────────

@dataclass
class OBConfig:
    host: str = field(default_factory=lambda: _env("OCEANBASE_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("OCEANBASE_PORT", 2881))
    user: str = field(default_factory=lambda: _env("OCEANBASE_USER", "root"))
    password: str = field(default_factory=lambda: _env("OCEANBASE_PASSWORD", ""))
    database: str = field(default_factory=lambda: _env("OCEANBASE_DATABASE", "hermes_lite"))
    charset: str = "utf8mb4"

    # 连接池
    pool_min: int = field(default_factory=lambda: _env_int("OB_POOL_MIN", 2))
    pool_max: int = field(default_factory=lambda: _env_int("OB_POOL_MAX", 10))

    @property
    def dsn(self) -> dict:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "db": self.database,
            "charset": self.charset,
        }


# ── Embedding ────────────────────────────────────────────────────────

@dataclass
class EmbeddingConfig:
    provider: str = field(default_factory=lambda: _env("EMBEDDING_PROVIDER", "deepseek"))
    model: str = field(default_factory=lambda: _env("EMBEDDING_MODEL", "deepseek-embedding"))
    base_url: str = field(default_factory=lambda: _env("EMBEDDING_BASE_URL", "https://api.deepseek.com/v1"))
    api_key: str = field(default_factory=lambda: _env("EMBEDDING_API_KEY"))
    dimensions: int = field(default_factory=lambda: _env_int("EMBEDDING_DIMENSIONS", 1536))
    batch_size: int = field(default_factory=lambda: _env_int("EMBEDDING_BATCH_SIZE", 64))
    timeout: int = field(default_factory=lambda: _env_int("EMBEDDING_TIMEOUT", 30))


# ── Rerank ───────────────────────────────────────────────────────────

@dataclass
class RerankConfig:
    enabled: bool = field(default_factory=lambda: _env("RERANK_ENABLED", "true").lower() == "true")
    provider: str = field(default_factory=lambda: _env("RERANK_PROVIDER", "bge"))
    model: str = field(default_factory=lambda: _env("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"))
    base_url: str = field(default_factory=lambda: _env("RERANK_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: _env("RERANK_API_KEY", ""))
    timeout: int = field(default_factory=lambda: _env_int("RERANK_TIMEOUT", 30))


# ── 检索参数 ─────────────────────────────────────────────────────────

@dataclass
class RetrievalConfig:
    vector_top_k: int = field(default_factory=lambda: _env_int("RETRIEVAL_VECTOR_TOP_K", 20))
    bm25_top_k: int = field(default_factory=lambda: _env_int("RETRIEVAL_BM25_TOP_K", 20))
    rrf_k: int = field(default_factory=lambda: _env_int("RETRIEVAL_RRF_K", 60))
    rerank_top_n: int = field(default_factory=lambda: _env_int("RETRIEVAL_RERANK_TOP_N", 10))
    final_top_n: int = field(default_factory=lambda: _env_int("RETRIEVAL_FINAL_TOP_N", 3))


# ── 聚合配置 ─────────────────────────────────────────────────────────

@dataclass
class KnowledgeConfig:
    ob: OBConfig = field(default_factory=OBConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)


_config: Optional[KnowledgeConfig] = None


def get_config() -> KnowledgeConfig:
    global _config
    if _config is None:
        _config = KnowledgeConfig()
    return _config
