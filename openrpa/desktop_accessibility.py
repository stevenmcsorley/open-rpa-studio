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


def window_exists(window_title: str | None = None, process_id: int | None = None) -> bool:
    return _adapter().window_exists(window_title,process_id)


def activate_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _adapter().activate_window(window_title,process_id)


def minimize_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _adapter().minimize_window(window_title,process_id)


def restore_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _adapter().restore_window(window_title,process_id)


def close_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _adapter().close_window(window_title,process_id)


def list_controls(window_title: str, process_id: int | None = None, limit: int = 300) -> list[dict[str, Any]]:
    return _adapter().list_controls(window_title, process_id, limit)


def click(window_title: str, name: str | None, automation_id: str | None,
          control_type: str | None, process_id: int | None = None) -> None:
    _adapter().click(window_title, name, automation_id, control_type, process_id)


def scroll_into_view(window_title: str, name: str | None, automation_id: str | None,
                     control_type: str | None, process_id: int | None = None) -> None:
    action=getattr(_adapter(),"scroll_into_view",None)
    if action is None:
        raise RuntimeError(f"Accessible scroll-into-view is not implemented by the {sys.platform} adapter")
    action(window_title,name,automation_id,control_type,process_id)


def drag(window_title: str, source_name: str | None, source_automation_id: str | None,
         source_control_type: str | None, target_name: str | None,
         target_automation_id: str | None, target_control_type: str | None,
         duration_milliseconds: int = 500, process_id: int | None = None) -> None:
    adapter = _adapter()
    action = getattr(adapter, "drag", None)
    if action is None:
        raise RuntimeError(f"Accessible drag-and-drop is not implemented by the {sys.platform} adapter")
    action(window_title, source_name, source_automation_id, source_control_type,
           target_name, target_automation_id, target_control_type,
           duration_milliseconds, process_id)


def invoke(window_title: str, name: str | None, automation_id: str | None,
           control_type: str | None, process_id: int | None = None) -> None:
    _adapter().invoke(window_title,name,automation_id,control_type,process_id)


def press(window_title: str, name: str | None, automation_id: str | None,
          control_type: str | None, key: str, process_id: int | None = None) -> None:
    _adapter().press(window_title,name,automation_id,control_type,key,process_id)


def fill(window_title: str, name: str | None, automation_id: str | None,
         control_type: str | None, value: str, process_id: int | None = None) -> None:
    _adapter().fill(window_title, name, automation_id, control_type, value, process_id)


def set_range_value(window_title: str, name: str | None, automation_id: str | None,
                    control_type: str | None, value: float, process_id: int | None = None) -> None:
    adapter = _adapter()
    action = getattr(adapter, "set_range_value", None)
    if action is None:
        raise RuntimeError(f"Range value setting is not implemented by the {sys.platform} accessibility adapter")
    action(window_title, name, automation_id, control_type, value, process_id)


def select(window_title: str, name: str | None, automation_id: str | None,
           control_type: str | None, value: str, process_id: int | None = None) -> None:
    _adapter().select(window_title,name,automation_id,control_type,value,process_id)


def set_selection(window_title: str, name: str | None, automation_id: str | None,
                  control_type: str | None, values: list[str], mode: str = "replace",
                  process_id: int | None = None) -> list[str]:
    adapter=_adapter()
    action=getattr(adapter,"set_selection",None)
    if action is None:raise RuntimeError(f"Multi-item selection is not implemented by the {sys.platform} adapter")
    return action(window_title,name,automation_id,control_type,values,mode,process_id)


def set_checked(window_title: str, name: str | None, automation_id: str | None,
                control_type: str | None, checked: bool, process_id: int | None = None) -> None:
    _adapter().set_checked(window_title,name,automation_id,control_type,checked,process_id)


def set_expanded(window_title: str, name: str | None, automation_id: str | None,
                 control_type: str | None, expanded: bool, process_id: int | None = None) -> None:
    _adapter().set_expanded(window_title,name,automation_id,control_type,expanded,process_id)


def read_text(window_title: str, name: str | None, automation_id: str | None,
              control_type: str | None, process_id: int | None = None) -> str:
    return _adapter().read_text(window_title, name, automation_id, control_type, process_id)


def read_grid(window_title: str, name: str | None, automation_id: str | None,
              control_type: str | None, max_rows: int = 100, max_columns: int = 30,
              max_output_chars: int = 50_000, process_id: int | None = None) -> tuple[list[dict[str,str]],dict[str,Any]]:
    adapter=_adapter()
    action=getattr(adapter,"read_grid",None)
    if action is None:raise RuntimeError(f"Accessible grid reading is not implemented by the {sys.platform} adapter")
    return action(window_title,name,automation_id,control_type,max_rows=max_rows,
                  max_columns=max_columns,max_output_chars=max_output_chars,process_id=process_id)


def control_state(window_title: str, name: str | None, automation_id: str | None,
                  control_type: str | None, process_id: int | None = None) -> dict[str, bool] | None:
    return _adapter().control_state(window_title, name, automation_id, control_type, process_id)
