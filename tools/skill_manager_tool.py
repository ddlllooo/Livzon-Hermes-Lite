"""Skill Manager Tool for LeadFlow Agent Core.

提供技能的创建、编辑、删除、查看等功能。
技能存储在 {HERMES_HOME}/skills/ 目录下。

目录结构：
    skills/
    ├── my-skill/
    │   ├── SKILL.md           # 主指令文件（必需）
    │   ├── references/        # 参考文档
    │   │   └── api.md
    │   ├── templates/         # 模板文件
    │   │   └── template.md
    │   └── scripts/           # 脚本文件
    │       └── helper.py
    └── category/              # 分类目录
        └── another-skill/
            └── SKILL.md
"""

import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_SKILL_FILE_BYTES = 1 * 1024 * 1024  # 1 MiB

# Valid file paths within a skill directory
ALLOWED_FILE_PREFIXES = {"references/", "templates/", "scripts/", "assets/"}

# Security: patterns that may indicate prompt injection
_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "disregard your",
    "forget your instructions",
    "new instructions:",
    "system prompt:",
    "<system>",
    "]]>",
]


# ── Path helpers ──────────────────────────────────────────────────────────

def get_skills_dir() -> Path:
    """Return the local skills directory path."""
    from hermes_constants import get_hermes_home
    return get_hermes_home() / "skills"


def _find_skill(name: str) -> Optional[Dict[str, Any]]:
    """Find a skill by name in the skills directory.

    Returns:
        {"name": str, "path": Path} or None
    """
    skills_dir = get_skills_dir()
    if not skills_dir.exists():
        return None

    # Search recursively for SKILL.md files
    for skill_md in skills_dir.rglob("SKILL.md"):
        try:
            content = skill_md.read_text(encoding="utf-8")[:4000]
            from agent.skill_utils import parse_frontmatter
            frontmatter, _ = parse_frontmatter(content)
            skill_name = frontmatter.get("name") or skill_md.parent.name
            if skill_name == name:
                return {"name": name, "path": skill_md.parent}
        except Exception:
            continue

    return None


def _resolve_skill_dir(name: str, category: str = None) -> Path:
    """Resolve the directory path for a new skill."""
    skills_dir = get_skills_dir()
    if category:
        return skills_dir / category / name
    return skills_dir / name


def _skill_not_found_error(name: str, hint: str = "") -> str:
    """Generate a skill-not-found error message."""
    skills = _find_all_skills()
    available = [s["name"] for s in skills[:20]]
    return (
        f"Skill '{name}' not found.{hint}\n"
        f"Available skills: {', '.join(available) if available else 'none'}"
    )


def _find_all_skills() -> List[Dict[str, Any]]:
    """Find all skills in the skills directory."""
    skills_dir = get_skills_dir()
    if not skills_dir.exists():
        return []

    skills = []
    seen_names = set()

    for skill_md in skills_dir.rglob("SKILL.md"):
        try:
            content = skill_md.read_text(encoding="utf-8")[:4000]
            from agent.skill_utils import parse_frontmatter, skill_matches_platform
            frontmatter, _ = parse_frontmatter(content)

            if not skill_matches_platform(frontmatter):
                continue

            name = frontmatter.get("name") or skill_md.parent.name
            if name in seen_names:
                continue

            description = frontmatter.get("description", "")
            if not description:
                # Try to get description from first non-heading line
                for line in content.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("---"):
                        description = line[:MAX_DESCRIPTION_LENGTH]
                        break

            seen_names.add(name)
            skills.append({
                "name": name,
                "description": description,
                "path": skill_md.parent,
            })
        except Exception:
            continue

    return sorted(skills, key=lambda s: s["name"])


# ── Validation helpers ────────────────────────────────────────────────────

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _validate_name(name: str) -> Optional[str]:
    """Validate a skill name."""
    if not name:
        return "Skill name is required."
    if len(name) > MAX_NAME_LENGTH:
        return f"Skill name must be <= {MAX_NAME_LENGTH} chars."
    if not _NAME_RE.match(name):
        return "Skill name must be lowercase alphanumeric with hyphens/underscores."
    return None


