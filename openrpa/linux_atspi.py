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


def _value_method(obj: Any, *names: str) -> Any:
    """Invoke either legacy pyatspi or PyGObject method spelling."""
    for name in names:
        method = getattr(obj, name, None)
        if callable(method):
            return method
    raise ATSPIError(f"The AT-SPI Value interface does not expose {names[0]}")


def _range_interface(api: Any, control: Any) -> Any:
    role = _role(control)
    if role not in {"slider", "spin button"}:
        raise ATSPIError(f"Set Range Value requires an AT-SPI Slider or Spin Button; matched {role or 'unknown'}")
    try:
        value = control.queryValue()
    except Exception as exc:
        raise ATSPIError(f"The selected control does not expose the AT-SPI Value interface: {type(exc).__name__}: {exc}") from exc
    readonly_state = getattr(api, "STATE_READ_ONLY", None)
    if readonly_state is not None:
        try:
            if control.getState().contains(readonly_state):
                raise ATSPIError("The selected AT-SPI range control is read-only")
        except ATSPIError:
            raise
        except Exception as exc:
            raise ATSPIError(f"Could not determine whether the AT-SPI range control is read-only: {type(exc).__name__}: {exc}") from exc
    return value


def _range_value_supported(api: Any, control: Any) -> bool:
    if _role(control) not in {"slider", "spin button"}:
        return False
    try:
        interface = _range_interface(api, control)
        for names in (("getMinimumValue", "get_minimum_value"),
                      ("getMaximumValue", "get_maximum_value"),
                      ("getCurrentValue", "get_current_value"),
                      ("setCurrentValue", "set_current_value")):
            if not any(callable(getattr(interface, name, None)) for name in names):
                return False
        return True
    except Exception:
        return False


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
    object_paths: set[tuple[int,str]] = set()
    while stack and visited < maximum:
        node = stack.pop()
        # Some providers expose the same accessible object more than once
        # through wrapper/container nodes. Count and traverse each AT-SPI
        # object path once so it does not look like an ambiguous selector.
        try:
            object_path=str(getattr(node,"path",""))
        except Exception:
            object_path=""
        if object_path:
            identity=(_pid(node),object_path)
            if identity in object_paths:
                continue
            object_paths.add(identity)
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
        "link", "slider", "spin button", "password text", "label", "table", "tree table",
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
    try:
        control.queryTable()
        actions.append("read_grid")
    except Exception:
        pass
    if _editable(control) and not _protected(_module(), control):
        actions.append("fill")
    if _role(control)=="list box":
        try:control.querySelection();actions.append("select_many")
        except Exception:pass
    if _role(control) in {"text", "label", "entry", "password text"}:
        actions.append("text")
    if _role(control) in {"combo box", "list box", "list item"}:
        actions.append("select")
    elif _role(control)=="tree item":
        parent=_value(control,"get_parent",default=None)
        try:
            if parent is not None:parent.querySelection();actions.append("select")
        except Exception:
            pass
    elif _role(control) == "check box":
        actions.extend(["check", "uncheck"])
    elif _role(control) == "radio button":
        actions.append("check")
    if _range_value_supported(_module(), control):
        actions.append("set_range_value")
    actions.append("wait")
    try:
        action = control.queryAction()
        expanded = _state(control,("STATE_EXPANDED",)) if _role(control)=="tree item" else False
        for index in range(action.nActions):
            name = str(action.getName(index)).lower().replace("_", " ")
            if _role(control)=="tree item" and name in {"expand","expand or collapse"}:
                if not expanded:actions.append("expand")
                else:actions.append("collapse")
            elif _role(control)=="tree item" and name=="collapse" and expanded:
                actions.append("collapse")
            if _role(control) not in {"check box","radio button"} and name in {"click", "press", "activate", "invoke"}:
                actions.insert(0, "click")
                break
    except Exception:
        pass
    if "click" in actions:actions.insert(0,"invoke")
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


