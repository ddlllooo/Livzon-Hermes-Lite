#!/usr/bin/env python3
"""Hermes-Lite 招标数据管理 — 命令行工具。

用法：
    # 导入招标数据（JSON 文件）
    python scripts/tender_cli.py import-tenders path/to/tenders.json

    # 导入企业数据（JSON 文件）
    python scripts/tender_cli.py import-companies path/to/companies.json

    # 添加单条招标
    python scripts/tender_cli.py add-tender '{"title":"...", "industry":"IT", ...}'

    # 添加单家企业
    python scripts/tender_cli.py add-company '{"name":"...", "industry":"IT", ...}'

    # 查看统计
    python scripts/tender_cli.py stats

    # 测试推荐
    python scripts/tender_cli.py recommend <company_id> [--top-k 5]

    # 测试匹配
    python scripts/tender_cli.py match <company_id> <tender_id>

    # 测试搜索
    python scripts/tender_cli.py search [--keyword ...] [--industry ...] [--region ...]

JSON 数据格式见 data/examples/ 目录。

环境变量（.env）：
    OCEANBASE_HOST / OCEANBASE_PORT / OCEANBASE_USER / OCEANBASE_PASSWORD / OCEANBASE_DATABASE
    EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL
"""

import argparse
import json
import logging
import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(_project_root) / ".env")
except ImportError:
    pass


def _get_svc():
    from services.tender_service import TenderService
    from services.chunk_store import get_chunk_store
    from services.embedding_service import get_embedder
    return TenderService(chunk_store=get_chunk_store(), embedder=get_embedder())


def cmd_import_tenders(args):
    """批量导入招标数据。"""
    path = Path(args.file)
    if not path.exists():
        print(f"错误: 文件不存在 — {args.file}", file=sys.stderr)
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    svc = _get_svc()
    ok, fail = 0, 0
    for item in data:
        try:
            svc.add_tender(item)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ✗ {item.get('title', '?')[:40]}: {e}")

    print(f"\n招标导入完成: {ok} 成功, {fail} 失败")


def cmd_import_companies(args):
    """批量导入企业数据。"""
    path = Path(args.file)
    if not path.exists():
        print(f"错误: 文件不存在 — {args.file}", file=sys.stderr)
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    svc = _get_svc()
    ok, fail = 0, 0
    for item in data:
        try:
            cid = svc.add_company(item)
            # 导入资质
            for q in item.get("qualifications_detail", []):
                q["company_id"] = cid
                svc.add_qualification(q)
            # 导入业绩
            for p in item.get("performance_history", []):
                p["company_id"] = cid
                svc.add_performance(p)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"  ✗ {item.get('name', '?')}: {e}")

    print(f"\n企业导入完成: {ok} 成功, {fail} 失败")


def cmd_add_tender(args):
    """添加单条招标。"""
    data = json.loads(args.json)
    svc = _get_svc()
    tid = svc.add_tender(data)
    print(f"✓ 招标已添加: {tid} — {data.get('title', '')[:60]}")


def cmd_add_company(args):
    """添加单家企业。"""
    data = json.loads(args.json)
    svc = _get_svc()
    cid = svc.add_company(data)
    # 导入资质明细
    for q in data.get("qualifications_detail", []):
        q["company_id"] = cid
        svc.add_qualification(q)
    # 导入业绩明细
    for p in data.get("performance_history", []):
        p["company_id"] = cid
        svc.add_performance(p)
    print(f"✓ 企业已添加: {cid} — {data['name']}")


def cmd_stats(args):
    """查看统计。"""
    svc = _get_svc()
    stats = svc.get_stats()
    print(f"\nHermes-Lite 招标系统统计")
    print(f"{'='*50}")
    print(f"  招标项目总数:  {stats.get('tenders', 0)}")
    print(f"  活跃招标:      {stats.get('active_tenders', 0)}")
    print(f"  企业总数:      {stats.get('companies', 0)}")
    print(f"  资质记录:      {stats.get('company_qualifications', 0)}")
    print(f"  历史业绩:      {stats.get('company_performance', 0)}")
    print(f"  匹配缓存:      {stats.get('tender_matches', 0)}")
    industries = stats.get("top_industries", [])
    if industries:
        print(f"\n  行业分布 (Top {len(industries)}):")
        for ind in industries:
            print(f"    {ind['industry'] or '未分类':<20} {ind['cnt']:>5} 个")


