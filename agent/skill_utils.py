"""Skill utilities for LeadFlow Agent Core.

保留功能：
- SKILL.md 文件解析（frontmatter）
- 平台/环境匹配
- 技能目录扫描
- 渐进式披露支持

移除功能：
- 技能管理（创建/编辑/删除）
- 外部技能目录
- 配置变量系统
- 禁用技能管理
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ── Platform mapping ──────────────────────────────────────────────────────

PLATFORM_MAP = {
    "macos": "darwin",
    "linux": "linux",
    "windows": "win32",
}

EXCLUDED_SKILL_DIRS = frozenset((
    ".git", ".github", ".hub", ".archive",
    ".venv", "venv", "node_modules", "site-packages",
    "__pycache__", ".tox", ".nox",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
))


def is_excluded_skill_path(path) -> bool:
    """True if any component of *path* is in EXCLUDED_SKILL_DIRS."""
    try:
        parts = path.parts
    except AttributeError:
        from pathlib import PurePath
        parts = PurePath(str(path)).parts
    return any(part in EXCLUDED_SKILL_DIRS for part in parts)


# ── Lazy YAML loader ─────────────────────────────────────────────────────

_yaml_load_fn = None


def yaml_load(content: str):
    """Parse YAML with lazy import and CSafeLoader preference."""
    global _yaml_load_fn
    if _yaml_load_fn is None:
        import yaml
        loader = getattr(yaml, "CSafeLoader", None) or yaml.SafeLoader
        def _load(value: str):
            return yaml.load(value, Loader=loader)
        _yaml_load_fn = _load
    return _yaml_load_fn(content)


# ── Frontmatter parsing ──────────────────────────────────────────────────


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from a markdown string.

    Returns:
        (frontmatter_dict, remaining_body)
    """
    frontmatter: Dict[str, Any] = {}
    body = content

    if not content.startswith("---"):
        return frontmatter, body

    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return frontmatter, body

    yaml_content = content[3 : end_match.start() + 3]
    body = content[end_match.end() + 3 :]

    try:
        parsed = yaml_load(yaml_content)
        if isinstance(parsed, dict):
            frontmatter = parsed
    except Exception:
        # Fallback: simple key:value parsing for malformed YAML
        for line in yaml_content.strip().split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()

    return frontmatter, body


# ── Platform matching ─────────────────────────────────────────────────────


def skill_matches_platform(frontmatter: Dict[str, Any]) -> bool:
    """Return True when the skill is compatible with the current OS.

    Skills declare platform requirements via a top-level ``platforms`` list::

        platforms: [macos]          # macOS only
        platforms: [macos, linux]   # macOS and Linux
        platforms: [windows]        # Windows only

    If the field is absent or empty the skill is compatible with **all** platforms.
    """
    platforms = frontmatter.get("platforms")
    if not platforms:
        return True
    if not isinstance(platforms, list):
        platforms = [platforms]
    current = sys.platform
    for platform in platforms:
        normalized = str(platform).lower().strip()
        mapped = PLATFORM_MAP.get(normalized, normalized)
        if current.startswith(mapped):
            return True
    return False


# ── Environment matching ──────────────────────────────────────────────────

# LeadFlow 简化版：只检查基本环境
_KNOWN_ENVIRONMENTS = frozenset({"docker"})
_ENV_DETECT_CACHE: Dict[str, bool] = {}


def _detect_environment(env: str) -> bool:
    """Return True when the named runtime environment is currently active."""
    if env in _ENV_DETECT_CACHE:
        return _ENV_DETECT_CACHE[env]

    result = True
    if env == "docker":
        try:
            # 检查是否在 Docker 容器中
            result = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
        except Exception:
            result = False

    _ENV_DETECT_CACHE[env] = result
    return result


