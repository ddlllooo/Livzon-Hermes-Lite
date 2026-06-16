"""招标智能匹配服务 — 核心业务逻辑层。

提供：
  - 招标项目搜索（结构化筛选 + 语义检索）
  - 企业-招标匹配评分（六维度加权）
  - 中标概率预测
  - 智能推荐（针对企业推荐最优招标项目）
  - 深度分析（单个招标项目的综合分析）
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── 匹配评分权重配置 ────────────────────────────────────────────────

DEFAULT_WEIGHTS = {
    "industry":    0.20,   # 行业匹配
    "region":      0.10,   # 地域匹配
    "qualification": 0.25, # 资质匹配（硬性门槛）
    "budget":      0.10,   # 预算匹配
    "capability":  0.20,   # 技术能力匹配
    "experience":  0.15,   # 历史业绩匹配
}


# ── 数据结构 ─────────────────────────────────────────────────────────

@dataclass
class TenderInfo:
    tender_id: str
    title: str
    buyer: str
    industry: str
    region: str
    budget_min: float
    budget_max: float
    deadline: str
    status: str
    tender_type: str
    project_type: str
    qualifications: list
    requirements: dict
    content: str
    source_url: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class CompanyInfo:
    company_id: str
    name: str
    industry: str
    region: str
    registered_capital: float
    capabilities: list
    qualifications: list
    total_wins: int
    win_rate: float
    total_win_amount: float
    established_year: int
    employee_count: int
    profile_text: str = ""


@dataclass
class MatchResult:
    tender_id: str
    tender_title: str
    company_id: str
    company_name: str
    # 分维度评分 (0-100)
    industry_score: float = 0
    region_score: float = 0
    qual_score: float = 0
    budget_score: float = 0
    capability_score: float = 0
    experience_score: float = 0
    semantic_score: float = 0
    # 综合
    total_score: float = 0
    win_probability: float = 0
    recommendation: str = ""  # strong/medium/weak/skip
    match_reasons: list = field(default_factory=list)
    risk_factors: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)


@dataclass
class Recommendation:
    """针对一家企业的推荐结果。"""
    company_id: str
    company_name: str
    recommendations: List[MatchResult] = field(default_factory=list)
    summary: str = ""


# ── TenderService ────────────────────────────────────────────────────

class TenderService:
    """招标智能匹配业务逻辑。

    依赖 ChunkStore 的连接池执行 SQL，不自己建连接。
    """

    def __init__(self, chunk_store, embedder=None, weights: dict = None):
        self.store = chunk_store
        self.embedder = embedder
        self.weights = weights or DEFAULT_WEIGHTS

    # ================================================================
    # ① 招标搜索（结构化筛选 + 语义检索）
    # ================================================================

    def search_tenders(
        self,
        keyword: str = "",
        industry: str = "",
        region: str = "",
        budget_min: float = 0,
        budget_max: float = 0,
        status: str = "active",
        tender_type: str = "",
        deadline_before: str = "",
        deadline_after: str = "",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """多条件筛选招标项目。

        所有参数可选，支持组合筛选。
        """
        conditions = []
        params = []

        if status:
            conditions.append("t.status = %s")
            params.append(status)
        if industry:
            conditions.append("t.industry LIKE %s")
            params.append(f"%{industry}%")
        if region:
            conditions.append("t.region LIKE %s")
            params.append(f"%{region}%")
        if budget_min > 0:
            conditions.append("t.budget_max >= %s")
            params.append(budget_min)
        if budget_max > 0:
            conditions.append("t.budget_min <= %s")
            params.append(budget_max)
        if tender_type:
            conditions.append("t.tender_type LIKE %s")
            params.append(f"%{tender_type}%")
        if deadline_before:
            conditions.append("t.deadline <= %s")
            params.append(deadline_before)
        if deadline_after:
            conditions.append("t.deadline >= %s")
            params.append(deadline_after)
        if keyword:
            conditions.append(
                "MATCH(t.title, t.content) AGAINST(%s IN NATURAL LANGUAGE MODE)"
            )
            params.append(keyword)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        sql = f"""
            SELECT t.tender_id, t.title, t.buyer, t.industry, t.region,
                   t.budget_min, t.budget_max, t.deadline, t.status,
                   t.tender_type, t.project_type, t.qualifications,
                   t.requirements, t.publish_date, t.source_url,
                   LEFT(t.content, 500) AS content_preview
            FROM tenders t
            WHERE {where}
            ORDER BY t.publish_date DESC, t.deadline ASC
            LIMIT %s
        """
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return [self._row_to_dict(r) for r in rows]

    def semantic_search_tenders(
        self, query: str, top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """语义检索招标项目（向量相似度）。"""
        if not self.embedder:
            return self.search_tenders(keyword=query, limit=top_k)

        vector = self.embedder.embed(query)
        vector_str = self.store._vector_to_str(vector)

        sql = """
            SELECT tender_id, title, buyer, industry, region,
                   budget_min, budget_max, deadline, status,
                   tender_type, project_type, qualifications,
                   LEFT(content, 500) AS content_preview,
                   (1 - COSINE_DISTANCE(content_embedding, %s)) AS relevance
            FROM tenders
            WHERE status = 'active'
            ORDER BY COSINE_DISTANCE(content_embedding, %s) ASC
            LIMIT %s
        """
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (vector_str, vector_str, top_k))
                rows = cur.fetchall()

        return [self._row_to_dict(r) for r in rows]

    # ================================================================
    # ② 企业-招标匹配评分（六维度加权）
    # ================================================================

    def match(
        self, company_id: str, tender_id: str
    ) -> MatchResult:
        """单个企业 vs 单个招标 的六维度匹配评分。"""
        company = self._get_company(company_id)
        tender = self._get_tender(tender_id)
        if not company or not tender:
            raise ValueError(f"企业或招标不存在: company={company_id}, tender={tender_id}")

        result = MatchResult(
            tender_id=tender_id,
            tender_title=tender["title"],
            company_id=company_id,
            company_name=company["name"],
        )

        # 分维度评分
        result.industry_score = self._score_industry(company, tender)
        result.region_score = self._score_region(company, tender)
        result.qual_score = self._score_qualification(company, tender)
        result.budget_score = self._score_budget(company, tender)
        result.capability_score = self._score_capability(company, tender)
        result.experience_score = self._score_experience(company, tender)

        # 语义相似度（可选）
        if self.embedder:
            result.semantic_score = self._score_semantic(company, tender)

        # 加权总分
        w = self.weights
        result.total_score = round(
            result.industry_score * w["industry"]
            + result.region_score * w["region"]
            + result.qual_score * w["qualification"]
            + result.budget_score * w["budget"]
            + result.capability_score * w["capability"]
            + result.experience_score * w["experience"],
            2,
        )

        # 中标概率预测
        result.win_probability = self._predict_win_probability(company, tender, result)

        # 推荐等级
        result.recommendation = self._classify_recommendation(result)

        # 匹配分析
        result.match_reasons = self._analyze_strengths(result)
        result.risk_factors = self._analyze_risks(company, tender, result)
        result.suggestions = self._generate_suggestions(company, tender, result)

        return result

    def match_batch(
        self, company_id: str, tender_ids: List[str]
    ) -> List[MatchResult]:
        """一家企业 vs 多个招标，按总分排序。"""
        results = []
        for tid in tender_ids:
            try:
                results.append(self.match(company_id, tid))
            except Exception as e:
                logger.warning("匹配失败 company=%s tender=%s: %s", company_id, tid, e)
        results.sort(key=lambda r: r.total_score, reverse=True)
        return results

    # ================================================================
    # ③ 智能推荐（针对企业推荐最优招标）
    # ================================================================

    def recommend_for_company(
        self,
        company_id: str,
        top_k: int = 5,
        min_score: float = 40.0,
        industry: str = "",
        region: str = "",
    ) -> Recommendation:
        """为一家企业推荐最匹配的活跃招标项目。

        两阶段：
          1) 从活跃招标中用行业/地域/资质预筛候选集（~50个）
          2) 逐个六维度评分，返回 Top-K
        """
        company = self._get_company(company_id)
        if not company:
            raise ValueError(f"企业不存在: {company_id}")

        # 候选预筛
        candidates = self._prescreen_candidates(
            company, industry=industry, region=region, limit=50
        )
        if not candidates:
            return Recommendation(
                company_id=company_id,
                company_name=company["name"],
                summary="当前没有符合条件的活跃招标项目",
            )

        # 逐个匹配评分
        match_results = []
        for tender in candidates:
            try:
                result = self._match_from_data(company, tender)
                if result.total_score >= min_score:
                    match_results.append(result)
            except Exception as e:
                logger.debug("推荐评分跳过 %s: %s", tender.get("tender_id"), e)

        # 排序取 Top-K
        match_results.sort(key=lambda r: r.total_score, reverse=True)
        top_results = match_results[:top_k]

        # 生成推荐摘要
        summary = self._generate_recommendation_summary(company, top_results)

        return Recommendation(
            company_id=company_id,
            company_name=company["name"],
            recommendations=top_results,
            summary=summary,
        )

    # ================================================================
    # ④ 招标深度分析
    # ================================================================

    def analyze_tender(self, tender_id: str) -> Dict[str, Any]:
        """分析单个招标项目，返回综合信息。"""
        tender = self._get_tender(tender_id)
        if not tender:
            raise ValueError(f"招标不存在: {tender_id}")

        # 查找相似招标
        similar = self._find_similar_tenders(tender, limit=5)

        # 查找已匹配的企业
        matched_companies = self._get_matched_companies(tender_id)

        # 分析资质门槛
        qual_analysis = self._analyze_qualification_barriers(tender)

        # 竞争度评估
        competition = self._assess_competition(tender, matched_companies)

        return {
            "tender": self._row_to_dict(tender),
            "similar_tenders": [self._row_to_dict(s) for s in similar],
            "matched_companies": matched_companies,
            "qualification_barriers": qual_analysis,
            "competition_assessment": competition,
            "suggestions": self._generate_tender_analysis_suggestions(
                tender, competition, qual_analysis
            ),
        }

    # ================================================================
    # ⑤ 数据管理
    # ================================================================

    def add_tender(self, data: dict) -> str:
        """添加招标项目。返回 tender_id。"""
        tender_id = data.get("tender_id") or self._gen_id(data["title"])

        # 生成内容 Embedding
        content = data.get("content", "")
        embedding = None
        if self.embedder and content:
            embedding = self.embedder.embed(content)

        sql = """
            INSERT INTO tenders (
                tender_id, project_code, title, buyer, agency,
                industry, region, tender_type, project_type,
                budget_min, budget_max, publish_date, deadline, open_date,
                requirements, eval_criteria, qualifications,
                content, content_embedding, status, source_url, metadata
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                title=VALUES(title), buyer=VALUES(buyer),
                industry=VALUES(industry), region=VALUES(region),
                budget_min=VALUES(budget_min), budget_max=VALUES(budget_max),
                deadline=VALUES(deadline), status=VALUES(status),
                content=VALUES(content), content_embedding=VALUES(content_embedding),
                requirements=VALUES(requirements), qualifications=VALUES(qualifications)
        """
        params = (
            tender_id,
            data.get("project_code", ""),
            data["title"],
            data.get("buyer", ""),
            data.get("agency", ""),
            data.get("industry", ""),
            data.get("region", ""),
            data.get("tender_type", ""),
            data.get("project_type", ""),
            data.get("budget_min", 0),
            data.get("budget_max", 0),
            data.get("publish_date"),
            data.get("deadline"),
            data.get("open_date"),
            json.dumps(data.get("requirements", {}), ensure_ascii=False),
            json.dumps(data.get("eval_criteria", {}), ensure_ascii=False),
            json.dumps(data.get("qualifications", []), ensure_ascii=False),
            content,
            self.store._vector_to_str(embedding) if embedding else None,
            data.get("status", "active"),
            data.get("source_url", ""),
            json.dumps(data.get("metadata", {}), ensure_ascii=False),
        )

        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

        logger.info("招标写入: %s — %s", tender_id, data["title"][:60])
        return tender_id

    def add_company(self, data: dict) -> str:
        """添加企业信息。返回 company_id。"""
        company_id = data.get("company_id") or self._gen_id(data["name"])

        # 生成企业画像 Embedding
        profile_text = data.get("profile_text") or self._build_profile_text(data)
        embedding = None
        if self.embedder and profile_text:
            embedding = self.embedder.embed(profile_text)

        sql = """
            INSERT INTO companies (
                company_id, name, unified_code, legal_person,
                industry, region, address, registered_capital,
                employee_count, revenue, established_year,
                capabilities, equipment, team_info,
                qualification_level, certifications,
                total_bids, total_wins, win_rate, total_win_amount,
                profile_text, profile_embedding, status, metadata
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                name=VALUES(name), industry=VALUES(industry),
                region=VALUES(region), registered_capital=VALUES(registered_capital),
                capabilities=VALUES(capabilities), qualifications=VALUES(qualifications),
                total_wins=VALUES(total_wins), win_rate=VALUES(win_rate),
                profile_text=VALUES(profile_text), profile_embedding=VALUES(profile_embedding)
        """
        params = (
            company_id,
            data["name"],
            data.get("unified_code", ""),
            data.get("legal_person", ""),
            data.get("industry", ""),
            data.get("region", ""),
            data.get("address", ""),
            data.get("registered_capital", 0),
            data.get("employee_count", 0),
            data.get("revenue", 0),
            data.get("established_year", 0),
            json.dumps(data.get("capabilities", []), ensure_ascii=False),
            json.dumps(data.get("equipment", []), ensure_ascii=False),
            json.dumps(data.get("team_info", {}), ensure_ascii=False),
            data.get("qualification_level", ""),
            json.dumps(data.get("certifications", []), ensure_ascii=False),
            data.get("total_bids", 0),
            data.get("total_wins", 0),
            data.get("win_rate", 0),
            data.get("total_win_amount", 0),
            profile_text,
            self.store._vector_to_str(embedding) if embedding else None,
            data.get("status", "active"),
            json.dumps(data.get("metadata", {}), ensure_ascii=False),
        )

        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

        logger.info("企业写入: %s — %s", company_id, data["name"])
        return company_id

    def add_qualification(self, data: dict) -> None:
        """添加企业资质。"""
        sql = """
            INSERT INTO company_qualifications
                (company_id, qual_type, qual_name, qual_level,
                 qual_code, issue_date, expire_date, issue_authority)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    data["company_id"], data["qual_type"], data["qual_name"],
                    data.get("qual_level", ""), data.get("qual_code", ""),
                    data.get("issue_date"), data.get("expire_date"),
                    data.get("issue_authority", ""),
                ))

    def add_performance(self, data: dict) -> None:
        """添加企业历史业绩。"""
        sql = """
            INSERT INTO company_performance
                (company_id, project_name, project_type, industry, region,
                 contract_amount, award_date, completion_date, buyer,
                 tender_id, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    data["company_id"], data["project_name"],
                    data.get("project_type", ""), data.get("industry", ""),
                    data.get("region", ""), data.get("contract_amount", 0),
                    data.get("award_date"), data.get("completion_date"),
                    data.get("buyer", ""), data.get("tender_id", ""),
                    data.get("description", ""),
                ))

    def get_stats(self) -> Dict[str, Any]:
        """知识库统计。"""
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                stats = {}
                for table in ("tenders", "companies",
                              "company_qualifications", "company_performance",
                              "tender_matches"):
                    cur.execute(f"SELECT COUNT(*) AS cnt FROM {table}")
                    stats[table] = cur.fetchone()["cnt"]
                # 活跃招标数
                cur.execute("SELECT COUNT(*) AS cnt FROM tenders WHERE status='active'")
                stats["active_tenders"] = cur.fetchone()["cnt"]
                # 行业分布
                cur.execute("""
                    SELECT industry, COUNT(*) AS cnt
                    FROM tenders WHERE status='active'
                    GROUP BY industry ORDER BY cnt DESC LIMIT 10
                """)
                stats["top_industries"] = [dict(r) for r in cur.fetchall()]
        return stats

    # ================================================================
    # 评分算法（内部）
    # ================================================================

    def _score_industry(self, company: dict, tender: dict) -> float:
        """行业匹配评分。"""
        c_ind = (company.get("industry") or "").lower()
        t_ind = (tender.get("industry") or "").lower()
        if not t_ind:
            return 50.0  # 招标未指定行业，中性分
        if c_ind == t_ind:
            return 100.0
        # 检查企业能力中是否覆盖该行业
        caps = company.get("capabilities") or []
        if isinstance(caps, str):
            try:
                caps = json.loads(caps)
            except (json.JSONDecodeError, TypeError):
                caps = []
        caps_lower = [str(c).lower() for c in caps]
        if any(t_ind in c for c in caps_lower):
            return 80.0
        return 20.0

    def _score_region(self, company: dict, tender: dict) -> float:
        """地域匹配评分。"""
        c_reg = (company.get("region") or "").lower()
        t_reg = (tender.get("region") or "").lower()
        if not t_reg:
            return 70.0
        # 省级匹配
        c_prov = c_reg[:2] if len(c_reg) >= 2 else c_reg
        t_prov = t_reg[:2] if len(t_reg) >= 2 else t_reg
        if c_reg == t_reg:
            return 100.0
        if c_prov == t_prov:
            return 75.0
        return 30.0

    def _score_qualification(self, company: dict, tender: dict) -> float:
        """资质匹配评分。硬性门槛，不满足直接大幅降分。"""
        quals_required = tender.get("qualifications") or []
        if isinstance(quals_required, str):
            try:
                quals_required = json.loads(quals_required)
            except (json.JSONDecodeError, TypeError):
                quals_required = []
        if not quals_required:
            return 80.0  # 无资质要求

        # 从 company_qualifications 表查询企业实际资质
        company_quals = self._get_company_qualifications(
            company.get("company_id", "")
        )
        qual_names = {q["qual_name"].lower() for q in company_quals}
        qual_types = {q["qual_type"].lower() for q in company_quals}

        matched = 0
        for req in quals_required:
            req_str = str(req).lower()
            if any(req_str in qn or qn in req_str for qn in qual_names):
                matched += 1
            elif any(req_str in qt or qt in req_str for qt in qual_types):
                matched += 0.8

        if not quals_required:
            return 80.0
        ratio = matched / len(quals_required)
        if ratio >= 1.0:
            return 100.0
        elif ratio >= 0.7:
            return 70.0
        elif ratio >= 0.4:
            return 40.0
        else:
            return 10.0

    def _score_budget(self, company: dict, tender: dict) -> float:
        """预算匹配评分。企业营收规模与项目预算的匹配度。"""
        revenue = float(company.get("revenue") or 0)
        bmin = float(tender.get("budget_min") or 0)
        bmax = float(tender.get("budget_max") or 0)
        budget = bmax if bmax > 0 else bmin

        if budget <= 0:
            return 60.0  # 未知预算

        # 企业营收是项目预算的 3~20 倍为最佳
        if revenue <= 0:
            return 40.0

        ratio = revenue / budget
        if 5 <= ratio <= 30:
            return 100.0
        elif 3 <= ratio < 5 or 30 < ratio <= 50:
            return 80.0
        elif 1 <= ratio < 3:
            return 60.0
        elif ratio > 50:
            return 50.0  # 大材小用
        else:
            return 20.0  # 预算超出企业能力

    def _score_capability(self, company: dict, tender: dict) -> float:
        """技术能力匹配评分。"""
        reqs = tender.get("requirements") or {}
        if isinstance(reqs, str):
            try:
                reqs = json.loads(reqs)
            except (json.JSONDecodeError, TypeError):
                reqs = {}
        if not reqs:
            return 60.0

        caps = company.get("capabilities") or []
        if isinstance(caps, str):
            try:
                caps = json.loads(caps)
            except (json.JSONDecodeError, TypeError):
                caps = []
        caps_lower = " ".join(str(c) for c in caps).lower()

        # 从 requirements 中提取关键词
        req_keywords = []
        if isinstance(reqs, dict):
            for v in reqs.values():
                if isinstance(v, str):
                    req_keywords.append(v.lower())
                elif isinstance(v, list):
                    req_keywords.extend(str(item).lower() for item in v)
        elif isinstance(reqs, list):
            req_keywords = [str(r).lower() for r in reqs]
        else:
            req_keywords = [str(reqs).lower()]

        if not req_keywords:
            return 60.0

        hits = sum(1 for kw in req_keywords if kw in caps_lower)
        ratio = hits / len(req_keywords) if req_keywords else 0
        return min(100, 30 + ratio * 70)

    def _score_experience(self, company: dict, tender: dict) -> float:
        """历史业绩匹配评分。"""
        cid = company.get("company_id", "")
        t_ind = (tender.get("industry") or "").lower()
        t_type = (tender.get("project_type") or "").lower()

        # 查询企业相关业绩
        perf = self._get_company_performance(cid, industry=t_ind, limit=10)

        if not perf:
            # 无业绩记录，根据中标率给基础分
            wr = float(company.get("win_rate") or 0)
            return min(60, 20 + wr * 0.5)

        # 相关业绩数量 + 金额
        total_amount = sum(float(p.get("contract_amount") or 0) for p in perf)
        count = len(perf)

        score = 40  # 基础分
        if count >= 5:
            score += 30
        elif count >= 3:
            score += 20
        elif count >= 1:
            score += 10

        bmax = float(tender.get("budget_max") or 0)
        if bmax > 0 and total_amount > 0:
            # 有类似金额的业绩
            avg_amount = total_amount / count
            if 0.3 * bmax <= avg_amount <= 3 * bmax:
                score += 20

        # 中标率加成
        wr = float(company.get("win_rate") or 0)
        if wr >= 30:
            score += 10

        return min(100, score)

    def _score_semantic(self, company: dict, tender: dict) -> float:
        """语义相似度评分。"""
        if not self.embedder:
            return 0
        c_text = company.get("profile_text") or ""
        t_text = (tender.get("content") or "")[:1000]
        if not c_text or not t_text:
            return 0
        c_vec = self.embedder.embed(c_text)
        t_vec = self.embedder.embed(t_text)
        # cosine similarity
        dot = sum(a * b for a, b in zip(c_vec, t_vec))
        norm_c = sum(a * a for a in c_vec) ** 0.5
        norm_t = sum(b * b for b in t_vec) ** 0.5
        if norm_c == 0 or norm_t == 0:
            return 0
        return round((dot / (norm_c * norm_t)) * 100, 2)

    def _predict_win_probability(
        self, company: dict, tender: dict, match: MatchResult
    ) -> float:
        """中标概率预测。

        基于综合匹配分 + 历史中标率 + 资质门槛。
        """
        base = match.total_score

        # 历史中标率加成
        wr = float(company.get("win_rate") or 0)
        wr_bonus = min(15, wr * 0.3)

        # 资质门槛惩罚
        qual_penalty = 0
        if match.qual_score < 50:
            qual_penalty = 20  # 资质不达标，大幅降低概率

        prob = base * 0.6 + wr_bonus - qual_penalty
        return round(max(0, min(100, prob)), 1)

    def _classify_recommendation(self, match: MatchResult) -> str:
        """推荐等级分类。"""
        if match.total_score >= 75 and match.qual_score >= 70:
            return "strong"
        elif match.total_score >= 55:
            return "medium"
        elif match.total_score >= 35:
            return "weak"
        else:
            return "skip"

    def _analyze_strengths(self, match: MatchResult) -> List[str]:
        """分析匹配优势。"""
        reasons = []
        if match.industry_score >= 80:
            reasons.append("行业高度匹配")
        if match.region_score >= 80:
            reasons.append("地域优势明显")
        if match.qual_score >= 90:
            reasons.append("资质完全满足要求")
        if match.budget_score >= 80:
            reasons.append("企业规模与项目预算匹配")
        if match.capability_score >= 80:
            reasons.append("技术能力覆盖项目需求")
        if match.experience_score >= 80:
            reasons.append("有丰富的同类项目经验")
        return reasons

    def _analyze_risks(
        self, company: dict, tender: dict, match: MatchResult
    ) -> List[str]:
        """分析风险因素。"""
        risks = []
        if match.qual_score < 50:
            risks.append("⚠ 资质不满足招标硬性要求，可能被废标")
        if match.budget_score < 40:
            risks.append("⚠ 企业规模与项目预算不匹配")
        if match.region_score < 40:
            risks.append("⚠ 异地投标，可能影响评审得分")
        if match.experience_score < 40:
            risks.append("⚠ 缺乏同类项目经验")

        # 时间风险
        deadline = tender.get("deadline")
        if deadline:
            try:
                dl = datetime.strptime(str(deadline), "%Y-%m-%d").date()
                days_left = (dl - date.today()).days
                if days_left <= 7:
                    risks.append(f"⚠ 距投标截止仅 {days_left} 天，准备时间紧张")
            except (ValueError, TypeError):
                pass

        return risks

    def _generate_suggestions(
        self, company: dict, tender: dict, match: MatchResult
    ) -> List[str]:
        """生成投标准备建议。"""
        suggestions = []
        if match.recommendation in ("strong", "medium"):
            suggestions.append("✅ 建议积极准备投标文件")
            if match.qual_score < 100:
                suggestions.append("📋 检查并补齐所需资质证明材料")
            if match.capability_score < 80:
                suggestions.append("🔧 技术方案中突出优势能力，弥补不足项")
            if match.experience_score < 70:
                suggestions.append("📊 准备详细的过往业绩证明和案例")
            suggestions.append("📐 仔细研究评标标准，针对性编制投标方案")
        elif match.recommendation == "weak":
            suggestions.append("🔍 建议进一步评估项目细节后再决定是否投标")
            suggestions.append("🤝 考虑与互补企业联合投标")
        else:
            suggestions.append("⏭ 建议跳过，将精力投入到更匹配的项目")

        return suggestions

    def _generate_recommendation_summary(
        self, company: dict, results: List[MatchResult]
    ) -> str:
        """生成推荐摘要文本。"""
        if not results:
            return "暂无推荐项目"

        strong = [r for r in results if r.recommendation == "strong"]
        medium = [r for r in results if r.recommendation == "medium"]

        parts = [f"为 {company['name']} 推荐 {len(results)} 个项目："]
        if strong:
            parts.append(f"  🟢 强烈推荐 {len(strong)} 个：{'、'.join(r.tender_title[:20] for r in strong)}")
        if medium:
            parts.append(f"  🟡 建议关注 {len(medium)} 个：{'、'.join(r.tender_title[:20] for r in medium)}")

        return "\n".join(parts)

    # ================================================================
    # 内部查询辅助
    # ================================================================

    def _get_company(self, company_id: str) -> Optional[dict]:
        sql = "SELECT * FROM companies WHERE company_id = %s"
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (company_id,))
                row = cur.fetchone()
        return dict(row) if row else None

    def _get_tender(self, tender_id: str) -> Optional[dict]:
        sql = "SELECT * FROM tenders WHERE tender_id = %s"
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tender_id,))
                row = cur.fetchone()
        return dict(row) if row else None

    def _get_company_qualifications(self, company_id: str) -> List[dict]:
        sql = "SELECT * FROM company_qualifications WHERE company_id = %s"
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (company_id,))
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def _get_company_performance(
        self, company_id: str, industry: str = "", limit: int = 10
    ) -> List[dict]:
        conditions = ["company_id = %s"]
        params = [company_id]
        if industry:
            conditions.append("industry LIKE %s")
            params.append(f"%{industry}%")
        params.append(limit)
        sql = f"""
            SELECT * FROM company_performance
            WHERE {' AND '.join(conditions)}
            ORDER BY award_date DESC LIMIT %s
        """
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def _prescreen_candidates(
        self, company: dict, industry: str = "", region: str = "", limit: int = 50
    ) -> List[dict]:
        """预筛候选招标（快速 SQL 过滤）。"""
        conditions = ["status = 'active'"]
        params = []

        if industry:
            conditions.append("industry LIKE %s")
            params.append(f"%{industry}%")
        elif company.get("industry"):
            conditions.append("industry LIKE %s")
            params.append(f"%{company['industry']}%")

        if region:
            conditions.append("region LIKE %s")
            params.append(f"%{region}%")

        # 预算筛选：项目预算不超过企业营收的 50%
        revenue = float(company.get("revenue") or 0)
        if revenue > 0:
            conditions.append("budget_max <= %s")
            params.append(revenue * 0.5)

        # 截止日期筛选
        conditions.append("deadline >= CURDATE()")

        params.append(limit)
        sql = f"""
            SELECT * FROM tenders
            WHERE {' AND '.join(conditions)}
            ORDER BY deadline ASC
            LIMIT %s
        """
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def _find_similar_tenders(self, tender: dict, limit: int = 5) -> list:
        """查找相似招标。"""
        t_ind = tender.get("industry", "")
        t_reg = tender.get("region", "")
        tid = tender.get("tender_id", "")

        conditions = ["tender_id != %s", "status = 'active'"]
        params = [tid]

        if t_ind:
            conditions.append("industry = %s")
            params.append(t_ind)
        if t_reg:
            conditions.append("region = %s")
            params.append(t_reg)

        params.append(limit)
        sql = f"""
            SELECT * FROM tenders
            WHERE {' AND '.join(conditions)}
            ORDER BY publish_date DESC LIMIT %s
        """
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return rows

    def _get_matched_companies(self, tender_id: str) -> List[dict]:
        sql = """
            SELECT m.*, c.name AS company_name
            FROM tender_matches m
            JOIN companies c ON m.company_id = c.company_id
            WHERE m.tender_id = %s
            ORDER BY m.total_score DESC
            LIMIT 10
        """
        with self.store._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tender_id,))
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def _analyze_qualification_barriers(self, tender: dict) -> dict:
        quals = tender.get("qualifications") or []
        if isinstance(quals, str):
            try:
                quals = json.loads(quals)
            except (json.JSONDecodeError, TypeError):
                quals = []
        return {
            "required_qualifications": quals,
            "barrier_level": "high" if len(quals) >= 3 else ("medium" if quals else "low"),
            "description": f"需要 {len(quals)} 项资质" if quals else "无特殊资质要求",
        }

    def _assess_competition(self, tender: dict, matched: list) -> dict:
        return {
            "matched_companies": len(matched),
            "competition_level": (
                "激烈" if len(matched) >= 10 else
                "中等" if len(matched) >= 5 else
                "较低"
            ),
            "top_competitors": [
                {"name": m.get("company_name"), "score": m.get("total_score")}
                for m in matched[:3]
            ],
        }

    def _generate_tender_analysis_suggestions(
        self, tender: dict, competition: dict, qual_analysis: dict
    ) -> list:
        suggestions = []
        if competition["competition_level"] == "激烈":
            suggestions.append("🔥 竞争激烈，需重点打磨技术方案和报价策略")
        if qual_analysis["barrier_level"] == "high":
            suggestions.append("📋 资质门槛较高，提前确认所有资质证书有效期")
        deadline = tender.get("deadline")
        if deadline:
            try:
                dl = datetime.strptime(str(deadline), "%Y-%m-%d").date()
                days = (dl - date.today()).days
                if days > 0:
                    suggestions.append(f"⏰ 距截止日 {days} 天，建议提前 3 天完成投标文件")
            except (ValueError, TypeError):
                pass
        suggestions.append("📖 详细研读招标文件中的评分标准和否决条款")
        return suggestions

    def _match_from_data(self, company: dict, tender: dict) -> MatchResult:
        """从已加载的数据直接评分（避免重复查 DB）。"""
        result = MatchResult(
            tender_id=tender.get("tender_id", ""),
            tender_title=tender.get("title", ""),
            company_id=company.get("company_id", ""),
            company_name=company.get("name", ""),
        )
        result.industry_score = self._score_industry(company, tender)
        result.region_score = self._score_region(company, tender)
        result.qual_score = self._score_qualification(company, tender)
        result.budget_score = self._score_budget(company, tender)
        result.capability_score = self._score_capability(company, tender)
        result.experience_score = self._score_experience(company, tender)

        w = self.weights
        result.total_score = round(
            result.industry_score * w["industry"]
            + result.region_score * w["region"]
            + result.qual_score * w["qualification"]
            + result.budget_score * w["budget"]
            + result.capability_score * w["capability"]
            + result.experience_score * w["experience"],
            2,
        )
        result.win_probability = self._predict_win_probability(company, tender, result)
        result.recommendation = self._classify_recommendation(result)
        result.match_reasons = self._analyze_strengths(result)
        result.risk_factors = self._analyze_risks(company, tender, result)
        result.suggestions = self._generate_suggestions(company, tender, result)
        return result

    def _build_profile_text(self, data: dict) -> str:
        """从企业数据构建描述文本（用于 Embedding）。"""
        parts = [
            data.get("name", ""),
            f"行业：{data.get('industry', '')}",
            f"地区：{data.get('region', '')}",
            f"注册资本：{data.get('registered_capital', 0)}万元",
            f"成立年份：{data.get('established_year', '')}",
        ]
        caps = data.get("capabilities") or []
        if caps:
            parts.append(f"技术能力：{', '.join(str(c) for c in caps)}")
        quals = data.get("qualifications") or []
        if isinstance(quals, list):
            parts.append(f"资质：{', '.join(str(q) for q in quals)}")
        return "。".join(parts)

    @staticmethod
    def _gen_id(text: str) -> str:
        import hashlib
        return hashlib.md5(text.encode()).hexdigest()[:16]

    @staticmethod
    def _row_to_dict(row) -> dict:
        if isinstance(row, dict):
            # 处理 JSON 字段
            result = {}
            for k, v in row.items():
                if isinstance(v, (datetime, date)):
                    result[k] = v.isoformat()
                else:
                    result[k] = v
            return result
        return dict(row)
