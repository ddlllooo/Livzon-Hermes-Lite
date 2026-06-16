"""OceanBase 原生混合检索存储层。

使用 OceanBase V4.4.1+ 的原生能力：
  - VECTOR 数据类型 + COSINE_DISTANCE 向量检索
  - FULLTEXT INDEX + MATCH AGAINST BM25 关键词检索
  - 通过 SQL 层原生 RRF 融合实现混合检索

依赖：pymysql（同步，工具 handler 内直接调用）
"""

import json
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from services.config import OBConfig, get_config

logger = logging.getLogger(__name__)

# ── 延迟导入 pymysql ─────────────────────────────────────────────────

_pymysql = None


def _ensure_pymysql():
    global _pymysql
    if _pymysql is None:
        try:
            import pymysql
            _pymysql = pymysql
        except ImportError:
            raise RuntimeError(
                "需要 pymysql: pip install pymysql\n"
                "OceanBase 使用 MySQL 协议（端口 2881）"
            )


# ── 连接池 ───────────────────────────────────────────────────────────

class _ConnectionPool:
    """简易同步连接池，复用 pymysql 连接。"""

    def __init__(self, dsn: dict, min_size: int = 2, max_size: int = 10):
        self._dsn = dsn
        self._min = min_size
        self._max = max_size
        self._pool: list = []
        self._in_use = 0

    def _create_conn(self):
        _ensure_pymysql()
        return _pymysql.connect(
            **self._dsn,
            cursorclass=_pymysql.cursors.DictCursor,
            autocommit=True,
        )

    @contextmanager
    def connection(self):
        conn = None
        try:
            if self._pool:
                conn = self._pool.pop()
                # 检查连接是否存活
                try:
                    conn.ping(reconnect=True)
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = self._create_conn()
            else:
                conn = self._create_conn()
            self._in_use += 1
            yield conn
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
            raise
        finally:
            self._in_use -= 1
            if conn and len(self._pool) < self._max:
                self._pool.append(conn)
            elif conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def close_all(self):
        for conn in self._pool:
            try:
                conn.close()
            except Exception:
                pass
        self._pool.clear()


# ── ChunkStore ───────────────────────────────────────────────────────

