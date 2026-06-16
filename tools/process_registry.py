"""Stub for process_registry."""

class _ProcessRegistry:
    def register(self, *args, **kwargs):
        pass
    def unregister(self, *args, **kwargs):
        pass
    def list_processes(self):
        return []

process_registry = _ProcessRegistry()
