"""Semantic Linux desktop access through the system AT-SPI accessibility bus.

The adapter intentionally imports pyatspi only at runtime. On Linux this is
normally supplied by the distribution (for example python3-pyatspi), together
with an active graphical session and AT-SPI D-Bus service.
"""
from __future__ import annotations

import sys
from typing import Any, Iterator


class ATSPIError(RuntimeError):
    """An AT-SPI query or action could not be completed safely."""


def _module() -> Any:
    if not sys.platform.startswith("linux"):
        raise ATSPIError("AT-SPI desktop automation is available only on Linux")
    try:
        import pyatspi
    except ImportError as exc:
        raise ATSPIError("Install the distribution's python3-pyatspi package to enable AT-SPI") from exc
    return pyatspi


def _desktop() -> tuple[Any, Any]:
    api = _module()
    try:
        desktop = api.Registry.getDesktop(0)
        # Force one live D-Bus round trip so a present Python module is not
        # mistaken for a usable accessibility bus.
        desktop.getChildCount()
    except Exception as exc:
        raise ATSPIError(f"AT-SPI accessibility bus is unavailable: {type(exc).__name__}: {exc}") from exc
    return api, desktop


def _value(obj: Any, method: str, attribute: str | None = None, default: Any = "") -> Any:
    try:
        getter = getattr(obj, method, None)
        if callable(getter):
            return getter()
        if attribute:
            return getattr(obj, attribute)
    except Exception:
        return default
    return default


def _name(obj: Any) -> str:
    return str(_value(obj, "get_name", "name", "") or "").strip()


def _role(obj: Any) -> str:
    return str(_value(obj, "getRoleName", "roleName", "") or "").strip().lower().replace("_", " ")