def window_exists(window_title: str | None = None, process_id: int | None = None) -> bool:
    if (not isinstance(window_title,str) or not window_title.strip()) and process_id is None:
        raise ATSPIError("Specify an exact windowTitle or a processId to identify the window")
    api,desktop=_desktop()
    return any((not window_title or _name(item)==window_title)
               and (process_id is None or _pid(item)==process_id)
               and _visible(item) for item in _windows(api,desktop))


def _window_action(window_title: str | None, process_id: int | None, names: set[str], action_label: str) -> None:
    api,desktop=_desktop()
    if (not isinstance(window_title,str) or not window_title.strip()) and process_id is None:
        raise ATSPIError("Specify an exact windowTitle or a processId to identify the window")
    matches=[item for item in _windows(api,desktop)
             if (not window_title or _name(item)==window_title)
             and (process_id is None or _pid(item)==process_id) and _visible(item)]
    if not matches:raise ATSPIError("No visible accessible window matched the configured title and process ID")
    if len(matches)!=1:raise ATSPIError(f"The configured window identity matched {len(matches)} windows; add an exact title or processId")
    try:action=matches[0].queryAction()
    except Exception as exc:raise ATSPIError(f"The accessible window does not expose an AT-SPI Action interface for {action_label}") from exc
    for index in range(action.nActions):
        name=str(action.getName(index)).lower().replace("_"," ")
        if name in names:
            if not action.doAction(index):raise ATSPIError(f"The AT-SPI {action_label} action was rejected")
            return
    raise ATSPIError(f"The accessible window does not expose a {action_label} action")


def activate_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _window_action(window_title,process_id,{"activate","focus"},"activate")


def minimize_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _window_action(window_title,process_id,{"minimize","minimise"},"minimize")


def restore_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _window_action(window_title,process_id,{"restore","unminimize","unminimise"},"restore")


def close_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _window_action(window_title,process_id,{"close","close window"},"close")


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


def invoke(window_title: str, name: str | None, automation_id: str | None,
           control_type: str | None, process_id: int | None = None) -> None:
    """Invoke an AT-SPI Action interface without coordinate input."""
    click(window_title,name,automation_id,control_type,process_id)


def press(window_title: str, name: str | None, automation_id: str | None,
          control_type: str | None, key: str, process_id: int | None = None) -> None:
    """Focus one exact, non-password AT-SPI control and send one allowlisted key."""
    api, control = _control(window_title,name,automation_id,control_type,process_id)
    if _protected(api,control):
        raise ATSPIError("Keyboard actions on password controls are blocked; use the credential vault")
    activate_window(window_title,process_id)
    try:
        if not control.grabFocus():
            raise ATSPIError("The accessible control rejected keyboard focus")
        if not _state(control,("STATE_FOCUSED",)):
            raise ATSPIError("AT-SPI did not confirm keyboard focus on the selected control")
    except ATSPIError:
        raise
    except Exception as exc:
        raise ATSPIError(f"Could not focus the AT-SPI control: {type(exc).__name__}: {exc}") from exc
    from .desktop_keys import send_key
    send_key(key)


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


