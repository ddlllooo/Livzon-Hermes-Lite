"""Stub for tool_search."""

TOOL_CALL_NAME = "tool_call"


def assemble_tool_defs(*args, **kwargs):
    return []


def load_config(*args, **kwargs):
    return {}


def is_bridge_tool(*args, **kwargs):
    return False


def resolve_underlying_call(*args, **kwargs):
    return None, None, "tool_search is disabled"


def scoped_deferrable_names(*args, **kwargs):
    return frozenset()