class ChunkStore:
    """OceanBase 原生混合检索。

    表结构（见 scripts/init_knowledge_db.sql）：
      - parent_chunks: 父块表（完整文档片段）
      - child_chunks:  子块表（带 embedding VECTOR + FULLTEXT 索引）
    """

    def __init__(self, config: OBConfig = None):
        self._cfg = config or get_config().ob
        self._pool = _ConnectionPool(
            dsn=self._cfg.dsn,
            min_size=self._cfg.pool_min,
            max_size=self._cfg.pool_max,
        )

    def close(self):
        self._pool.close_all()

    # ─────────────────────────────────────────────────────────────────
    # ① 原生混合检索（OceanBase BM25 + Vector + RRF 一体化）
    # ─────────────────────────────────────────────────────────────────

    def hybrid_search(
        self,
        query_text: str,
        query_vector: List[float],
        top_k: int = 30,
    ) -> List[Dict[str, Any]]:
        """OceanBase 原生混合检索：向量语义 + BM25 关键词，RRF 融合。

        利用 OceanBase 的 VECTOR 类型 + FULLTEXT 索引 + 窗口函数实现
        单条 SQL 内的 RRF 融合，无需应用层拼接。

        返回 top_k 个候选子块，每个包含：
          chunk_id, parent_id, content, vector_score, bm25_score, hybrid_score
        """
        vector_str = self._vector_to_str(query_vector)

        # OceanBase 原生混合 SQL：
        # 1) vector_rank: 按 COSINE_DISTANCE 排序的排名
        # 2) bm25_rank:   按 MATCH AGAINST 排序的排名
        # 3) rrf_score:   1/(k+rank) 融合
        sql = """
            WITH vector_hits AS (
                SELECT
                    chunk_id, parent_id, content,
                    (1 - COSINE_DISTANCE(embedding, %s)) AS vector_score,
                    ROW_NUMBER() OVER (
                        ORDER BY COSINE_DISTANCE(embedding, %s) ASC
                    ) AS v_rank
                FROM child_chunks
                ORDER BY COSINE_DISTANCE(embedding, %s) ASC
                LIMIT %s
            ),
            bm25_hits AS (
                SELECT
                    chunk_id, parent_id, content,
                    MATCH(content) AGAINST(%s IN NATURAL LANGUAGE MODE) AS bm25_score,
                    ROW_NUMBER() OVER (
                        ORDER BY MATCH(content) AGAINST(%s IN NATURAL LANGUAGE MODE) DESC
                    ) AS b_rank
                FROM child_chunks
                WHERE MATCH(content) AGAINST(%s IN NATURAL LANGUAGE MODE)
                ORDER BY bm25_score DESC
                LIMIT %s
            ),
            combined AS (
                SELECT chunk_id, parent_id, content,
                       COALESCE(v.vector_score, 0) AS vector_score,
                       COALESCE(b.bm25_score, 0) AS bm25_score,
                       COALESCE(v.v_rank, 9999) AS v_rank,
                       COALESCE(b.b_rank, 9999) AS b_rank
                FROM vector_hits v
                LEFT JOIN bm25_hits b USING (chunk_id)
                UNION
                SELECT chunk_id, parent_id, content,
                       COALESCE(v.vector_score, 0) AS vector_score,
                       COALESCE(b.bm25_score, 0) AS bm25_score,
                       COALESCE(v.v_rank, 9999) AS v_rank,
                       COALESCE(b.b_rank, 9999) AS b_rank
                FROM bm25_hits b
                LEFT JOIN vector_hits v USING (chunk_id)
                WHERE v.chunk_id IS NULL
            )
            SELECT
                chunk_id, parent_id, content,
                vector_score, bm25_score,
                (1.0 / (60 + v_rank) + 1.0 / (60 + b_rank)) AS hybrid_score
            FROM combined
            ORDER BY hybrid_score DESC
            LIMIT %s
        """
        params = (
            vector_str, vector_str, vector_str,  # vector CTE
            top_k,
            query_text, query_text, query_text,  # bm25 CTE
            top_k,
            top_k,                                 # final
        )

        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────
    # 备选：纯向量检索
    # ─────────────────────────────────────────────────────────────────

    def vector_search(
        self,
        query_vector: List[float],
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """纯向量语义检索。"""
        vector_str = self._vector_to_str(query_vector)
        sql = """
            SELECT chunk_id, parent_id, content,
                   (1 - COSINE_DISTANCE(embedding, %s)) AS vector_score
            FROM child_chunks
            ORDER BY COSINE_DISTANCE(embedding, %s) ASC
            LIMIT %s
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (vector_str, vector_str, top_k))
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────
    # 备选：纯 BM25 检索
    # ─────────────────────────────────────────────────────────────────

    def bm25_search(
        self,
        query_text: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """纯 BM25 关键词检索。"""
        sql = """
            SELECT chunk_id, parent_id, content,
                   MATCH(content) AGAINST(%s IN NATURAL LANGUAGE MODE) AS bm25_score
            FROM child_chunks
            WHERE MATCH(content) AGAINST(%s IN NATURAL LANGUAGE MODE)
            ORDER BY bm25_score DESC
            LIMIT %s
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (query_text, query_text, top_k))
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────
    # ③ 父块反查
    # ─────────────────────────────────────────────────────────────────

    def get_parent(self, parent_id: str) -> Optional[Dict[str, Any]]:
        """获取单个父块完整文本。"""
        sql = """
            SELECT parent_id, content, source, metadata
            FROM parent_chunks
            WHERE parent_id = %s
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (parent_id,))
                row = cur.fetchone()
        return dict(row) if row else None

    def get_parents_batch(self, parent_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量获取父块。返回 {parent_id: {...}} 字典。"""
        if not parent_ids:
            return {}
        placeholders = ", ".join(["%s"] * len(parent_ids))
        sql = f"""
            SELECT parent_id, content, source, metadata
            FROM parent_chunks
            WHERE parent_id IN ({placeholders})
        """
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, parent_ids)
                rows = cur.fetchall()
        return {row["parent_id"]: dict(row) for row in rows}

    # ─────────────────────────────────────────────────────────────────
    # 文档管理（写入/删除）
    # ─────────────────────────────────────────────────────────────────

    def insert_parent(self, parent_id: str, content: str,
                      source: str = "", metadata: dict = None) -> None:
        """插入父块。"""
        sql = """
            INSERT INTO parent_chunks (parent_id, content, source, metadata)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE content=VALUES(content), source=VALUES(source),
                                    metadata=VALUES(metadata)
        """
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (parent_id, content, source, meta_json))

    def insert_children(self, rows: List[Dict[str, Any]]) -> int:
        """批量插入子块。

        每行需包含: chunk_id, parent_id, content, embedding (List[float])
        """
        if not rows:
            return 0
        sql = """
            INSERT INTO child_chunks (chunk_id, parent_id, content, embedding)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                content=VALUES(content), embedding=VALUES(embedding)
        """
        params = [
            (r["chunk_id"], r["parent_id"], r["content"],
             self._vector_to_str(r["embedding"]))
            for r in rows
        ]
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, params)
        return len(params)

    def delete_document(self, parent_id: str) -> int:
        """删除文档（父块 + 所有子块），返回删除的子块数。"""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM child_chunks WHERE parent_id = %s", (parent_id,))
                deleted = cur.rowcount
                cur.execute("DELETE FROM parent_chunks WHERE parent_id = %s", (parent_id,))
        return deleted

    # ─────────────────────────────────────────────────────────────────
    # 健康检查
    # ─────────────────────────────────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """检查 OceanBase 连接和表状态。"""
        result = {"connected": False, "tables": {}, "error": None}
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    result["connected"] = True
                    for table in ("parent_chunks", "child_chunks"):
                        cur.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
                        row = cur.fetchone()
                        result["tables"][table] = row["cnt"]
        except Exception as e:
            result["error"] = str(e)
        return result

    # ── 工具函数 ─────────────────────────────────────────────────────

    @staticmethod
    def _vector_to_str(vec: List[float]) -> str:
        """将 Python 列表转为 OceanBase VECTOR 字面量 '[0.1,0.2,...]'。"""
        return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"


# ── 单例 ─────────────────────────────────────────────────────────────

_store: Optional[ChunkStore] = None


def get_chunk_store() -> ChunkStore:
    global _store
    if _store is None:
        _store = ChunkStore()
    return _store