def _pid(obj: Any) -> int:
    value = _value(obj, "get_process_id", "processID", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _children(obj: Any) -> Iterator[Any]:
    try:
        count = min(max(int(obj.getChildCount()), 0), 5000)
    except Exception:
        return
    for index in range(count):
        try:
            child = obj.getChildAtIndex(index)
            if child is not None:
                yield child
        except Exception:
            continue


def _walk(root: Any, maximum: int = 5000) -> Iterator[Any]:
    stack = list(reversed(list(_children(root))))
    visited = 0
    while stack and visited < maximum:
        node = stack.pop()
        visited += 1
        yield node
        stack.extend(reversed(list(_children(node))))
    if stack:
        raise ATSPIError(f"Accessibility tree exceeds the safe {maximum}-control selector limit")


def _window_role(role: str) -> bool:
    return role in {"frame", "window", "dialog", "alert"}


def _windows(api: Any, desktop: Any) -> list[Any]:
    result = []
    for application in _children(desktop):
        candidates = [application] if _window_role(_role(application)) else list(_children(application))
        for node in candidates:
            if _window_role(_role(node)) and _name(node):
                result.append(node)
    return result


def _state(obj: Any, names: tuple[str, ...]) -> bool:
    api = _module()
    states = obj.getState()
    for name in names:
        enum = getattr(api, name, None)
        if enum is not None:
            return bool(states.contains(enum))
    raise ATSPIError(f"This AT-SPI runtime does not expose required state {names[0]}")


def _attributes(obj: Any) -> dict[str, str]:
    try:
        value = obj.getAttributes()
        if isinstance(value, dict):
            return {str(key).lower(): str(item) for key, item in value.items()}
        result = {}
        for item in value or []:
            key, separator, content = str(item).partition(":")
            if separator:
                result[key.strip().lower()] = content.strip()
        return result
    except Exception:
        return {}


def _automation_id(obj: Any) -> str:
    attributes = _attributes(obj)
    return str(attributes.get("id") or attributes.get("automation-id") or attributes.get("automation_id") or "").strip()


def _interactive(role: str) -> bool:
    return role in {
        "push button", "toggle button", "check box", "radio button", "entry", "text",
        "combo box", "list box", "list item", "tree item", "page tab", "menu item",
        "link", "slider", "spin button", "password text", "label",
    }


def _editable(control: Any) -> bool:
    try:
        control.queryEditableText()
        return True
    except Exception:
        return False


def _control_type(control: Any) -> str:
    role = _role(control)
    if role == "entry" or (role == "text" and _editable(control)):
        return "Entry"
    return role.title()


def _actions(control: Any) -> list[str]:
    actions = []
    if _editable(control) and not _protected(_module(), control):
        actions.append("fill")
    if _role(control) in {"text", "label", "entry", "password text"}:
        actions.append("text")
    actions.append("wait")
    try:
        action = control.queryAction()
        for index in range(action.nActions):
            name = str(action.getName(index)).lower().replace("_", " ")
            if name in {"click", "press", "activate", "invoke"}:
                actions.insert(0, "click")
                break
    except Exception:
        pass
    return actions


def _protected(api: Any, control: Any) -> bool:
    role = _role(control)
    if "password" in role:
        return True
    attrs = _attributes(control)
    if attrs.get("password", "").lower() in {"true", "1", "yes"}:
        return True
    state = getattr(api, "STATE_PROTECTED", getattr(api, "STATE_PASSWORD_TEXT", None))
    if state is None:
        # AT-SPI versions commonly omit a PROTECTED state. Password fields use
        # a distinct PasswordText role or a toolkit-specific password attribute.
        return False
    try:
        return bool(control.getState().contains(state))
    except Exception:
        return False


def _visible(obj: Any) -> bool:
    return _state(obj, ("STATE_VISIBLE", "STATE_SHOWING"))


def _enabled(obj: Any) -> bool:
    return _state(obj, ("STATE_ENABLED",))


def list_windows(limit: int = 200) -> list[dict[str, Any]]:
    api, desktop = _desktop()
    result = []
    for window in _windows(api, desktop)[: max(1, min(int(limit), 200))]:
        try:
            if not _visible(window):
                continue
        except ATSPIError:
            continue
        result.append({"title": _name(window)[:512], "processId": _pid(window), "controlType": _role(window).title()})
    return result


def _window(window_title: str, process_id: int | None = None) -> tuple[Any, Any, Any]:
    if not isinstance(window_title, str) or not window_title.strip() or len(window_title) > 512:
        raise ATSPIError("windowTitle must be an exact accessible window name of 1–512 characters")
    api, desktop = _desktop()
    matches = [item for item in _windows(api, desktop)
               if _name(item) == window_title and (process_id is None or _pid(item) == int(process_id))]
    matches = [item for item in matches if _visible(item)]
    if not matches:
        raise ATSPIError(f"No accessible window matched the exact name {window_title!r}")
    if len(matches) != 1:
        raise ATSPIError(f"The window name {window_title!r} matched {len(matches)} windows; specify processId")
    return api, desktop, matches[0]


def _controls(window: Any, name: str | None, automation_id: str | None, control_type: str | None) -> list[Any]:
    if not (isinstance(name, str) and name.strip()) and not (isinstance(automation_id, str) and automation_id.strip()):
        raise ATSPIError("Specify an accessible name or AT-SPI id attribute to identify the control")
    if isinstance(name, str) and len(name) > 512 or isinstance(automation_id, str) and len(automation_id) > 512:
        raise ATSPIError("Accessible names and IDs must not exceed 512 characters")
    wanted_type = str(control_type or "").strip().lower().replace("_", " ")
    matches = []
    for control in _walk(window):
        role = _role(control)
        if not _interactive(role):
            continue
        if name and _name(control) != name:
            continue
        if automation_id and _automation_id(control) != automation_id:
            continue
        if wanted_type and _control_type(control).lower() != wanted_type:
            continue
        try:
            if not _visible(control):
                continue
            if _protected(_module(), control):
                continue
        except ATSPIError:
            if role == "entry" or (role == "text" and _editable(control)):
                continue
        matches.append(control)
    return matches


def _control(window_title: str, name: str | None, automation_id: str | None,
             control_type: str | None, process_id: int | None = None) -> tuple[Any, Any]:
    api, _, window = _window(window_title, process_id)
    matches = _controls(window, name, automation_id, control_type)
    if not matches:
        raise ATSPIError(f"No visible accessible control matched name={name!r}, id={automation_id!r}, type={control_type!r}")
    if len(matches) != 1:
        raise ATSPIError(f"Control selector is ambiguous: {len(matches)} matches; add an AT-SPI id or role")
    return api, matches[0]


def list_controls(window_title: str, process_id: int | None = None, limit: int = 300) -> list[dict[str, Any]]:
    api, _, window = _window(window_title, process_id)
    grouped: dict[tuple[str, str, str], int] = {}
    objects: list[tuple[Any, tuple[str, str, str]]] = []
    for control in _walk(window):
        role = _role(control)
        if not _interactive(role):
            continue
        try:
            if not _visible(control) or _protected(api, control):
                continue
            enabled = _enabled(control)
        except ATSPIError:
            if role == "entry" or (role == "text" and _editable(control)):
                continue
            enabled = False
        name = _name(control)[:512]
        identifier = _automation_id(control)[:512]
        if not name and not identifier:
            continue
        key = (_control_type(control), name, identifier)
        if key not in grouped:
            objects.append((control, key))
        grouped[key] = grouped.get(key, 0) + 1
    maximum = max(1, min(int(limit), 300))
    return [{"name": key[1], "automationId": key[2], "controlType": key[0],
             "matchCount": grouped[key], "enabled": _enabled(control), "actions": _actions(control)}
            for control, key in objects[:maximum]]


def click(window_title: str, name: str | None, automation_id: str | None,
          control_type: str | None, process_id: int | None = None) -> None:
    api, control = _control(window_title, name, automation_id, control_type, process_id)
    action = control.queryAction()
    for index in range(action.nActions):
        action_name = str(action.getName(index)).lower().replace("_", " ")
        if action_name in {"click", "press", "activate", "invoke"}:
            if not action.doAction(index):
                raise ATSPIError(f"AT-SPI action {action_name!r} was rejected")
            return
    raise ATSPIError("The accessible control exposes no supported click, press or activate action")


def fill(window_title: str, name: str | None, automation_id: str | None,
         control_type: str | None, value: str, process_id: int | None = None) -> None:
    api, control = _control(window_title, name, automation_id, control_type, process_id)
    if not (_role(control) == "entry" or (_role(control) == "text" and _editable(control))):
        raise ATSPIError(f"Set Text requires an AT-SPI Entry control; matched {_role(control) or 'unknown'}")
    if _protected(api, control):
        raise ATSPIError("Writing protected/password controls is blocked; use the credential vault")
    try:
        editable = control.queryEditableText()
        if not editable.setTextContents(value):
            raise ATSPIError("The AT-SPI editable-text interface rejected the requested value")
    except ATSPIError:
        raise
    except Exception as exc:
        raise ATSPIError(f"The Entry does not expose editable text: {type(exc).__name__}: {exc}") from exc


def read_text(window_title: str, name: str | None, automation_id: str | None,
              control_type: str | None, process_id: int | None = None) -> str:
    api, control = _control(window_title, name, automation_id, control_type, process_id)
    if _protected(api, control):
        raise ATSPIError("Reading protected/password controls is blocked")
    try:
        return str(control.queryText().getText(0, -1))
    except Exception:
        value = _name(control)
        if value:
            return value
        raise ATSPIError("The accessible control exposes no readable text")


def control_state(window_title: str, name: str | None, automation_id: str | None,
                  control_type: str | None, process_id: int | None = None) -> dict[str, bool] | None:
    try:
        api, _, window = _window(window_title, process_id)
    except ATSPIError as exc:
        if str(exc).startswith("No accessible window matched"):
            return None
        raise
    try:
        matches = _controls(window, name, automation_id, control_type)
    except ATSPIError:
        raise
    if not matches:
        return None
    if len(matches) != 1:
        raise ATSPIError(f"Control selector is ambiguous: {len(matches)} matches")
    control = matches[0]
    return {"exists": True, "visible": _visible(control), "enabled": _enabled(control)}


def status() -> dict[str, Any]:
    if not sys.platform.startswith("linux"):
        return {"available": False, "adapter": "AT-SPI", "reason": "This adapter is Linux-only"}
    try:
        _desktop()
        return {"available": True, "adapter": "AT-SPI accessibility", "reason": None}
    except Exception as exc:
        return {"available": False, "adapter": "AT-SPI", "reason": f"AT-SPI runtime unavailable: {type(exc).__name__}: {exc}"}
