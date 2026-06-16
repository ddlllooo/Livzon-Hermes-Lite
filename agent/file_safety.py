"""File safety utilities for LeadFlow Agent Core.

Trimmed to only include _resolve_active_profile_name (used by system_prompt.py).
"""

from pathlib import Path
from typing import Optional


def _hermes_home_path() -> Path:
    """Return the resolved HERMES_HOME path."""
    from hermes_constants import get_hermes_home
    return Path(str(get_hermes_home()))


def _hermes_root_path() -> Path:
    """Return the Hermes root (~/.hermes or equivalent)."""
    return _hermes_home_path().parent if "profiles" in str(_hermes_home_path()) else _hermes_home_path()


def _resolve_active_profile_name() -> str:
    """Return the active profile name derived from HERMES_HOME."""
    try:
        home_real = _hermes_home_path().resolve()
        root_real = _hermes_root_path().resolve()
    except (OSError, RuntimeError):
        return "default"
    profiles_dir = root_real / "profiles"
    try:
        rel = home_real.relative_to(profiles_dir)
        parts = rel.parts
        if len(parts) >= 1:
            return parts[0]
    except ValueError:
        pass
    return "default"