def skill_matches_environment(frontmatter: Dict[str, Any]) -> bool:
    """Return True when the skill is relevant to the current runtime environment.

    Skills may declare an ``environments`` list::

        environments: [docker]        # only relevant inside any container

    If the field is absent or empty the skill is relevant in **all** environments.
    """
    environments = frontmatter.get("environments")
    if not environments:
        return True
    if not isinstance(environments, list):
        environments = [environments]
    for env in environments:
        normalized = str(env).lower().strip()
        if not normalized:
            continue
        if normalized not in _KNOWN_ENVIRONMENTS:
            return True  # Unknown tag - don't hide
        if _detect_environment(normalized):
            return True
    return False


# ── Disabled skills ───────────────────────────────────────────────────────


def get_disabled_skill_names(platform: str | None = None) -> Set[str]:
    """LeadFlow: 不支持禁用技能，返回空集合。"""
    return set()


# ── Skills directories ────────────────────────────────────────────────────


def get_skills_dir() -> Path:
    """Return the local skills directory path."""
    from hermes_constants import get_hermes_home
    return get_hermes_home() / "skills"


def get_external_skills_dirs() -> List[Path]:
    """LeadFlow: 不支持外部技能目录，返回空列表。"""
    return []


def get_all_skills_dirs() -> List[Path]:
    """Return all skill directories.

    LeadFlow 版本：只返回本地 skills 目录。
    """
    return [get_skills_dir()]


# ── Condition extraction ──────────────────────────────────────────────────


def extract_skill_conditions(frontmatter: Dict[str, Any]) -> Dict[str, List]:
    """Extract conditional activation fields from parsed frontmatter.

    返回示例：
    {
        "fallback_for_toolsets": ["web"],
        "requires_toolsets": ["memory"],
        "fallback_for_tools": ["web_search"],
        "requires_tools": ["terminal"],
    }
    """
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    hermes = metadata.get("hermes") or {}
    if not isinstance(hermes, dict):
        hermes = {}

    return {
        "fallback_for_toolsets": hermes.get("fallback_for_toolsets", []),
        "requires_toolsets": hermes.get("requires_toolsets", []),
        "fallback_for_tools": hermes.get("fallback_for_tools", []),
        "requires_tools": hermes.get("requires_tools", []),
    }


# ── Description extraction ────────────────────────────────────────────────


def extract_skill_description(frontmatter: Dict[str, Any]) -> str:
    """Extract a truncated description from parsed frontmatter."""
    raw_desc = frontmatter.get("description", "")
    if not raw_desc:
        return ""
    desc = str(raw_desc).strip().strip("'\"")
    if len(desc) > 60:
        return desc[:57] + "..."
    return desc


# ── File iteration ────────────────────────────────────────────────────────


def iter_skill_index_files(skills_dir: Path, filename: str):
    """Walk skills_dir yielding sorted paths matching *filename*.

    Excludes dependency, virtualenv, VCS, and cache directories.
    """
    if not skills_dir.is_dir():
        return
    matches = []
    for root, dirs, files in os.walk(skills_dir, followlinks=True):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_SKILL_DIRS]
        if filename in files:
            matches.append(Path(root) / filename)
    for path in sorted(matches, key=lambda p: str(p.relative_to(skills_dir))):
        yield path


# ── Skill loading ─────────────────────────────────────────────────────────


def load_skill_file(skill_path: Path) -> Optional[Dict[str, Any]]:
    """Load a single SKILL.md file and return parsed metadata.

    Returns:
        {
            "name": "skill-name",
            "description": "Short description",
            "path": Path(...),
            "content": "Full markdown content",
            "frontmatter": {...},
            "conditions": {...},
        }
        or None if loading fails.
    """
    try:
        raw = skill_path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter(raw)

        # 从目录名或 frontmatter 获取技能名
        name = frontmatter.get("name") or skill_path.parent.name

        return {
            "name": str(name),
            "description": extract_skill_description(frontmatter),
            "path": skill_path,
            "content": body.strip(),
            "frontmatter": frontmatter,
            "conditions": extract_skill_conditions(frontmatter),
        }
    except Exception as e:
        logger.debug("Failed to load skill %s: %s", skill_path, e)
        return None


