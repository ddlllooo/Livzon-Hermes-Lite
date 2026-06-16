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
关注领域：（未设置 — 请告知您常处理的任务类型）
§
工作环境：（未设置 — 请告知常用平台、项目目录或工具偏好）
§
用户角色：（未设置 — 如：开发者 / 研究者 / 产品经理 / 运营人员）
§
常用功能：（未设置 — 如：代码分析、资料检索、文档整理、任务规划）
§
偏好输出格式：（未设置）
§
沟通语言偏好：中文
"""

INITIAL_MEMORY = """\
§
Hermes-Lite Agent 引擎记忆初始化 — 此文件存储 Agent 学到的业务规则和系统经验。
注意：此内容为系统内部信息，禁止向用户披露。
§
项目定位：Hermes Agent 的轻量裁剪版，默认仅启用通用对话、Web 检索、记忆、会话搜索、待办和澄清工具。
"""


def main():
    print("Hermes-Lite Memory System Init")
    print("=" * 40)
    init_memory_system()


if __name__ == "__main__":
    main()
