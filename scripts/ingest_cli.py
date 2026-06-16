#!/usr/bin/env python3
"""Hermes-Lite 知识库 — 命令行导入工具。

用法：
    # 导入单个文件
    python scripts/ingest_cli.py import path/to/file.pdf

    # 导入整个目录（递归扫描）
    python scripts/ingest_cli.py import path/to/docs/

    # 导入纯文本
    python scripts/ingest_cli.py import --text "要导入的文本内容" --source "来源标识"

    # 查看知识库统计
    python scripts/ingest_cli.py stats

    # 删除指定文档
    python scripts/ingest_cli.py delete --source "文件名.pdf"

    # 健康检查
    python scripts/ingest_cli.py health

环境变量（.env 文件）：
    OCEANBASE_HOST / OCEANBASE_PORT / OCEANBASE_USER / OCEANBASE_PASSWORD / OCEANBASE_DATABASE
    EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(_project_root) / ".env")
except ImportError:
    pass


def cmd_import(args):
    """导入文件或目录。"""
    from services.embedding_service import get_embedder
    from services.chunk_store import get_chunk_store

    embedder = get_embedder()
    store = get_chunk_store()

    if args.text:
        # 纯文本模式
        from services.document_ingestion import parse_text_content, process_document
        doc = parse_text_content(args.text, source=args.source or "inline")
        stat = process_document(doc, embedder, store)
        print(json.dumps(stat, ensure_ascii=False, indent=2))
        return

    path = Path(args.path)
    if not path.exists():
        print(f"错误: 路径不存在 — {args.path}", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        from services.document_ingestion import process_directory
        results = process_directory(
            str(path), embedder, store,
            parent_chars=args.parent_chars,
            child_chars=args.child_chars,
        )
        # 汇总
        ok = [r for r in results if "error" not in r]
        fail = [r for r in results if "error" in r]
        print(f"\n{'='*50}")
        print(f"导入完成: {len(ok)} 成功, {len(fail)} 失败")
        if ok:
            total_parents = sum(r["parent_chunks"] for r in ok)
            total_children = sum(r["child_chunks"] for r in ok)
            total_chars = sum(r["total_chars"] for r in ok)
            print(f"总计: {total_chars} 字符, {total_parents} 父块, {total_children} 子块")
        if fail:
            print(f"\n失败文件:")
            for r in fail:
                print(f"  {r['source']}: {r['error']}")
    else:
        from services.document_ingestion import process_file
        stat = process_file(
            str(path), embedder, store,
            parent_chars=args.parent_chars,
            child_chars=args.child_chars,
        )
        print(json.dumps(stat, ensure_ascii=False, indent=2))


def cmd_delete(args):
    """删除指定文档。"""
    from services.chunk_store import get_chunk_store
    store = get_chunk_store()

    if not args.source:
        print("错误: 需要指定 --source 参数", file=sys.stderr)
        sys.exit(1)

    # 先查找匹配的 parent_id
    with store._pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT parent_id FROM parent_chunks WHERE source = %s",
                (args.source,),
            )
            rows = cur.fetchall()

    if not rows:
        print(f"未找到 source='{args.source}' 的文档")
        return

    total_deleted = 0
    for row in rows:
        pid = row["parent_id"]
        # 取 parent_id 前缀（去掉 _pXXXX 后缀）
        doc_prefix = pid.rsplit("_p", 1)[0] if "_p" in pid else pid
        deleted = store.delete_document(doc_prefix)
        total_deleted += deleted

    print(f"已删除 {len(rows)} 个父块, {total_deleted} 个子块 (source='{args.source}')")


def cmd_stats(args):
    """查看知识库统计。"""
    from services.chunk_store import get_chunk_store
    store = get_chunk_store()
    info = store.health_check()

    if not info["connected"]:
        print(f"连接失败: {info['error']}")
        sys.exit(1)

    print(f"OceanBase 连接: ✓")
    for table, count in info["tables"].items():
        print(f"  {table}: {count} 行")

    # 按 source 统计
    with store._pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source, COUNT(*) AS parent_count
                FROM parent_chunks
                GROUP BY source
                ORDER BY parent_count DESC
                LIMIT 20
            """)
            rows = cur.fetchall()

    if rows:
        print(f"\n文档列表 (Top 20):")
        print(f"  {'来源':<40} {'父块数':>6}")
        print(f"  {'-'*40} {'-'*6}")
        for r in rows:
            print(f"  {r['source']:<40} {r['parent_count']:>6}")


