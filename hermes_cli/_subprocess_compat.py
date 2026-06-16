"""Stub for hermes_cli._subprocess_compat."""
import subprocess

def windows_hide_flags():
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        return subprocess.CREATE_NO_WINDOW
    return 0