def read_grid(window_title: str, name: str | None, automation_id: str | None,
              control_type: str | None, *, max_rows: int = 100,
              max_columns: int = 30, max_output_chars: int = 50_000,
              process_id: int | None = None) -> tuple[list[dict[str,str]],dict[str,Any]]:
    """Read a bounded AT-SPI Table interface as normalized row records."""
    import json
    import re
    api,control=_control(window_title,name,automation_id,control_type,process_id)
    if _protected(api,control):raise ATSPIError("Reading a password-marked AT-SPI table is blocked")
    try:table=control.queryTable()
    except Exception as exc:raise ATSPIError(f"The selected control does not expose the AT-SPI Table interface: {type(exc).__name__}: {exc}") from exc
    total_rows=int(_value(table,"getNRows","nRows",-1));total_columns=int(_value(table,"getNColumns","nColumns",-1))
    if total_rows<0 or total_columns<0 or total_rows>1_000_000 or total_columns>10_000:raise ATSPIError("The AT-SPI Table reported invalid dimensions")
    row_count=min(total_rows,max_rows);column_count=min(total_columns,max_columns)
    headers=[];used={}
    for column in range(column_count):
        try:header=table.getColumnHeader(column)
        except Exception:header=None
        base=re.sub(r"\s+"," ",_name(header) if header is not None else "").strip() or f"column_{column+1}"
        base=base[:256];used[base]=used.get(base,0)+1
        headers.append(base if used[base]==1 else f"{base}_{used[base]}")
    rows=[];chars=sum(len(header) for header in headers);redacted=0
    for row_index in range(row_count):
        record={}
        for column_index,header in enumerate(headers):
            try:cell=table.getAccessibleAt(row_index,column_index)
            except Exception as exc:raise ATSPIError(f"Could not read AT-SPI table cell at row {row_index+1}, column {column_index+1}: {type(exc).__name__}: {exc}") from exc
            if cell is None:value=""
            elif _protected(api,cell):value="";redacted+=1
            else:
                try:value=str(cell.queryText().getText(0,-1) or "")
                except Exception:value=_name(cell)
                value=re.sub(r"\s+"," ",value).strip()
            chars+=len(value)
            if chars>max_output_chars:raise ATSPIError(f"AT-SPI table text exceeds the configured output limit of {max_output_chars} characters; lower maxRows or maxColumns")
            record[header]=value
        rows.append(record)
    serialized=json.dumps(rows,ensure_ascii=False,separators=(",",":"))
    if len(serialized)>max_output_chars:raise ATSPIError(f"AT-SPI table JSON exceeds the configured output limit of {max_output_chars} characters; lower maxRows or maxColumns")
    metadata={"totalRows":total_rows,"totalColumns":total_columns,"rowsRead":len(rows),"columnsRead":len(headers),
              "truncated":row_count<total_rows or column_count<total_columns,"redactedCells":redacted,"outputChars":len(serialized)}
    return rows,metadata


def select(window_title: str, name: str | None, automation_id: str | None,
           control_type: str | None, value: str, process_id: int | None = None) -> None:
    _,control=_control(window_title,name,automation_id,control_type,process_id)
    role=_role(control)
    if role in {"list item","tree item"}:
        if _name(control)!=value:raise ATSPIError("List Item selection requires its exact accessible name as value")
        parent=_value(control,"get_parent",default=None) if role=="tree item" else control
        if parent is None:raise ATSPIError("Could not resolve the Tree Item's selection container")
        try:selection=parent.querySelection()
        except Exception as exc:raise ATSPIError(f"List Item does not expose a selection interface: {type(exc).__name__}: {exc}") from exc
        parent=_value(control,"get_parent",default=None)
        children=list(_children(parent)) if parent is not None else []
        index=next((i for i,item in enumerate(children) if item is control),-1)
        if index<0:raise ATSPIError("Could not resolve this selectable item's parent index")
        if not selection.selectChild(index):raise ATSPIError("AT-SPI rejected the List Item selection")
        if callable(getattr(selection,"isChildSelected",None)) and not selection.isChildSelected(index):raise ATSPIError("AT-SPI did not select the requested List Item")
        return
    if role not in {"combo box","list box"}:
        raise ATSPIError(f"Select Option requires a Combo Box, List Box, List Item or Tree Item; matched {role or 'unknown'}")
    matches=[(index,item) for index,item in enumerate(_children(control)) if _name(item)==value]
    if not matches:raise ATSPIError(f"No option with exact accessible name {value!r} was found")
    if len(matches)!=1:raise ATSPIError(f"Option name {value!r} is ambiguous: {len(matches)} matches")
    try:selection=control.querySelection()
    except Exception as exc:raise ATSPIError(f"The control does not expose a selection interface: {type(exc).__name__}: {exc}") from exc
    index=matches[0][0]
    if not selection.selectChild(index):raise ATSPIError("AT-SPI rejected the requested option")
    if callable(getattr(selection,"isChildSelected",None)) and not selection.isChildSelected(index):raise ATSPIError("AT-SPI did not select the requested option")


