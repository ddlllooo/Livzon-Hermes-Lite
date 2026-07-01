"""Consolidated stubs for agent modules removed during LeadFlow trimming.

Every function here is a safe no-op. Original modules were 1-15 line stubs
left over from the Hermes Agent → LeadFlow trim. Consolidated into one file
to reduce file count while preserving import compatibility.
"""

from dataclasses import dataclass
from typing import Any


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


@dataclass(frozen=True)
class UsageCostResult:
    amount_usd: float | None = None
    status: str = "unknown"
    source: str = "stub"


@dataclass(frozen=True)
class CanonicalUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0


def _usage_get(usage: Any, key: str, default: int = 0) -> int:
    if usage is None:
        return default
    if isinstance(usage, dict):
        value = usage.get(key, default)
    else:
        value = getattr(usage, key, default)
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def estimate_usage_cost(*a, **kw):
    """Stub: usage_pricing."""
    return UsageCostResult()


def normalize_usage(*a, **kw):
    """Stub: usage_pricing."""
    usage = a[0] if a else None
    prompt_tokens = _usage_get(usage, "prompt_tokens") or _usage_get(usage, "input_tokens")
    completion_tokens = _usage_get(usage, "completion_tokens") or _usage_get(usage, "output_tokens")
    total_tokens = _usage_get(usage, "total_tokens") or (prompt_tokens + completion_tokens)

    prompt_details = _usage_get(usage, "prompt_tokens_details", {})
    completion_details = _usage_get(usage, "completion_tokens_details", {})
    if not isinstance(prompt_details, dict) and hasattr(prompt_details, "model_dump"):
        prompt_details = prompt_details.model_dump()
    if not isinstance(completion_details, dict) and hasattr(completion_details, "model_dump"):
        completion_details = completion_details.model_dump()

    cache_read_tokens = 0
    reasoning_tokens = 0
    if isinstance(prompt_details, dict):
        cache_read_tokens = _usage_get(prompt_details, "cached_tokens")
    if isinstance(completion_details, dict):
        reasoning_tokens = _usage_get(completion_details, "reasoning_tokens")

    return CanonicalUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=0,
        reasoning_tokens=reasoning_tokens,
    )


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