def cmd_health(args):
    """健康检查。"""
    from services.chunk_store import get_chunk_store
    from services.embedding_service import get_embedder
    from services.rerank_service import get_reranker

    print("Hermes-Lite 知识库健康检查")
    print("=" * 40)

    # OceanBase
    store = get_chunk_store()
    info = store.health_check()
    if info["connected"]:
        print(f"✓ OceanBase: 已连接")
        for t, c in info["tables"].items():
            print(f"  {t}: {c} 行")
    else:
        print(f"✗ OceanBase: {info['error']}")

    # Embedding
    embedder = get_embedder()
    if embedder.available:
        print(f"✓ Embedding: {embedder.cfg.provider}/{embedder.model}")
    else:
        print(f"✗ Embedding: API key 未配置")

    # Rerank
    reranker = get_reranker()
    if reranker.available:
        print(f"✓ Rerank: {reranker.cfg.provider}/{reranker.model}")
    elif reranker.cfg.enabled:
        print(f"△ Rerank: 已启用但未配置")
    else:
        print(f"○ Rerank: 已禁用（退化为跳过精排）")


def cmd_search(args):
    """快速测试检索（调试用）。"""
    from services.retrieval_pipeline import RetrievalPipeline
    from services.chunk_store import get_chunk_store
    from services.embedding_service import get_embedder
    from services.rerank_service import get_reranker

    pipeline = RetrievalPipeline(
        chunk_store=get_chunk_store(),
        embedder=get_embedder(),
        reranker=get_reranker(),
        config={"final_top_n": args.top_k},
    )
    results = pipeline.search(args.query)

    if not results:
        print("未找到相关内容")
        return

    for i, r in enumerate(results):
        print(f"\n{'='*60}")
        print(f"[{i+1}] parent_id={r.parent_id}  score={r.score}  children={r.matched_children}")
        print(f"    source: {r.source}")
        print(f"    content ({len(r.content)} chars):")
        # 截断显示
        preview = r.content[:500] + ("..." if len(r.content) > 500 else "")
        print(f"    {preview}")


def main():
    parser = argparse.ArgumentParser(
        description="Hermes-Lite 知识库管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # import
    p_import = sub.add_parser("import", help="导入文档到知识库")
    p_import.add_argument("path", nargs="?", help="文件或目录路径")
    p_import.add_argument("--text", help="直接导入文本内容")
    p_import.add_argument("--source", help="来源标识（配合 --text 使用）")
    p_import.add_argument("--parent-chars", type=int, default=2000, help="父块最大字符数")
    p_import.add_argument("--child-chars", type=int, default=512, help="子块字符数")
    p_import.set_defaults(func=cmd_import)

    # delete
    p_delete = sub.add_parser("delete", help="删除文档")
    p_delete.add_argument("--source", required=True, help="文档来源标识")
    p_delete.set_defaults(func=cmd_delete)

    # stats
    p_stats = sub.add_parser("stats", help="知识库统计")
    p_stats.set_defaults(func=cmd_stats)

    # health
    p_health = sub.add_parser("health", help="健康检查")
    p_health.set_defaults(func=cmd_health)

    # search
    p_search = sub.add_parser("search", help="测试检索（调试）")
    p_search.add_argument("query", help="检索查询")
    p_search.add_argument("--top-k", type=int, default=3, help="返回数量")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.func(args)


if __name__ == "__main__":
    main()