def _validate_category(category: str) -> Optional[str]:
    """Validate a category name."""
    if not category:
        return None
    if not _NAME_RE.match(category):
        return "Category must be lowercase alphanumeric with hyphens/underscores."
    return None


def _validate_frontmatter(content: str) -> Optional[str]:
    """Validate that content has valid YAML frontmatter."""
    if not content.startswith("---"):
        return "Content must start with YAML frontmatter (---)."
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return "YAML frontmatter not closed (missing second ---)."
    return None


def _validate_content_size(content: str, label: str = "content") -> Optional[str]:
    """Validate content size."""
    size = len(content.encode("utf-8"))
    if size > MAX_SKILL_FILE_BYTES:
        return f"{label} is {size:,} bytes (limit: {MAX_SKILL_FILE_BYTES:,} bytes / 1 MiB)."
    return None


def _validate_file_path(file_path: str) -> Optional[str]:
    """Validate a file path within a skill directory."""
    if not file_path:
        return "file_path is required."
    if ".." in file_path:
        return "Path traversal ('..') is not allowed."
    # Check if path is under an allowed prefix
    allowed = any(file_path.startswith(prefix) for prefix in ALLOWED_FILE_PREFIXES)
    if not allowed:
        return f"file_path must start with one of: {', '.join(ALLOWED_FILE_PREFIXES)}"
    return None


def _resolve_skill_target(skill_dir: Path, file_path: str) -> tuple:
    """Resolve a file path within a skill directory.

    Returns:
        (target_path, error_message)
    """
    target = skill_dir / file_path

    # Verify resolved path is still within skill directory
    try:
        target.resolve().relative_to(skill_dir.resolve())
    except ValueError:
        return None, f"Path '{file_path}' is outside the skill directory."

    return target, None


# ── Security helpers ──────────────────────────────────────────────────────

def _security_scan_skill(skill_dir: Path) -> Optional[str]:
    """Scan a skill directory for security issues.

    Returns error message if issues found, None otherwise.
    """
    for md_file in skill_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8").lower()
            for pattern in _INJECTION_PATTERNS:
                if pattern in content:
                    return f"Security: skill content contains potentially unsafe pattern '{pattern}'"
        except Exception:
            continue
    return None


# ── File I/O helpers ──────────────────────────────────────────────────────

