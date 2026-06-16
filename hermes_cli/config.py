"""Stub for hermes_cli.config - provides essential config functions."""
import os
import yaml
from pathlib import Path

_CONFIG_CACHE = None
_ENV_LOADED = False

def get_hermes_home():
    """Return the Hermes home directory as a Path object."""
    from pathlib import Path
    return Path(os.environ.get("HERMES_HOME", os.path.join(os.path.expanduser("~"), ".hermes")))

def ensure_hermes_home() -> str:
    """Ensure hermes home exists and return it."""
    home = get_hermes_home()
    os.makedirs(home, exist_ok=True)
    return home

def get_config_path() -> str:
    """Return the config.yaml path."""
    return os.path.join(get_hermes_home(), "config.yaml")

def get_env_path() -> str:
    """Return the .env path."""
    return os.path.join(get_hermes_home(), ".env")

def load_config(**kwargs) -> dict:
    """Load and return config dict. Cached after first load."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    cfg_path = get_config_path()
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                _CONFIG_CACHE = yaml.safe_load(f) or {}
        except Exception:
            _CONFIG_CACHE = {}
    else:
        _CONFIG_CACHE = {}
    return _CONFIG_CACHE

def load_env(*args, **kwargs):
    """Load .env file. No-op in slim mode."""
    global _ENV_LOADED
    if not _ENV_LOADED:
        try:
            from dotenv import load_dotenv
            load_dotenv(get_env_path(), override=False)
        except Exception:
            pass
        _ENV_LOADED = True

def read_raw_config(**kwargs) -> dict:
    """Read raw config without merging."""
    return load_config(**kwargs)

def cfg_get(key: str, default=None, **kwargs):
    """Get a config value by dot-separated key."""
    cfg = load_config(**kwargs)
    parts = key.split(".")
    val = cfg
    for part in parts:
        if isinstance(val, dict):
            val = val.get(part)
        else:
            return default
        if val is None:
            return default
    return val

def get_config_value(key: str, default=None):
    """Alias for cfg_get."""
    return cfg_get(key, default)

def remove_env_value(*args, **kwargs):
    """Stub - no-op."""
    pass

def is_managed() -> bool:
    """Check if running in managed mode."""
    return False

def get_compatible_custom_providers(**kwargs) -> list:
    """Return list of custom provider names."""
    return []

def get_custom_provider_context_length(*args, **kwargs) -> int:
    """Return context length for custom provider."""
    return 0

OPTIONAL_ENV_VARS = []
