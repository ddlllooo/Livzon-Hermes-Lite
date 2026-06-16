"""Stub for vision_tools."""

def vision_analyze_tool(*args, **kwargs):
    raise NotImplementedError("Vision not available in LeadFlow Agent Core.")

def _resize_image_for_vision(*args, **kwargs):
    return args[0] if args else None
