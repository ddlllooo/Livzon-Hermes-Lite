"""Stub for hermes_cli.auth - LeadFlow Agent Core.

All functions are safe no-ops for a standalone deployment without
Nous Portal, Codex, Copilot, or other OAuth-based providers.
"""

import threading

# ── Constants ──
CODEX_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120
DEFAULT_XAI_OAUTH_BASE_URL = "https" + "://api.x.ai"
NOUS_DEVICE_CODE_SOURCE = "leadflow"
XAI_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120
PROVIDER_REGISTRY = {}

# ── Thread lock ──
_auth_lock = threading.Lock()


class AuthError(Exception):
    pass


def _auth_store_lock():
    return _auth_lock


# ── Auth store ──
def _load_auth_store(*a, **kw):
    return {}


def _save_auth_store(*a, **kw):
    pass


# ── Provider state ──
def _load_provider_state(*a, **kw):
    return {}


def _save_provider_state(*a, **kw):
    pass


def _store_provider_state(*a, **kw):
    pass


# ── Credential pool ──
def read_credential_pool(*a, **kw):
    return []


def write_credential_pool(*a, **kw):
    pass


# ── JWT / token ──
def _decode_jwt_claims(*a, **kw):
    return {}


def _codex_access_token_is_expiring(*a, **kw):
    return False


def _xai_access_token_is_expiring(*a, **kw):
    return False


def refresh_codex_oauth_pure(*a, **kw):
    return None


def refresh_xai_oauth_pure(*a, **kw):
    return None


def _is_terminal_codex_oauth_refresh_error(*a, **kw):
    return True


def _is_terminal_nous_refresh_error(*a, **kw):
    return True


def _is_terminal_xai_oauth_refresh_error(*a, **kw):
    return True


def _quarantine_nous_oauth_state(*a, **kw):
    pass


def _quarantine_nous_pool_entries(*a, **kw):
    pass


# ── Resolution ──
def resolve_nous_runtime_credentials(*a, **kw):
    return None


def resolve_codex_runtime_credentials(*a, **kw):
    return None


def resolve_xai_oauth_runtime_credentials(*a, **kw):
    return None


def resolve_nous_access_token(*a, **kw):
    return None


def resolve_api_key_provider_credentials(*a, **kw):
    return None


def resolve_qwen_runtime_credentials(*a, **kw):
    return None


def resolve_external_process_provider_credentials(*a, **kw):
    return None


# ── Provider queries ──
def get_provider_auth_state(*a, **kw):
    return {}


def is_provider_explicitly_configured(*a, **kw):
    return False


def is_source_suppressed(*a, **kw):
    return False


def suppress_credential_source(*a, **kw):
    pass


def _nous_invoke_jwt_is_usable(*a, **kw):
    return False


def _read_codex_tokens(*a, **kw):
    return None


def _resolve_kimi_base_url(*a, **kw):
    return None


def _resolve_zai_base_url(*a, **kw):
    return None


def _xai_validate_inference_base_url(*a, **kw):
    return None


def build_minimax_oauth_token_provider(*a, **kw):
    return None
