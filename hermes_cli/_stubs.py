"""Consolidated stubs for hermes_cli modules removed during LeadFlow trimming."""


def windows_hide_flags():
    """Stub: _subprocess_compat."""
    import subprocess
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0


def copilot_request_headers(*a, **kw):
    """Stub: copilot_auth."""
    return {}


def resolve_copilot_token(*a, **kw):
    """Stub: copilot_auth."""
    return None


def get_copilot_api_token(*a, **kw):
    """Stub: copilot_auth."""
    return None


def get_secret_source(*a, **kw):
    """Stub: env_loader."""
    return None


def normalize_model_for_provider(model, *a, **kw):
    """Stub: model_normalize."""
    return model


def get_nous_portal_account_info(*a, **kw):
    """Stub: nous_account."""
    return None


def get_nous_portal_credits(*a, **kw):
    """Stub: nous_account."""
    return None


def get_nous_subscription_features(*a, **kw):
    """Stub: nous_subscription."""
    return {}


def get_active_profile_name() -> str:
    """Stub: profiles."""
    return "default"


def determine_api_mode(*a, **kw):
    """Stub: providers."""
    return "chat_completions"


def resolve_runtime_provider(*a, **kw):
    """Stub: runtime_provider."""
    return None


def _resolve_azure_foundry_runtime(*a, **kw):
    """Stub: runtime_provider."""
    return None


def _get_named_custom_provider(*a, **kw):
    """Stub: runtime_provider."""
    return None


def get_active_skin(*a, **kw):
    """Stub: skin_engine."""
    return {}


def get_provider_request_timeout(*a, **kw):
    """Stub: timeouts."""
    return 1800


def get_provider_stale_timeout(*a, **kw):
    """Stub: timeouts."""
    return 600


# gateway stubs
class _PlatformRegistry:
    """Stub: gateway.platform_registry."""
    def get(self, *a, **kw):
        return None


platform_registry = _PlatformRegistry()


_UNSET = object()
_VAR_MAP = {}


def set_current_session_id(*a, **kw):
    """Stub: gateway.session_context."""
    pass


def get_session_env(key, default=""):
    """Stub: gateway.session_context."""
    import os
    return os.environ.get(key, default)
