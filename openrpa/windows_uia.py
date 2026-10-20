"""Bounded, exact-match helpers for Windows UI Automation controls."""
from __future__ import annotations

import sys
from typing import Any


class UIAutomationError(RuntimeError):
    """A selector could not be resolved safely through Windows UIA."""


def _is_password(control: Any) -> bool:
    """Read the UIA IsPassword property directly; fail closed for Edit controls."""
    try:
        return bool(control.element_info.element.CurrentIsPassword)
    except Exception:
        return str(getattr(control.element_info, "control_type", "")) == "Edit"


def _desktop() -> Any:
    if sys.platform != "win32":
        raise UIAutomationError("Windows UI Automation is available only on Windows")
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise UIAutomationError("Install the optional desktop extra to enable Windows UI Automation") from exc
    return Desktop(backend="uia")


def _title(window: Any) -> str:
    try:
        return str(window.window_text()).strip()
    except Exception:
        return ""


def _window(window_title: str, process_id: int | None = None) -> Any:
    if not isinstance(window_title, str) or not window_title.strip() or len(window_title) > 512:
        raise UIAutomationError("windowTitle must be an exact visible window title of 1–512 characters")
    candidates = [window for window in _desktop().windows(visible_only=True, top_level_only=True)
                  if _title(window) == window_title]
    if process_id is not None:
        candidates = [window for window in candidates if int(window.element_info.process_id) == process_id]
    if not candidates:
        raise UIAutomationError(f"No visible window matched the exact title {window_title!r}")
    if len(candidates) != 1:
        raise UIAutomationError(f"The window title {window_title!r} matched {len(candidates)} windows; specify processId")
    return candidates[0]


def _criteria(name: str | None, automation_id: str | None, control_type: str | None) -> dict[str, str]:
    criteria: dict[str, str] = {}
    if isinstance(name, str) and name.strip():
        if len(name) > 512:
            raise UIAutomationError("name must not exceed 512 characters")
        criteria["title"] = name
    if isinstance(automation_id, str) and automation_id.strip():
        if len(automation_id) > 512:
            raise UIAutomationError("automationId must not exceed 512 characters")
        criteria["auto_id"] = automation_id
    if isinstance(control_type, str) and control_type.strip():
        if len(control_type) > 128:
            raise UIAutomationError("controlType must not exceed 128 characters")
        criteria["control_type"] = control_type
    if not ("title" in criteria or "auto_id" in criteria):
        raise UIAutomationError("Specify an accessible name or Automation ID to identify the control")
    return criteria


def _find_controls(window: Any, criteria: dict[str, str]) -> list[Any]:
    """Use pywinauto's UIA-aware Automation ID filter (UIA descendants omit it)."""
    from pywinauto.findwindows import find_elements
    elements = find_elements(parent=window, top_level_only=False, visible_only=True,
                             backend="uia", **criteria)
    return [window.backend.generic_wrapper_class(element) for element in elements]


def _control(window_title: str, name: str | None, automation_id: str | None,
             control_type: str | None, process_id: int | None = None) -> Any:
    window = _window(window_title, process_id)
    criteria = _criteria(name, automation_id, control_type)
    try:
        matches = _find_controls(window, criteria)
    except Exception as exc:
        raise UIAutomationError(f"Windows UIA could not inspect controls in {window_title!r}: {type(exc).__name__}: {exc}") from exc
    if not matches:
        selector = ", ".join(f"{key}={value!r}" for key, value in criteria.items())
        raise UIAutomationError(f"No control matched {selector} in window {window_title!r}")
    if len(matches) != 1:
        raise UIAutomationError(f"Control selector is ambiguous: {len(matches)} matches in window {window_title!r}; add Automation ID or control type")
    return matches[0]


def _process_id(window: Any) -> int:
    return int(window.element_info.process_id)


