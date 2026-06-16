"""
Per-User Memory Service — 用户画像隔离

LeadFlow 是多用户 Web 应用，不同账号需要独立的用户画像（USER.md）。
此模块提供：
  - 按 user_id 隔离 USER.md 路径
  - 默认用户画像模板
  - 用户画像初始化/迁移
  - MemoryStore 工厂（配置好 per-user 路径）

访问控制模型：
  ┌─────────────┬──────────────┬──────────────────────────────┐
  │ 文件         │ 可见性       │ 说明                          │
  ├─────────────┼──────────────┼──────────────────────────────┤
  │ AGENTS.md   │ 系统内部     │ Agent 引擎指令，用户禁止访问    │
  │ MEMORY.md   │ 系统内部     │ 引擎记忆，用户禁止访问          │
  │ USER.md     │ 用户可见     │ 用户画像，前端格式化展示        │
  └─────────────┴──────────────┴──────────────────────────────┘

  MEMORY.md 工具响应已脱敏（_success_response 屏蔽 entries），
  AGENTS.md 通过 build_context_files_prompt 注入 system prompt 但
  不暴露给任何工具/API 端点。

架构：
  memories/
  ├── MEMORY.md              ← 全局引擎记忆（内部，用户不可见）
  ├── users/
  │   ├── {user_id_1}/
  │   │   └── USER.md        ← 用户1 的画像（用户可见）
  │   └── _default/
  │       └── USER.md        ← 默认画像模板（新用户复制此文件）
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def get_memory_base_dir() -> Path:
    """返回记忆根目录（HERMES_HOME/memories）"""
    from hermes_constants import get_hermes_home
    return get_hermes_home() / "memories"


def get_user_memory_dir(user_id: Optional[str] = None) -> Path:
    """返回指定用户的记忆目录。

    - 有 user_id → memories/users/{user_id}/
    - 无 user_id → memories/（全局，兼容单用户模式）
    """
    base = get_memory_base_dir()
    if user_id and user_id.strip():
        return base / "users" / user_id.strip()
    return base


def ensure_user_memory(user_id: str) -> Path:
    """确保用户记忆目录存在，不存在则从模板初始化。

    Returns:
        用户记忆目录路径
    """
    user_dir = get_user_memory_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    user_file = user_dir / "USER.md"
    if not user_file.exists():
        template = _get_default_template()
        user_file.write_text(template, encoding="utf-8")
        logger.info("Initialized USER.md for user %s from template", user_id)

    return user_dir


def _get_default_template() -> str:
    """获取默认用户画像模板内容。

    模板文件优先从 memories/users/_default/USER.md 读取，
    不存在则使用内置默认值。
    """
    base = get_memory_base_dir()
    template_path = base / "users" / "_default" / "USER.md"

    if template_path.exists():
        return template_path.read_text(encoding="utf-8")

    return DEFAULT_USER_PROFILE_TEMPLATE


def create_memory_store_for_user(
    user_id: Optional[str] = None,
    memory_char_limit: int = 2200,
    user_char_limit: int = 1375,
):
    """创建针对特定用户配置的 MemoryStore。

    核心逻辑：
    - MEMORY.md（引擎记忆）：始终在 memories/ 根目录，全局共享
    - USER.md（用户画像）：当有 user_id 时，在 memories/users/{user_id}/

    通过 monkey-patch MemoryStore._path_for() 实现路径重定向。
    这样不修改 core 代码，仅改变文件路径解析。

    Args:
        user_id: 平台用户 ID（Web API 传入），None 表示全局/单用户模式
        memory_char_limit: MEMORY.md 字符上限
        user_char_limit: USER.md 字符上限

    Returns:
        配置好的 MemoryStore 实例
    """
    from tools.memory_tool import MemoryStore

    store = MemoryStore(
        memory_char_limit=memory_char_limit,
        user_char_limit=user_char_limit,
    )

    if user_id and user_id.strip():
        # Per-user 模式：重定向 USER.md 路径
        user_dir = ensure_user_memory(user_id)

        def _per_user_path_for(self_or_target, target=None):
            """Override _path_for to scope USER.md per user_id."""
            # MemoryStore._path_for is a @staticmethod, so when called
            # on an instance it gets no 'self'. But types.MethodType
            # injects 'self' as first arg. Handle both cases.
            t = target if target is not None else self_or_target
            if t == "user":
                return user_dir / "USER.md"
            return get_memory_base_dir() / "MEMORY.md"

        # 绑定到实例（不影响其他 MemoryStore 实例）
        import types
        store._path_for = types.MethodType(_per_user_path_for, store)
        logger.info("Memory store scoped: user_id=%s, USER.md=%s", user_id, user_dir)

    return store


# ── 默认用户画像模板 ────────────────────────────────────────────

DEFAULT_USER_PROFILE_TEMPLATE = """§
我是新注册的 LeadFlow 用户，请通过对话了解我的信息并更新此画像。
§
关注行业：（未设置 — 请告知您所在的行业或关注的领域）
§
关注地区：（未设置 — 请告知您关注的地域范围）
§
用户角色：（未设置 — 如：企业管理者 / 投标经理 / 市场分析师 / 采购负责人）
§
偏好输出格式：表格形式的结构化对比分析
"""