def _atomic_write_text(path: Path, content: str) -> None:
    """Write text to a file atomically using a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file first
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        # Atomic rename
        os.replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Core actions ──────────────────────────────────────────────────────────

def _create_skill(name: str, content: str, category: str = None) -> Dict[str, Any]:
    """Create a new skill with SKILL.md content."""
    # Validate name
    err = _validate_name(name)
    if err:
        return {"success": False, "error": err}

    err = _validate_category(category)
    if err:
        return {"success": False, "error": err}

    # Validate content
    err = _validate_frontmatter(content)
    if err:
        return {"success": False, "error": err}

    err = _validate_content_size(content)
    if err:
        return {"success": False, "error": err}

    # Check for name collisions
    existing = _find_skill(name)
    if existing:
        return {
            "success": False,
            "error": f"A skill named '{name}' already exists at {existing['path']}."
        }

    # Create the skill directory
    skill_dir = _resolve_skill_dir(name, category)
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Write SKILL.md atomically
    skill_md = skill_dir / "SKILL.md"
    _atomic_write_text(skill_md, content)

    # Security scan — roll back on block
    scan_error = _security_scan_skill(skill_dir)
    if scan_error:
        shutil.rmtree(skill_dir, ignore_errors=True)
        return {"success": False, "error": scan_error}

    result = {
        "success": True,
        "message": f"Skill '{name}' created.",
        "path": str(skill_dir),
        "skill_md": str(skill_md),
    }
    if category:
        result["category"] = category
    result["hint"] = (
        f"To add reference files, use "
        f"skill_manage(action='write_file', name='{name}', "
        f"file_path='references/example.md', file_content='...')"
    )
    return result


def _edit_skill(name: str, content: str) -> Dict[str, Any]:
    """Replace the SKILL.md of an existing skill (full rewrite)."""
    err = _validate_frontmatter(content)
    if err:
        return {"success": False, "error": err}

    err = _validate_content_size(content)
    if err:
        return {"success": False, "error": err}

    existing = _find_skill(name)
    if not existing:
        return {"success": False, "error": _skill_not_found_error(name)}

    skill_md = existing["path"] / "SKILL.md"
    # Back up original content for rollback
    original_content = skill_md.read_text(encoding="utf-8") if skill_md.exists() else None
    _atomic_write_text(skill_md, content)

    # Security scan — roll back on block
    scan_error = _security_scan_skill(existing["path"])
    if scan_error:
        if original_content is not None:
            _atomic_write_text(skill_md, original_content)
        return {"success": False, "error": scan_error}

    return {
        "success": True,
        "message": f"Skill '{name}' updated.",
        "path": str(existing["path"]),
    }


def _patch_skill(
    name: str,
    old_string: str,
    new_string: str,
    file_path: str = None,
    replace_all: bool = False,
) -> Dict[str, Any]:
    """Targeted find-and-replace within a skill file."""
    if not old_string:
        return {"success": False, "error": "old_string is required for 'patch'."}
    if new_string is None:
        return {"success": False, "error": "new_string is required for 'patch'."}

    existing = _find_skill(name)
    if not existing:
        return {"success": False, "error": _skill_not_found_error(name)}

    skill_dir = existing["path"]

    if file_path:
        err = _validate_file_path(file_path)
        if err:
            return {"success": False, "error": err}
        target, err = _resolve_skill_target(skill_dir, file_path)
        if err:
            return {"success": False, "error": err}
    else:
        target = skill_dir / "SKILL.md"

    if not target.exists():
        return {"success": False, "error": f"File not found: {target.relative_to(skill_dir)}"}

    content = target.read_text(encoding="utf-8")

    # Simple find and replace
    if replace_all:
        new_content = content.replace(old_string, new_string)
        match_count = content.count(old_string)
    else:
        if old_string not in content:
            return {
                "success": False,
                "error": f"Text not found in {target.name}. Make sure the text matches exactly.",
                "file_preview": content[:500],
            }
        new_content = content.replace(old_string, new_string, 1)
        match_count = 1

    if match_count == 0:
        return {
            "success": False,
            "error": f"Text not found in {target.name}.",
            "file_preview": content[:500],
        }

    # Check size limit
    err = _validate_content_size(new_content, label=file_path or "SKILL.md")
    if err:
        return {"success": False, "error": err}

    # If patching SKILL.md, validate frontmatter is still intact
    if not file_path:
        err = _validate_frontmatter(new_content)
        if err:
            return {"success": False, "error": f"Patch would break SKILL.md structure: {err}"}

    original_content = content
    _atomic_write_text(target, new_content)

    # Security scan — roll back on block
    scan_error = _security_scan_skill(skill_dir)
    if scan_error:
        _atomic_write_text(target, original_content)
        return {"success": False, "error": scan_error}

    return {
        "success": True,
        "message": f"Patched {'SKILL.md' if not file_path else file_path} in skill '{name}' ({match_count} replacement{'s' if match_count > 1 else ''}).",
    }


def _delete_skill(name: str, absorbed_into: Optional[str] = None) -> Dict[str, Any]:
    """Delete a skill.

    absorbed_into: declares intent for the curator.
      - None / missing: not specified (backward compat)
      - "": explicitly pruned, no forwarding target
      - "<skill-name>": content absorbed into that skill
    """
    existing = _find_skill(name)
    if not existing:
        return {"success": False, "error": _skill_not_found_error(name)}

    # Validate absorbed_into target when declared non-empty
    if absorbed_into and absorbed_into.strip():
        target_name = absorbed_into.strip()
        if target_name == name:
            return {
                "success": False,
                "error": f"absorbed_into='{target_name}' cannot equal the skill being deleted.",
            }
        target = _find_skill(target_name)
        if not target:
            return {
                "success": False,
                "error": f"absorbed_into='{target_name}' does not exist.",
            }

    skill_dir = existing["path"]
    skills_root = get_skills_dir()

    # Delete the skill directory
    shutil.rmtree(skill_dir)

    # Clean up empty category directories
    parent = skill_dir.parent
    if parent != skills_root and parent.exists():
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

    message = f"Skill '{name}' deleted."
    if absorbed_into and absorbed_into.strip():
        message += f" Content absorbed into '{absorbed_into.strip()}'."

    return {"success": True, "message": message}


def _write_file(name: str, file_path: str, file_content: str) -> Dict[str, Any]:
    """Add or overwrite a supporting file within a skill directory."""
    err = _validate_file_path(file_path)
    if err:
        return {"success": False, "error": err}

    if file_content is None:
        return {"success": False, "error": "file_content is required."}

    # Check size limits
    content_bytes = len(file_content.encode("utf-8"))
    if content_bytes > MAX_SKILL_FILE_BYTES:
        return {
            "success": False,
            "error": f"File content is {content_bytes:,} bytes (limit: {MAX_SKILL_FILE_BYTES:,} bytes / 1 MiB).",
        }

    existing = _find_skill(name)
    if not existing:
        return {"success": False, "error": _skill_not_found_error(name)}

    target, err = _resolve_skill_target(existing["path"], file_path)
    if err:
        return {"success": False, "error": err}

    target.parent.mkdir(parents=True, exist_ok=True)

    # Back up for rollback
    original_content = target.read_text(encoding="utf-8") if target.exists() else None
    _atomic_write_text(target, file_content)

    # Security scan — roll back on block
    scan_error = _security_scan_skill(existing["path"])
    if scan_error:
        if original_content is not None:
            _atomic_write_text(target, original_content)
        else:
            target.unlink(missing_ok=True)
        return {"success": False, "error": scan_error}

    return {
        "success": True,
        "message": f"File '{file_path}' written to skill '{name}'.",
        "path": str(target),
    }


def _remove_file(name: str, file_path: str) -> Dict[str, Any]:
    """Remove a supporting file from a skill directory."""
    err = _validate_file_path(file_path)
    if err:
        return {"success": False, "error": err}

    existing = _find_skill(name)
    if not existing:
        return {"success": False, "error": _skill_not_found_error(name)}

    skill_dir = existing["path"]
    target, err = _resolve_skill_target(skill_dir, file_path)
    if err:
        return {"success": False, "error": err}

    if not target.exists():
        return {"success": False, "error": f"File '{file_path}' not found in skill '{name}'."}

    target.unlink()

    # Clean up empty subdirectories
    parent = target.parent
    if parent != skill_dir and parent.exists():
        try:
            if not any(parent.iterdir()):
                parent.rmdir()
        except Exception:
            pass

    return {
        "success": True,
        "message": f"File '{file_path}' removed from skill '{name}'.",
    }


# ── Main entry point ─────────────────────────────────────────────────────

def skill_manage(
    action: str,
    name: str,
    content: str = None,
    category: str = None,
    file_path: str = None,
    file_content: str = None,
    old_string: str = None,
    new_string: str = None,
    replace_all: bool = False,
    absorbed_into: str = None,
) -> str:
    """
    Manage skills. Dispatches to the appropriate action handler.

    Actions:
        create: Create a new skill (requires content)
        edit: Full rewrite of SKILL.md (requires content)
        patch: Find and replace in SKILL.md (requires old_string, new_string)
        delete: Delete a skill
        write_file: Add/overwrite a supporting file (requires file_path, file_content)
        remove_file: Remove a supporting file (requires file_path)

    Returns JSON string with results.
    """
    if action == "create":
        if not content:
            return json.dumps({"success": False, "error": "content is required for 'create'."}, ensure_ascii=False)
        result = _create_skill(name, content, category)

    elif action == "edit":
        if not content:
            return json.dumps({"success": False, "error": "content is required for 'edit'."}, ensure_ascii=False)
        result = _edit_skill(name, content)

    elif action == "patch":
        if not old_string:
            return json.dumps({"success": False, "error": "old_string is required for 'patch'."}, ensure_ascii=False)
        if new_string is None:
            return json.dumps({"success": False, "error": "new_string is required for 'patch'."}, ensure_ascii=False)
        result = _patch_skill(name, old_string, new_string, file_path, replace_all)

    elif action == "delete":
        result = _delete_skill(name, absorbed_into=absorbed_into)

    elif action == "write_file":
        if not file_path:
            return json.dumps({"success": False, "error": "file_path is required for 'write_file'."}, ensure_ascii=False)
        if file_content is None:
            return json.dumps({"success": False, "error": "file_content is required for 'write_file'."}, ensure_ascii=False)
        result = _write_file(name, file_path, file_content)

    elif action == "remove_file":
        if not file_path:
            return json.dumps({"success": False, "error": "file_path is required for 'remove_file'."}, ensure_ascii=False)
        result = _remove_file(name, file_path)

    else:
        result = {"success": False, "error": f"Unknown action '{action}'. Use: create, edit, patch, delete, write_file, remove_file"}

    # Clear skill cache on success
    if result.get("success"):
        try:
            from agent.prompt_builder import clear_skills_system_prompt_cache
            clear_skills_system_prompt_cache(clear_snapshot=True)
        except Exception:
            pass

    return json.dumps(result, ensure_ascii=False)


# ── OpenAI Function-Calling Schema ────────────────────────────────────────

SKILL_MANAGE_SCHEMA = {
    "name": "skill_manage",
    "description": (
        "Manage skills (create, update, delete). Skills are procedural "
        "memory — reusable approaches for recurring task types.\n\n"
        "Actions: create (full SKILL.md + optional category), "
        "patch (old_string/new_string — preferred for fixes), "
        "edit (full SKILL.md rewrite — major overhauls only), "
        "delete, write_file, remove_file.\n\n"
        "Good skills: trigger conditions, numbered steps with exact commands, "
        "pitfalls section, verification steps."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "patch", "edit", "delete", "write_file", "remove_file"],
                "description": "The action to perform."
            },
            "name": {
                "type": "string",
                "description": "Skill name (lowercase, hyphens/underscores, max 64 chars)."
            },
            "content": {
                "type": "string",
                "description": "Full SKILL.md content (YAML frontmatter + markdown body). Required for 'create' and 'edit'."
            },
            "old_string": {
                "type": "string",
                "description": "Text to find (required for 'patch')."
            },
            "new_string": {
                "type": "string",
                "description": "Replacement text (required for 'patch')."
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default: false)."
            },
            "category": {
                "type": "string",
                "description": "Optional category for organizing skills (e.g., 'bid-analysis', 'kg-tools')."
            },
            "file_path": {
                "type": "string",
                "description": "Path to a supporting file (e.g., 'references/api.md')."
            },
            "file_content": {
                "type": "string",
                "description": "Content for the file. Required for 'write_file'."
            },
            "absorbed_into": {
                "type": "string",
                "description": "For 'delete': skill name that absorbed this skill's content."
            },
        },
        "required": ["action", "name"],
    },
}


# ── Registration ──────────────────────────────────────────────────────────

from tools.registry import registry

registry.register(
    name="skill_manage",
    toolset="skills",
    schema=SKILL_MANAGE_SCHEMA,
    handler=lambda args: skill_manage(**args),
    emoji="🛠️",
)
