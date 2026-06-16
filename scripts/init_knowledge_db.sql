-- =============================================================================
-- Hermes-Lite 知识库 — OceanBase 建表脚本
-- 适用版本：OceanBase V4.4.1+（MySQL 模式）
-- =============================================================================
--
-- 表结构：
--   parent_chunks  — 父块（完整文档片段，用于 LLM Context）
--   child_chunks   — 子块（带 VECTOR + FULLTEXT 索引，用于检索）
--
-- 索引：
--   VECTOR INDEX   — HNSW 向量索引（cosine 距离）
--   FULLTEXT INDEX — ngram 全文索引（中文 BM25 检索）
--
-- 使用方法：
--   mysql -h <host> -P 2881 -u root -p hermes_lite < scripts/init_knowledge_db.sql
-- =============================================================================

-- ── 创建数据库（如不存在）────────────────────────────────────────────

CREATE DATABASE IF NOT EXISTS hermes_lite
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE hermes_lite;

-- ── 父块表 ──────────────────────────────────────────────────────────
-- 存储文档的完整片段，作为 LLM Context 返回给 Agent。

CREATE TABLE IF NOT EXISTS parent_chunks (
    parent_id   VARCHAR(128)    NOT NULL            COMMENT '父块唯一ID（文档路径/章节编号等）',
    content     MEDIUMTEXT      NOT NULL            COMMENT '父块完整文本',
    source      VARCHAR(512)    NOT NULL DEFAULT '' COMMENT '来源标识（文件名/URL/文档编号）',
    metadata    JSON                                COMMENT '元数据（标题、作者、日期等）',
    created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (parent_id),
    INDEX idx_source (source(128))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='知识库父块 — 完整文档片段';

-- ── 子块表 ──────────────────────────────────────────────────────────
-- 存储文档的细分片段，用于检索。
-- 每个子块通过 parent_id 关联到一个父块。

CREATE TABLE IF NOT EXISTS child_chunks (
    chunk_id    VARCHAR(128)    NOT NULL            COMMENT '子块唯一ID',
    parent_id   VARCHAR(128)    NOT NULL            COMMENT '所属父块ID',
    content     TEXT            NOT NULL            COMMENT '子块文本内容',
    embedding   VECTOR(1536)                       COMMENT 'Embedding 向量（1536维）',
    chunk_idx   INT             NOT NULL DEFAULT 0  COMMENT '子块在父块中的序号',
    created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (chunk_id),
    INDEX idx_parent (parent_id),
    -- 全文索引：ngram 解析器支持中文 BM25 检索
    FULLTEXT INDEX ft_content (content) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='知识库子块 — 检索单元';

-- ── 向量索引 ────────────────────────────────────────────────────────
-- HNSW 向量索引，余弦距离，用于高速近似最近邻检索。
-- OceanBase V4.4.1+ 原生支持。

CREATE VECTOR INDEX IF NOT EXISTS idx_embedding_hnsw
    ON child_chunks (embedding)
    WITH (distance_metric = 'cosine', type = 'hnsw', M = 16, ef_construction = 200);

-- ── 文档元信息表（可选，用于文档管理）────────────────────────────────

CREATE TABLE IF NOT EXISTS documents (
    doc_id      VARCHAR(256)    NOT NULL            COMMENT '文档唯一标识',
    title       VARCHAR(512)    NOT NULL DEFAULT '' COMMENT '文档标题',
    file_path   VARCHAR(1024)   NOT NULL DEFAULT '' COMMENT '原始文件路径',
    file_type   VARCHAR(32)     NOT NULL DEFAULT '' COMMENT '文件类型（pdf/docx/md/txt）',
    chunk_count INT             NOT NULL DEFAULT 0  COMMENT '分块总数',
    total_chars BIGINT          NOT NULL DEFAULT 0  COMMENT '总字符数',
    metadata    JSON                                COMMENT '额外元数据',
    created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (doc_id),
    INDEX idx_doc_title (title(128))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='文档元信息';