def load_user_skill_files() -> List[Dict[str, Any]]:
    """Load all user skill files from skills directories.

    Returns a list of skill metadata dicts, filtered by platform/environment.
    """
    skills = []
    disabled = get_disabled_skill_names()

    for skills_dir in get_all_skills_dirs():
        if not skills_dir.is_dir():
            continue
        for skill_file in iter_skill_index_files(skills_dir, "SKILL.md"):
            # Skip excluded paths
            if is_excluded_skill_path(skill_file):
                continue

            skill = load_skill_file(skill_file)
            if not skill:
                continue

            # Filter disabled skills
            if skill["name"] in disabled:
                continue

            # Filter by platform/environment
            if not skill_matches_platform(skill["frontmatter"]):
                continue
            if not skill_matches_environment(skill["frontmatter"]):
                continue

            skills.append(skill)

    return skills


# ── Skill matching for progressive disclosure ─────────────────────────────


def get_skill_metadata(skill: Dict[str, Any]) -> Dict[str, Any]:
    """Extract lightweight metadata for skill index/offer.

    Returns a dict suitable for inclusion in the system prompt skill index.
    """
    return {
        "name": skill["name"],
        "description": skill["description"],
        "conditions": skill["conditions"],
    }


def find_matching_skills(
    tools_used: List[str],
    toolsets_used: List[str],
    all_skills: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Find skills that match the current context for progressive disclosure.

    匹配规则：
    1. requires_tools: 如果使用了指定工具，推荐此技能
    2. requires_toolsets: 如果启用了指定工具集，推荐此技能
    3. fallback_for_tools: 如果工具不可用，推荐此技能作为替代
    4. fallback_for_toolsets: 如果工具集不可用，推荐此技能作为替代

    Args:
        tools_used: 当前会话中使用的工具名称列表
        toolsets_used: 当前启用的工具集名称列表
        all_skills: 所有可用的技能列表

    Returns:
        匹配的技能列表，按相关性排序
    """
    matched = []

    for skill in all_skills:
        conditions = skill.get("conditions", {})
        score = 0

        # Check requires_tools
        requires_tools = conditions.get("requires_tools", [])
        if requires_tools:
            matching_tools = set(requires_tools) & set(tools_used)
            if matching_tools:
                score += len(matching_tools) * 10

        # Check requires_toolsets
        requires_toolsets = conditions.get("requires_toolsets", [])
        if requires_toolsets:
            matching_toolsets = set(requires_toolsets) & set(toolsets_used)
            if matching_toolsets:
                score += len(matching_toolsets) * 5

        # Check fallback_for_tools (推荐作为替代)
        fallback_tools = conditions.get("fallback_for_tools", [])
        if fallback_tools:
            # 如果工具不可用，给予推荐分数
            score += len(fallback_tools) * 3

        # Check fallback_for_toolsets
        fallback_toolsets = conditions.get("fallback_for_toolsets", [])
        if fallback_toolsets:
            score += len(fallback_toolsets) * 2

        if score > 0:
            matched.append((score, skill))

    # Sort by score descending
    matched.sort(key=lambda x: x[0], reverse=True)

    return [skill for _, skill in matched]


def resolve_skill_path(skill_name: str) -> Optional[Path]:
    """Resolve a skill name to its SKILL.md file path.

    Supports qualified names like "namespace:skill-name".
    """
    # Parse qualified name
    namespace = None
    if ":" in skill_name:
        namespace, skill_name = skill_name.split(":", 1)

    for skills_dir in get_all_skills_dirs():
        if not skills_dir.is_dir():
            continue

        # Search for skill directory by name
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            if skill_dir.name == skill_name:
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    return skill_file

    return None


# ── Frontmatter extraction helpers ────────────────────────────────────────


def extract_frontmatter(content: str) -> Dict[str, Any]:
    """Extract only the frontmatter dict from markdown content."""
    frontmatter, _ = parse_frontmatter(content)
    return frontmatter