def cmd_recommend(args):
    """测试推荐。"""
    svc = _get_svc()
    rec = svc.recommend_for_company(
        company_id=args.company_id,
        top_k=args.top_k,
    )
    print(f"\n🎯 推荐结果 — {rec.company_name}")
    print(f"{'='*60}")
    print(rec.summary)
    for i, m in enumerate(rec.recommendations):
        print(f"\n  [{i+1}] {m.tender_title}")
        print(f"      综合分: {m.total_score}  中标率: {m.win_probability}%  等级: {m.recommendation}")
        print(f"      行业:{m.industry_score} 地域:{m.region_score} 资质:{m.qual_score} "
              f"预算:{m.budget_score} 能力:{m.capability_score} 业绩:{m.experience_score}")
        if m.match_reasons:
            print(f"      优势: {', '.join(m.match_reasons)}")
        if m.risk_factors:
            print(f"      风险: {', '.join(m.risk_factors)}")
        if m.suggestions:
            print(f"      建议: {m.suggestions[0]}")


def cmd_match(args):
    """测试匹配。"""
    svc = _get_svc()
    m = svc.match(company_id=args.company_id, tender_id=args.tender_id)
    print(f"\n📊 匹配评估")
    print(f"{'='*60}")
    print(f"  企业: {m.company_name} ({m.company_id})")
    print(f"  招标: {m.tender_title} ({m.tender_id})")
    print(f"\n  六维度评分:")
    print(f"    行业匹配:  {m.industry_score:>5.1f}")
    print(f"    地域匹配:  {m.region_score:>5.1f}")
    print(f"    资质匹配:  {m.qual_score:>5.1f}")
    print(f"    预算匹配:  {m.budget_score:>5.1f}")
    print(f"    能力匹配:  {m.capability_score:>5.1f}")
    print(f"    业绩匹配:  {m.experience_score:>5.1f}")
    print(f"\n  综合分: {m.total_score}  中标率: {m.win_probability}%  推荐: {m.recommendation}")
    if m.match_reasons:
        print(f"\n  ✅ 优势:")
        for r in m.match_reasons:
            print(f"    • {r}")
    if m.risk_factors:
        print(f"\n  ⚠️  风险:")
        for r in m.risk_factors:
            print(f"    • {r}")
    if m.suggestions:
        print(f"\n  💡 建议:")
        for s in m.suggestions:
            print(f"    • {s}")


def cmd_search(args):
    """测试搜索。"""
    svc = _get_svc()
    results = svc.search_tenders(
        keyword=args.keyword or "",
        industry=args.industry or "",
        region=args.region or "",
        budget_min=args.budget_min or 0,
        budget_max=args.budget_max or 0,
        status=args.status or "active",
        limit=args.limit or 20,
    )
    print(f"\n搜索结果: {len(results)} 条")
    print(f"{'='*60}")
    for i, r in enumerate(results):
        budget = f"{r.get('budget_min', 0)}-{r.get('budget_max', 0)}万" if r.get('budget_max') else "未公开"
        print(f"  [{i+1}] {r['title'][:50]}")
        print(f"      {r.get('industry','')} | {r.get('region','')} | {budget} | 截止:{r.get('deadline','')}")


def main():
    parser = argparse.ArgumentParser(description="Hermes-Lite 招标数据管理工具")
    sub = parser.add_subparsers(dest="command")

    # import-tenders
    p = sub.add_parser("import-tenders", help="批量导入招标（JSON文件）")
    p.add_argument("file", help="JSON 文件路径")
    p.set_defaults(func=cmd_import_tenders)

    # import-companies
    p = sub.add_parser("import-companies", help="批量导入企业（JSON文件）")
    p.add_argument("file", help="JSON 文件路径")
    p.set_defaults(func=cmd_import_companies)

    # add-tender
    p = sub.add_parser("add-tender", help="添加单条招标")
    p.add_argument("json", help="JSON 字符串")
    p.set_defaults(func=cmd_add_tender)

    # add-company
    p = sub.add_parser("add-company", help="添加单家企业")
    p.add_argument("json", help="JSON 字符串")
    p.set_defaults(func=cmd_add_company)

    # stats
    p = sub.add_parser("stats", help="查看统计")
    p.set_defaults(func=cmd_stats)

    # recommend
    p = sub.add_parser("recommend", help="测试推荐")
    p.add_argument("company_id", help="企业ID")
    p.add_argument("--top-k", type=int, default=5)
    p.set_defaults(func=cmd_recommend)

    # match
    p = sub.add_parser("match", help="测试匹配")
    p.add_argument("company_id", help="企业ID")
    p.add_argument("tender_id", help="招标ID")
    p.set_defaults(func=cmd_match)

    # search
    p = sub.add_parser("search", help="搜索招标")
    p.add_argument("--keyword", default="")
    p.add_argument("--industry", default="")
    p.add_argument("--region", default="")
    p.add_argument("--budget-min", type=float, default=0)
    p.add_argument("--budget-max", type=float, default=0)
    p.add_argument("--status", default="active")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