def list_windows(limit: int = 200) -> list[dict[str, Any]]:
    """Return visible top-level window identity only; never read control values."""
    result = []
    for window in _desktop().windows(visible_only=True, top_level_only=True):
        title = _title(window)
        if not title:
            continue
        result.append({"title": title[:512], "processId": _process_id(window),
                       "controlType": str(getattr(window.element_info, "control_type", "Window"))})
        if len(result) >= max(1, min(int(limit), 200)):
            break
    return result


def list_controls(window_title: str, process_id: int | None = None, limit: int = 300) -> list[dict[str, Any]]:
    """List interactive controls, filtering passwords and omitting all values."""
    window = _window(window_title, process_id)
    allowed = {"Button", "Edit", "ComboBox", "CheckBox", "RadioButton", "TabItem", "MenuItem",
               "Hyperlink", "ListItem", "TreeItem", "Slider", "Spinner", "SplitButton"}
    grouped: dict[tuple[str, str, str], int] = {}
    objects: list[tuple[Any, tuple[str, str, str]]] = []
    for control in window.descendants():
        info = control.element_info
        control_type = str(getattr(info, "control_type", ""))
        try:
            visible=bool(control.is_visible())
        except Exception:
            visible=False
        if not visible or control_type not in allowed or _is_password(control):
            continue
        name = str(getattr(info, "name", "") or "").strip()[:512]
        automation_id = str(getattr(info, "automation_id", "") or "").strip()[:512]
        if not name and not automation_id:
            continue
        signature = (control_type, name, automation_id)
        grouped[signature] = grouped.get(signature, 0) + 1
        objects.append((control, signature))
        if len(objects) >= max(1, min(int(limit), 300)):
            break
    return [{"name": signature[1], "automationId": signature[2], "controlType": signature[0],
             "matchCount": grouped[signature], "enabled": bool(getattr(control, "is_enabled", lambda: False)())}
            for control, signature in objects]


def click(window_title: str, name: str | None, automation_id: str | None,
          control_type: str | None, process_id: int | None = None) -> None:
    _control(window_title, name, automation_id, control_type, process_id).click_input()


def fill(window_title: str, name: str | None, automation_id: str | None,
         control_type: str | None, value: str, process_id: int | None = None) -> None:
    control = _control(window_title, name, automation_id, control_type, process_id)
    actual_type = str(getattr(control.element_info, "control_type", ""))
    if actual_type != "Edit":
        raise UIAutomationError(f"Set Text requires an Edit control; matched {actual_type or 'unknown'}")
    control.set_edit_text(value)


def read_text(window_title: str, name: str | None, automation_id: str | None,
              control_type: str | None, process_id: int | None = None) -> str:
    control = _control(window_title, name, automation_id, control_type, process_id)
    if _is_password(control):
        raise UIAutomationError("Reading password controls is blocked")
    try:
        value = control.get_value()
    except Exception:
        value = control.window_text()
    return str(value)


def control_state(window_title: str, name: str | None, automation_id: str | None,
                  control_type: str | None, process_id: int | None = None) -> dict[str, bool] | None:
    """Return safe state flags, or None while a uniquely named control is absent."""
    try:
        control = _control(window_title, name, automation_id, control_type, process_id)
    except UIAutomationError as exc:
        message = str(exc)
        if message.startswith("No visible window matched") or message.startswith("No control matched"):
            return None
        raise
    return {"exists": True, "visible": bool(control.is_visible()), "enabled": bool(control.is_enabled())}


def status() -> dict[str, Any]:
    if sys.platform != "win32":
        return {"available": False, "adapter": "Windows UI Automation", "reason": "This adapter is Windows-only"}
    try:
        _desktop()
        return {"available": True, "adapter": "Windows UI Automation (UIA)", "reason": None}
    except Exception as exc:
        return {"available": False, "adapter": "Windows UI Automation (UIA)",
                "reason": f"UIA runtime unavailable: {type(exc).__name__}: {exc}"}