def set_selection(window_title: str, name: str | None, automation_id: str | None,
                  control_type: str | None, values: list[str], mode: str = "replace",
                  process_id: int | None = None) -> list[str]:
    """Set selections in an accessible List Box while preserving unrelated items."""
    api,control=_control(window_title,name,automation_id,control_type,process_id)
    if _role(control)!="list box":raise ATSPIError(f"Set List Selection requires a List Box; matched {_role(control) or 'unknown'}")
    if not isinstance(values,list) or len(values)>100 or any(not isinstance(value,str) or len(value)>512 for value in values):
        raise ATSPIError("List selection values must be an array of at most 100 names, each no longer than 512 characters")
    if mode not in {"replace","add","remove"}:raise ATSPIError("List selection mode must be replace, add, or remove")
    if len(set(values))!=len(values):raise ATSPIError("List selection values must not contain duplicate names")
    if mode!="replace" and not values:raise ATSPIError("Add and remove selection modes need at least one option name")
    children=list(_children(control))
    by_name:dict[str,list[int]]={}
    for index,item in enumerate(children):
        item_name=_name(item)
        if item_name:by_name.setdefault(item_name,[]).append(index)
    target_indices=[]
    for value in values:
        matches=by_name.get(value,[])
        if not matches:raise ATSPIError(f"No List Box option with the exact accessible name {value!r} was found")
        if len(matches)!=1:raise ATSPIError(f"List Box option {value!r} is ambiguous: {len(matches)} matches")
        target_indices.append(matches[0])
    try:selection=control.querySelection()
    except Exception as exc:raise ATSPIError(f"The List Box does not expose a selection interface: {type(exc).__name__}: {exc}") from exc
    selected_check=getattr(selection,"isChildSelected",None)
    if not callable(selected_check):raise ATSPIError("The AT-SPI List Box does not expose selected-item state")
    before={index for index in range(len(children)) if selected_check(index)}
    if len(target_indices)>1:
        try:multiple=_state(control,("STATE_MULTISELECTABLE",))
        except ATSPIError as exc:raise ATSPIError("This AT-SPI List Box does not report whether multiple selection is supported") from exc
        if not multiple:raise ATSPIError("This AT-SPI List Box does not support multiple selection")
    if mode=="replace":
        if not selection.clearSelection():raise ATSPIError("AT-SPI rejected clearing the existing List Box selection")
        for index in target_indices:
            if not selection.selectChild(index):raise ATSPIError(f"AT-SPI rejected List Box option {values[target_indices.index(index)]!r}")
    elif mode=="add":
        for index in target_indices:
            if index not in before and not selection.selectChild(index):raise ATSPIError(f"AT-SPI rejected List Box option {values[target_indices.index(index)]!r}")
    else:
        for index in target_indices:
            if index in before and not selection.deselectChild(index):raise ATSPIError(f"AT-SPI rejected removing List Box option {values[target_indices.index(index)]!r}")
    after={index for index in range(len(children)) if selected_check(index)}
    expected=set(target_indices) if mode=="replace" else before|set(target_indices) if mode=="add" else before-set(target_indices)
    if after!=expected:raise ATSPIError("AT-SPI did not reach the requested List Box selection")
    return [_name(children[index]) for index in sorted(after)]


def set_range_value(window_title: str, name: str | None, automation_id: str | None,
                    control_type: str | None, value: float, process_id: int | None = None) -> None:
    """Set an AT-SPI Slider or Spin Button through its Value interface."""
    import math
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ATSPIError("Range value must be a finite number")
    api, control = _control(window_title, name, automation_id, control_type, process_id)
    interface = _range_interface(api, control)
    try:
        minimum = float(_value_method(interface, "getMinimumValue", "get_minimum_value")())
        maximum = float(_value_method(interface, "getMaximumValue", "get_maximum_value")())
        if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
            raise ATSPIError("The control reported invalid AT-SPI range bounds")
        if value < minimum or value > maximum:
            raise ATSPIError(f"Requested value is outside the control range ({minimum:g} to {maximum:g})")
        accepted = _value_method(interface, "setCurrentValue", "set_current_value")(float(value))
        if accepted is False:
            raise ATSPIError("The AT-SPI Value interface rejected the requested value")
        observed = float(_value_method(interface, "getCurrentValue", "get_current_value")())
        if not math.isfinite(observed) or not math.isclose(observed, float(value), rel_tol=1e-9, abs_tol=1e-7):
            raise ATSPIError("The AT-SPI range control did not retain the requested value")
    except ATSPIError:
        raise
    except Exception as exc:
        raise ATSPIError(f"Could not set the selected AT-SPI range value: {type(exc).__name__}: {exc}") from exc


