"""Select the platform accessibility adapter behind one workflow interface."""
from __future__ import annotations

import sys
from typing import Any


def _adapter() -> Any:
    if sys.platform == "win32":
        from . import windows_uia
        return windows_uia
    if sys.platform.startswith("linux"):
        from . import linux_atspi
        return linux_atspi
    raise RuntimeError(f"Semantic desktop accessibility is not implemented for {sys.platform}")


def status() -> dict[str, Any]:
    try:
        return _adapter().status()
    except Exception as exc:
        return {"available": False, "adapter": "Desktop accessibility", "reason": f"Adapter probe failed: {type(exc).__name__}: {exc}"}


def list_windows(limit: int = 200) -> list[dict[str, Any]]:
    return _adapter().list_windows(limit)


def list_controls(window_title: str, process_id: int | None = None, limit: int = 300) -> list[dict[str, Any]]:
    return _adapter().list_controls(window_title, process_id, limit)


def click(window_title: str, name: str | None, automation_id: str | None,
          control_type: str | None, process_id: int | None = None) -> None:
    _adapter().click(window_title, name, automation_id, control_type, process_id)


def fill(window_title: str, name: str | None, automation_id: str | None,
         control_type: str | None, value: str, process_id: int | None = None) -> None:
    _adapter().fill(window_title, name, automation_id, control_type, value, process_id)


def read_text(window_title: str, name: str | None, automation_id: str | None,
              control_type: str | None, process_id: int | None = None) -> str:
    return _adapter().read_text(window_title, name, automation_id, control_type, process_id)


def control_state(window_title: str, name: str | None, automation_id: str | None,
                  control_type: str | None, process_id: int | None = None) -> dict[str, bool] | None:
    return _adapter().control_state(window_title, name, automation_id, control_type, process_id)
