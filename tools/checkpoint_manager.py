"""No-op checkpoint manager for Hermes-Lite service deployments.

Hermes-Lite removes local file mutation tools from the default Dazah service
surface, but the retained agent loop still calls checkpoint hooks. This class
keeps that interface intact while doing no filesystem snapshot work.
"""

from pathlib import Path

class CheckpointManager:
    def __init__(self, enabled: bool = False, *args, **kwargs):
        self.enabled = bool(enabled)

    def new_turn(self) -> None:
        return None

    def ensure_checkpoint(self, *args, **kwargs) -> None:
        return None

    def get_working_dir_for_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        return candidate if candidate.is_dir() else candidate.parent

    def checkpoint(self, *args, **kwargs):
        return None

    def rollback(self, *args, **kwargs):
        return None