def set_expanded(window_title: str, name: str | None, automation_id: str | None,
                 control_type: str | None, expanded: bool, process_id: int | None = None) -> None:
    _,control=_control(window_title,name,automation_id,control_type,process_id)
    if _role(control)!="tree item":
        raise ATSPIError(f"Expand or Collapse requires a Tree Item; matched {_role(control) or 'unknown'}")
    try:action=control.queryAction()
    except Exception as exc:raise ATSPIError(f"The Tree Item does not expose an AT-SPI action: {type(exc).__name__}: {exc}") from exc
    current=_state(control,("STATE_EXPANDED",))
    if current is expanded:return
    expected={"expand"} if expanded else {"collapse"}
    for index in range(action.nActions):
        action_name=str(action.getName(index)).lower().replace("_"," ")
        if action_name in expected or action_name=="expand or collapse":
            if not action.doAction(index):raise ATSPIError(f"AT-SPI {action_name} action was rejected")
            if _state(control,("STATE_EXPANDED",)) is not expanded:raise ATSPIError("AT-SPI did not reach the requested Tree Item expansion state")
            return
    raise ATSPIError(f"The Tree Item exposes no {'expand' if expanded else 'collapse'} action")


def _checked(api: Any, control: Any) -> bool:
    if _role(control) not in {"check box","radio button"}:
        raise ATSPIError(f"Set Checked requires a Check Box or Radio Button; matched {_role(control) or 'unknown'}")
    return _state(control,("STATE_CHECKED",))


def set_checked(window_title: str, name: str | None, automation_id: str | None,
                control_type: str | None, checked: bool, process_id: int | None = None) -> None:
    api,control=_control(window_title,name,automation_id,control_type,process_id)
    before=_checked(api,control)
    if before is checked:return
    try:action=control.queryAction()
    except Exception as exc:raise ATSPIError(f"The control does not expose an accessible action: {type(exc).__name__}: {exc}") from exc
    for index in range(action.nActions):
        name=str(action.getName(index)).lower().replace("_"," ")
        if name in {"check","uncheck","click","toggle","press","activate","invoke"}:
            if not action.doAction(index):raise ATSPIError(f"AT-SPI action {name!r} was rejected")
            after=_checked(api,control)
            if after is not checked:raise ATSPIError("AT-SPI action did not reach the requested checked state")
            return
    raise ATSPIError("The accessible control exposes no supported check, uncheck or toggle action")


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
    state={"exists": True, "visible": _visible(control), "enabled": _enabled(control)}
    if _role(control) in {"check box","radio button"}:state["checked"]=_checked(api,control)
    if _role(control) in {"list item","tree item"}:
        try:state["selected"]=_state(control,("STATE_SELECTED",))
        except ATSPIError:pass
    if _role(control)=="tree item":state["expanded"]=_state(control,("STATE_EXPANDED",))
    return state


def status() -> dict[str, Any]:
    if not sys.platform.startswith("linux"):
        return {"available": False, "adapter": "AT-SPI", "reason": "This adapter is Linux-only"}
    try:
        _desktop()
        return {"available": True, "adapter": "AT-SPI accessibility", "reason": None}
    except Exception as exc:
        return {"available": False, "adapter": "AT-SPI", "reason": f"AT-SPI runtime unavailable: {type(exc).__name__}: {exc}"}
