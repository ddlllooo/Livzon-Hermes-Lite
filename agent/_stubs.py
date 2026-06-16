"""Consolidated stubs for agent modules removed during LeadFlow trimming.

Every function here is a safe no-op. Original modules were 1-15 line stubs
left over from the Hermes Agent → LeadFlow trim. Consolidated into one file
to reduce file count while preserving import compatibility.
"""


def is_token_provider(*a, **kw):
    """Stub: azure_identity_adapter."""
    return False


def maybe_schedule_background_review(*a, **kw):
    """Stub: background_review."""
    pass


def summarize_background_review_actions(*a, **kw):
    """Stub: background_review."""
    return ""


def spawn_background_review_thread(*a, **kw):
    """Stub: background_review."""
    pass


def build_memory_write_metadata(*a, **kw):
    """Stub: background_review."""
    return {}


def has_aws_credentials(*a, **kw):
    """Stub: bedrock_adapter."""
    return False


def resolve_bedrock_region(*a, **kw):
    """Stub: bedrock_adapter."""
    return None


def get_bedrock_context_length(*a, **kw):
    """Stub: bedrock_adapter."""
    return 0


def get_bedrock_auth(*a, **kw):
    """Stub: bedrock_adapter."""
    return None


def _summarize_user_message_for_log(*a, **kw):
    """Stub: codex_responses_adapter."""
    return ""


def run_codex_stream(*a, **kw):
    """Stub: codex_runtime."""
    raise NotImplementedError("Codex not available in LeadFlow")


def run_codex_create_stream_fallback(*a, **kw):
    """Stub: codex_runtime."""
    raise NotImplementedError("Codex not available in LeadFlow")


def run_codex_app_server_turn(*a, **kw):
    """Stub: codex_runtime."""
    raise NotImplementedError("Codex not available in LeadFlow")


def _consume_codex_event_stream(*a, **kw):
    """Stub: codex_runtime."""
    raise NotImplementedError("Codex not available in LeadFlow")


class CopilotACPClient:
    """Stub: copilot_acp_client."""
    pass


def seed_credits_at_session_start(*a, **kw):
    """Stub: credits_tracker."""
    pass


def dev_fixture_credits_state(*a, **kw):
    """Stub: credits_tracker."""
    pass


def parse_credits_headers(*a, **kw):
    """Stub: credits_tracker."""
    pass


def evaluate_credits_notices(*a, **kw):
    """Stub: credits_tracker."""
    pass


class GeminiCloudCodeClient:
    """Stub: gemini_cloudcode_adapter."""
    pass


class GeminiNativeClient:
    """Stub: gemini_native_adapter."""
    pass


class AsyncGeminiNativeClient:
    """Stub: gemini_native_adapter."""
    pass


def is_native_gemini_base_url(*a, **kw):
    """Stub: gemini_native_adapter."""
    return False


def _lookup_supports_vision(*a, **kw):
    """Stub: image_routing."""
    return False


def lookup_models_dev_context(*a, **kw):
    """Stub: models_dev."""
    return 0


def is_moonshot_model(*a, **kw):
    """Stub: moonshot_schema."""
    return False


def sanitize_moonshot_tools(*a, **kw):
    """Stub: moonshot_schema."""
    return a[0] if a else []


def nous_rate_limit_remaining(*a, **kw):
    """Stub: nous_rate_guard."""
    return -1


def clear_nous_rate_limit(*a, **kw):
    """Stub: nous_rate_guard."""
    pass


def get_nous_rate_limit_info(*a, **kw):
    """Stub: nous_rate_guard."""
    return None


def estimate_usage_cost(*a, **kw):
    """Stub: usage_pricing."""
    return {}


def normalize_usage(*a, **kw):
    """Stub: usage_pricing."""
    return a[0] if a else {}


# ── Additional stubs (background review prompts) ──
_COMBINED_REVIEW_PROMPT = ""
_MEMORY_REVIEW_PROMPT = ""
_SKILL_REVIEW_PROMPT = ""


# ── Codex helpers ──
def _derive_responses_function_call_id(*a, **kw):
    return ""


def _deterministic_call_id(*a, **kw):
    return ""


def _split_responses_tool_id(*a, **kw):
    return ("", "")


# ── Bedrock ──
def _get_bedrock_runtime_client(*a, **kw):
    return None


def invalidate_runtime_client(*a, **kw):
    pass


def stream_converse_with_callbacks(*a, **kw):
    raise NotImplementedError("Bedrock not available in LeadFlow")


def normalize_converse_response(*a, **kw):
    return {}


# ── Rate limit helpers ──
def format_remaining(*a, **kw):
    return ""


def is_genuine_nous_rate_limit(*a, **kw):
    return False


def record_nous_rate_limit(*a, **kw):
    pass


def is_stale_connection_error(*a, **kw):
    return False
