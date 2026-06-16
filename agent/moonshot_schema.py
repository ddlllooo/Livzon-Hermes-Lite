"""Stub for moonshot_schema."""

def is_moonshot_model(*args, **kwargs):
    return False

def sanitize_moonshot_tools(*args, **kwargs):
    return args[0] if args else []
