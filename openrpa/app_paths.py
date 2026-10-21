"""Paths shared with the installed Tauri desktop application."""
from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    """Return Tauri's app-data directory for identifier org.openrpa.studio."""
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "org.openrpa.studio"
    if sys_platform() == "darwin":
        return Path.home() / "Library" / "Application Support" / "org.openrpa.studio"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "org.openrpa.studio"


def sys_platform() -> str:
    # Kept behind a tiny helper to make platform path behavior easy to test.
    import sys
    return sys.platform
