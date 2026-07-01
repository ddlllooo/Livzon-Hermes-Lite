"""Stub: terminal execution disabled for LeadFlow Agent Core.

This module was intentionally emptied during security hardening.
All functions are safe no-ops.
"""


def cleanup_vm(*a, **kw):
    pass


def is_persistent_env(*a, **kw):
    return False


def get_active_env(*a, **kw):
    return None


def _get_env_config(*a, **kw):
    return {}


def _rewrite_compound_background(*a, **kw):
    return a[0] if a else ""


def _transform_sudo_command(*a, **kw):
    return a[0] if a else ""


_active_environments = {}


class _TerminalEnv:
    """Stub terminal environment."""
    def __init__(self, *a, **kw):
        self.cwd = None
    def execute(self, *a, **kw):
        return {"output": "", "exit_code": 1}
    def cleanup(self, *a, **kw):
        pass


def _get_approval_callback(*a, **kw):
    return None


def set_approval_callback(*a, **kw):
    pass


def _get_sudo_password_callback(*a, **kw):
    return None


def set_sudo_password_callback(*a, **kw):
    pass


def _prompt_for_sudo_password(*a, **kw):
    return ""


def terminal_tool(*a, **kw):
    return {"error": "Terminal not available in LeadFlow Agent Core", "exit_code": 1}
