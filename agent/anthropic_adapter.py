"""Stub for anthropic_adapter - LeadFlow uses OpenAI-compatible only."""

def build_anthropic_client(*args, **kwargs):
    raise NotImplementedError("Anthropic native API not available in LeadFlow Agent Core. Use OpenAI-compatible provider.")

def build_anthropic_bedrock_client(*args, **kwargs):
    raise NotImplementedError("Bedrock not available in LeadFlow Agent Core.")

def build_anthropic_kwargs(*args, **kwargs):
    return {}

def resolve_anthropic_token(*args, **kwargs):
    return None

def resolve_anthropic_to(*args, **kwargs):
    return None

def _is_oauth_token(*args, **kwargs):
    return False

def _forbids_sampling_params(*args, **kwargs):
    return False

def _get_anthropic_max_output(*args, **kwargs):
    return 4096

def read_claude_code_credentials(*args, **kwargs):
    return None

def refresh_anthropic_oauth_pure(*args, **kwargs):
    return None

def _write_claude_code_credentials(*args, **kwargs):
    pass

def read_hermes_oauth(*args, **kwargs):
    return None
