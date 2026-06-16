-- =============================================================================
-- Hermes-Lite 招标智能匹配系统 — OceanBase 结构化表设计
-- 适用版本：OceanBase V4.4.1+（MySQL 模式）
-- =============================================================================
--
-- 核心表：
--   tenders         — 招标项目（结构化字段 + 语义向量）
--   companies       — 企业信息（资质 + 能力 + 历史业绩）
--   company_qualifications — 企业资质证书明细
--   company_performance   — 企业历史中标业绩
--   tender_matches   — 招标匹配结果缓存（企业×招标 评分）
--
-- 知识库表（已有）：
--   parent_chunks / child_chunks — 文档级 RAG（补充非结构化知识）
-- =============================================================================

USE hermes_lite;

-- ── 招标项目表 ──────────────────────────────────────────────────────
-- 存储结构化招标公告信息，支持多维度筛选 + 语义检索。

CREATE TABLE IF NOT EXISTS tenders (
    tender_id       VARCHAR(64)     NOT NULL            COMMENT '招标项目ID',
    project_code    VARCHAR(128)    NOT NULL DEFAULT '' COMMENT '项目编号',
    title           VARCHAR(512)    NOT NULL            COMMENT '招标项目名称',
    buyer           VARCHAR(256)    NOT NULL DEFAULT '' COMMENT '采购方/招标人',
    agency          VARCHAR(256)    NOT NULL DEFAULT '' COMMENT '代理机构',

    -- 分类维度
    industry        VARCHAR(128)    NOT NULL DEFAULT '' COMMENT '行业分类（IT/医疗/建筑/教育等）',
    region          VARCHAR(128)    NOT NULL DEFAULT '' COMMENT '项目所在地区',
    tender_type     VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '招标类型（公开招标/邀请招标/竞争性谈判/询价/单一来源）',
    project_type    VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '项目类型（货物/工程/服务）',

    -- 预算与时间
    budget_min      DECIMAL(18,2)   NOT NULL DEFAULT 0  COMMENT '预算下限（万元）',
    budget_max      DECIMAL(18,2)   NOT NULL DEFAULT 0  COMMENT '预算上限（万元）',
    publish_date    DATE                                COMMENT '发布日期',
    deadline        DATE                                COMMENT '投标截止日期',
    open_date       DATE                                COMMENT '开标日期',

    -- 资质与技术要求（结构化 JSON）
    requirements    JSON                                COMMENT '技术要求（结构化）',
    eval_criteria   JSON                                COMMENT '评标办法与评分标准',
    qualifications  JSON                                COMMENT '资质要求列表（ISO/等级/行业许可等）',

    -- 全文内容（非结构化补充）
    content         MEDIUMTEXT                          COMMENT '招标公告完整原文',
    content_embedding VECTOR(1536)                       COMMENT '内容语义向量',

    -- 状态
    status          VARCHAR(32)     NOT NULL DEFAULT 'active'
                                    COMMENT '状态（active/closed/awarded/cancelled）',
    winner          VARCHAR(256)    NOT NULL DEFAULT '' COMMENT '中标单位',
    win_amount      DECIMAL(18,2)   NOT NULL DEFAULT 0  COMMENT '中标金额（万元）',

    -- 元数据
    source_url      VARCHAR(1024)   NOT NULL DEFAULT '' COMMENT '来源URL',
    metadata        JSON                                COMMENT '扩展字段',
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (tender_id),
    INDEX idx_industry (industry),
    INDEX idx_region (region),
    INDEX idx_status (status),
    INDEX idx_deadline (deadline),
    INDEX idx_publish_date (publish_date),
    INDEX idx_budget (budget_min, budget_max),
    FULLTEXT INDEX ft_title_content (title, content) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='招标项目表';

CREATE VECTOR INDEX IF NOT EXISTS idx_tender_embedding
    ON tenders (content_embedding)
    WITH (distance_metric = 'cosine', type = 'hnsw', M = 16, ef_construction = 200);


-- ── 企业信息表 ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS companies (
    company_id      VARCHAR(64)     NOT NULL            COMMENT '企业ID',
    name            VARCHAR(256)    NOT NULL            COMMENT '企业名称',
    unified_code    VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '统一社会信用代码',
    legal_person    VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '法定代表人',

    -- 基本信息
    industry        VARCHAR(128)    NOT NULL DEFAULT '' COMMENT '主营行业',
    region          VARCHAR(128)    NOT NULL DEFAULT '' COMMENT '注册地区',
    address         VARCHAR(512)    NOT NULL DEFAULT '' COMMENT '详细地址',
    registered_capital DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '注册资本（万元）',
    employee_count  INT             NOT NULL DEFAULT 0  COMMENT '员工人数',
    revenue         DECIMAL(18,2)   NOT NULL DEFAULT 0  COMMENT '年营收（万元）',
    established_year INT            NOT NULL DEFAULT 0  COMMENT '成立年份',

    -- 能力画像（结构化 JSON）
    capabilities   JSON                                COMMENT '技术能力标签列表',
    equipment      JSON                                COMMENT '关键设备/资源',
    team_info      JSON                                COMMENT '核心团队信息',

    -- 资质汇总
    qualification_level VARCHAR(32) NOT NULL DEFAULT '' COMMENT '最高资质等级',
    certifications  JSON                                COMMENT '认证列表（ISO9001等）',

    -- 业绩统计
    total_bids      INT             NOT NULL DEFAULT 0  COMMENT '累计投标数',
    total_wins      INT             NOT NULL DEFAULT 0  COMMENT '累计中标数',
    win_rate        DECIMAL(5,2)    NOT NULL DEFAULT 0  COMMENT '中标率（%）',
    total_win_amount DECIMAL(18,2)  NOT NULL DEFAULT 0  COMMENT '累计中标金额（万元）',

    -- 企业画像向量
    profile_text    TEXT                                COMMENT '企业综合描述文本（用于 Embedding）',
    profile_embedding VECTOR(1536)                       COMMENT '企业画像语义向量',

    -- 状态
    status          VARCHAR(32)     NOT NULL DEFAULT 'active'
                                    COMMENT '状态（active/blacklisted/inactive）',
    metadata        JSON                                COMMENT '扩展字段',
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (company_id),
    UNIQUE INDEX idx_unified_code (unified_code),
    INDEX idx_industry (industry),
    INDEX idx_region (region),
    INDEX idx_status (status),
    FULLTEXT INDEX ft_company_name (name) WITH PARSER ngram
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='企业信息表';

CREATE VECTOR INDEX IF NOT EXISTS idx_company_embedding
    ON companies (profile_embedding)
    WITH (distance_metric = 'cosine', type = 'hnsw', M = 16, ef_construction = 200);


-- ── 企业资质明细表 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS company_qualifications (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    company_id      VARCHAR(64)     NOT NULL            COMMENT '企业ID',
    qual_type       VARCHAR(64)     NOT NULL            COMMENT '资质类型（施工总承包/专业承包/设计/监理等）',
    qual_name       VARCHAR(256)    NOT NULL            COMMENT '资质名称',
    qual_level      VARCHAR(32)     NOT NULL DEFAULT '' COMMENT '资质等级（特级/一级/二级/三级/甲级/乙级）',
    qual_code       VARCHAR(128)    NOT NULL DEFAULT '' COMMENT '资质证书编号',
    issue_date      DATE                                COMMENT '发证日期',
    expire_date     DATE                                COMMENT '有效期至',
    issue_authority VARCHAR(256)    NOT NULL DEFAULT '' COMMENT '发证机关',
    status          VARCHAR(32)     NOT NULL DEFAULT 'valid' COMMENT '状态（valid/expired/revoked）',
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_company (company_id),
    INDEX idx_qual_type (qual_type),
    INDEX idx_qual_level (qual_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='企业资质证书明细';


-- ── 企业历史业绩表 ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS company_performance (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    company_id      VARCHAR(64)     NOT NULL            COMMENT '企业ID',
    project_name    VARCHAR(512)    NOT NULL            COMMENT '项目名称',
    project_type    VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '项目类型（货物/工程/服务）',
    industry        VARCHAR(128)    NOT NULL DEFAULT '' COMMENT '所属行业',
    region          VARCHAR(128)    NOT NULL DEFAULT '' COMMENT '项目地区',
    contract_amount DECIMAL(18,2)   NOT NULL DEFAULT 0  COMMENT '合同金额（万元）',
    award_date      DATE                                COMMENT '中标/签约日期',
    completion_date DATE                                COMMENT '竣工/完成日期',
    buyer           VARCHAR(256)    NOT NULL DEFAULT '' COMMENT '采购方',
    tender_id       VARCHAR(64)     NOT NULL DEFAULT '' COMMENT '关联招标ID（如有）',
    description     TEXT                                COMMENT '项目描述',
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_company (company_id),
    INDEX idx_industry (industry),
    INDEX idx_award_date (award_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='企业历史中标业绩';


-- ── 匹配结果缓存表 ─────────────────────────────────────────────────
-- 企业×招标 的匹配评分，支持增量更新和历史追踪。

CREATE TABLE IF NOT EXISTS tender_matches (
    id              BIGINT          NOT NULL AUTO_INCREMENT,
    tender_id       VARCHAR(64)     NOT NULL            COMMENT '招标ID',
    company_id      VARCHAR(64)     NOT NULL            COMMENT '企业ID',

    -- 分维度评分（0-100）
    industry_score  DECIMAL(5,2)    NOT NULL DEFAULT 0  COMMENT '行业匹配度',
    region_score    DECIMAL(5,2)    NOT NULL DEFAULT 0  COMMENT '地域匹配度',
    qual_score      DECIMAL(5,2)    NOT NULL DEFAULT 0  COMMENT '资质匹配度',
    budget_score    DECIMAL(5,2)    NOT NULL DEFAULT 0  COMMENT '预算匹配度',
    capability_score DECIMAL(5,2)   NOT NULL DEFAULT 0  COMMENT '能力匹配度',
    experience_score DECIMAL(5,2)   NOT NULL DEFAULT 0  COMMENT '业绩匹配度',
    semantic_score  DECIMAL(5,2)    NOT NULL DEFAULT 0  COMMENT '语义相似度',

    -- 综合评分
    total_score     DECIMAL(5,2)    NOT NULL DEFAULT 0  COMMENT '综合匹配分（加权）',
    win_probability DECIMAL(5,2)    NOT NULL DEFAULT 0  COMMENT '预测中标概率（%）',
    recommendation  VARCHAR(32)     NOT NULL DEFAULT '' COMMENT '推荐等级（strong/medium/weak/skip）',

    -- 匹配分析
    match_reasons   JSON                                COMMENT '匹配优势列表',
    risk_factors    JSON                                COMMENT '风险因素列表',
    suggestions     JSON                                COMMENT '投标准备建议',

    -- 缓存管理
    computed_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP                           COMMENT '缓存过期时间',

    PRIMARY KEY (id),
    UNIQUE INDEX idx_tender_company (tender_id, company_id),
    INDEX idx_company (company_id),
    INDEX idx_total_score (total_score DESC),
    INDEX idx_recommendation (recommendation)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='招标-企业匹配结果缓存';
