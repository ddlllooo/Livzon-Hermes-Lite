"""
Hermes-Lite Memory System Initialization

Creates the memory directory structure and default templates.
Run once during deployment or after a fresh install.

Usage:
    python scripts/init_memory.py
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def init_memory_system():
    """Initialize the memory directory structure with templates."""

    from hermes_constants import get_hermes_home
    base = get_hermes_home() / "memories"

    dirs = [
        base,
        base / "users" / "_default",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {d}")

    # ── Default USER.md template ──────────────────────────────────
    default_user = base / "users" / "_default" / "USER.md"
    if not default_user.exists():
        default_user.write_text(
            DEFAULT_USER_TEMPLATE,
            encoding="utf-8",
        )
        print(f"  ✓ Created template: {default_user}")
    else:
        print(f"  · Template exists: {default_user}")

    # ── Global MEMORY.md (engine knowledge) ───────────────────────
    global_memory = base / "MEMORY.md"
    if not global_memory.exists():
        global_memory.write_text(
            INITIAL_MEMORY,
            encoding="utf-8",
        )
        print(f"  ✓ Created: {global_memory}")
    else:
        print(f"  · Exists: {global_memory}")

    print("\n✅ Memory system initialized.")
    print(f"   Memory dir: {base}")
    print(f"   User template: {base / 'users' / '_default' / 'USER.md'}")
    print(f"   Per-user dirs will be created at: {base / 'users' / '<user_id>' / 'USER.md'}")


# ── Templates ────────────────────────────────────────────────────

DEFAULT_USER_TEMPLATE = """\
§
我是新注册的 Hermes-Lite 用户，请通过对话了解我的信息并更新此画像。
§
关注行业：（未设置 — 请告知您所在的行业或关注的领域，如：IT、医疗、建筑、制造业）
§
关注地区：（未设置 — 请告知您关注的地域范围，如：北京、长三角、全国）
§
用户角色：（未设置 — 如：企业管理者 / 投标经理 / 市场分析师 / 采购负责人）
§
常用功能：（未设置 — 如：招标搜索、企业匹配、资质分析、知识库查询）
§
偏好输出格式：表格形式的结构化对比分析
§
沟通语言偏好：中文
"""

INITIAL_MEMORY = """\
§
Hermes-Lite Agent 引擎记忆初始化 — 此文件存储 Agent 学到的业务规则和系统经验。
注意：此内容为系统内部信息，禁止向用户披露。
§
数据库：OceanBase V4.4.1+，MySQL 模式，支持 VECTOR 类型和 FULLTEXT 全文检索。
检索管道四阶段：向量检索 → BM25 检索 → RRF 融合 → Rerank 精排。
§
Embedding 模型可通过 .env 切换（zhipu/qwen/openai），切换后需重建向量索引。
"""


if __name__ == "__main__":
    print("Hermes-Lite Memory System Init")
    print("=" * 40)
    init_memory_system()
