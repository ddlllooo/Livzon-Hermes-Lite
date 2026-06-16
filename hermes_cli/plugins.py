"""Stub for hermes_cli.plugins."""

def discover_plugins(*args, **kwargs):
    return {}

def has_hook(*args, **kwargs):
    return False

def invoke_hook(*args, **kwargs):
    pass

def get_pre_tool_call_block_message(*args, **kwargs):
    return None

def get_plugin_auxiliary_tasks(*args, **kwargs):
    return None

def get_plugin_context_engine(*args, **kwargs):
    return None

def _ensure_plugins_discovered(*args, **kwargs):
    pass
