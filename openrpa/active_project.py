"""Shared, local pointer to the project currently open in the Studio desktop app."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


def active_project_file() -> Path:
    override = os.environ.get("OPENRPA_ACTIVE_PROJECT_FILE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "OpenRPAStudio" / "active-project.json"


def publish_active_project(root: str | Path) -> Path:
    """Atomically publish a project root selected by the local Studio app."""
    target = active_project_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "format": "openrpa.active-project",
        "formatVersion": 1,
        "root": str(Path(root).expanduser().resolve()),
        "updatedAt": time.time(),
    }
    fd, temporary = tempfile.mkstemp(prefix=".active-project-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def read_active_project() -> Path | None:
    """Read the current Studio project pointer; the caller validates the project."""
    target = active_project_file()
    try:
        raw = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    if len(raw.encode("utf-8")) > 16_384:
        raise ValueError("Studio active-project pointer exceeds 16 KB")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Studio active-project pointer is malformed") from exc
    if (not isinstance(payload, dict)
            or payload.get("format") != "openrpa.active-project"
            or payload.get("formatVersion") != 1
            or not isinstance(payload.get("root"), str)
            or not payload["root"].strip()):
        raise ValueError("Studio active-project pointer has an unsupported format")
    return Path(payload["root"]).expanduser().resolve()
