"""Bounded, exact-match helpers for Windows UI Automation controls."""
from __future__ import annotations

import sys
import math
import time
import csv
import io
import os
import shutil
import subprocess
import tempfile
import unicodedata
from typing import Any, Callable


class UIAutomationError(RuntimeError):
    """A selector could not be resolved safely through Windows UIA."""


def _ocr_normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _focus_ocr_window(window: Any) -> None:
    """Bring the exact OCR target forward and refuse input if activation fails."""
    try:
        import win32con
        import win32gui
        handle = int(getattr(window, "handle", 0) or getattr(window.element_info, "handle", 0))
        if handle < 1 or not win32gui.IsWindow(handle):
            raise UIAutomationError("The selected OCR window no longer exists")
        if win32gui.IsIconic(handle):
            win32gui.ShowWindow(handle, win32con.SW_RESTORE)
        window.set_focus()
        if win32gui.GetForegroundWindow() != handle:
            win32gui.SetForegroundWindow(handle)
        deadline = time.monotonic() + 1.5
        while win32gui.GetForegroundWindow() != handle and time.monotonic() < deadline:
            time.sleep(0.025)
        if win32gui.GetForegroundWindow() != handle:
            raise UIAutomationError("Could not activate the selected OCR window; refusing to click")
    except UIAutomationError:
        raise
    except Exception as exc:
        raise UIAutomationError(f"Could not activate the selected OCR window: {type(exc).__name__}: {exc}") from exc


def ocr_click(window_title: str, text: str, confidence_threshold: int = 80,
              timeout_seconds: float = 15, process_id: int | None = None,
              cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Click a unique exact OCR text match inside one exact visible window.

    OCR text and coordinates are deliberately never returned or audited. The
    caller must have already obtained explicit desktop permission.
    """
    if sys.platform != "win32":
        raise UIAutomationError("OCR desktop clicking is currently available only on Windows")
    if not isinstance(text, str) or not text.strip() or len(text) > 512:
        raise UIAutomationError("OCR target text must contain 1–512 characters")
    if isinstance(confidence_threshold, bool) or not isinstance(confidence_threshold, int) or not 0 <= confidence_threshold <= 100:
        raise UIAutomationError("OCR confidenceThreshold must be an integer from 0 to 100")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 60:
        raise UIAutomationError("OCR timeoutSeconds must be from 1 to 60")
    executable = shutil.which("tesseract")
    if not executable:
        raise UIAutomationError("Tesseract OCR is unavailable; install it and ensure tesseract is on PATH")
    try:
        import pyautogui
    except ImportError as exc:
        raise UIAutomationError("Install the optional desktop extra to enable OCR desktop clicking") from exc

    window = _window(window_title, process_id)
    try:
        _focus_ocr_window(window)
        rect = window.rectangle()
        left, top, width, height = int(rect.left), int(rect.top), int(rect.width()), int(rect.height())
        if width < 1 or height < 1 or width * height > 30_000_000:
            raise UIAutomationError("The selected window has invalid or oversized screen bounds")
        image = pyautogui.screenshot(region=(left, top, width, height))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    except UIAutomationError:
        raise
    except Exception as exc:
        raise UIAutomationError(f"Could not capture the selected window for OCR: {type(exc).__name__}: {exc}") from exc

    environment = {key: value for key, value in os.environ.items()
                   if not any(marker in key.upper() for marker in ("API_KEY", "APIKEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTHORIZATION"))}
    environment["OMP_THREAD_LIMIT"] = "1"
    deadline = time.monotonic() + float(timeout_seconds)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen([executable, "stdin", "stdout", "-l", "eng", "--psm", "11", "tsv"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               cwd=tempfile.gettempdir(), env=environment, creationflags=flags)
    input_payload: bytes | None = buffer.getvalue()
    try:
        while True:
            if cancelled and cancelled():
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
                raise UIAutomationError("OCR was cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(executable, timeout_seconds)
            try:
                output, _ = process.communicate(input_payload, timeout=min(0.25,remaining))
                break
            except subprocess.TimeoutExpired:
                input_payload = None
    except subprocess.TimeoutExpired as exc:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise UIAutomationError("OCR exceeded its configured timeout") from exc
    if process.returncode != 0:
        raise UIAutomationError("Tesseract failed to recognize the selected window")
    if len(output) > 8_000_000:
        raise UIAutomationError("OCR output exceeded the 8 MB safety limit")

    expected = _ocr_normalize(text)
    lines: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    try:
        for row in csv.DictReader(io.StringIO(output.decode("utf-8", errors="replace")), delimiter="\t"):
            word = str(row.get("text", "")).strip()
            if not word:
                continue
            confidence = float(row.get("conf", "-1"))
            if confidence < 0:
                continue
            key = tuple(str(row.get(field, "")) for field in ("page_num", "block_num", "par_num", "line_num"))
            lines.setdefault(key, []).append({
                "text": word, "confidence": confidence,
                "left": int(row["left"]), "top": int(row["top"]),
                "width": int(row["width"]), "height": int(row["height"]),
            })
    except (KeyError, TypeError, ValueError) as exc:
        raise UIAutomationError("Tesseract returned malformed OCR coordinates") from exc

    matches = []
    for words in lines.values():
        words.sort(key=lambda word: word["left"])
        line_text = _ocr_normalize(" ".join(word["text"] for word in words))
        if line_text != expected:
            continue
        average_confidence = sum(word["confidence"] for word in words) / len(words)
        if average_confidence < confidence_threshold:
            continue
        x1 = min(word["left"] for word in words)
        y1 = min(word["top"] for word in words)
        x2 = max(word["left"] + word["width"] for word in words)
        y2 = max(word["top"] + word["height"] for word in words)
        matches.append((x1, y1, x2, y2, average_confidence))
    if not matches:
        raise UIAutomationError("No exact OCR text match met the configured confidence threshold in the selected window")
    if len(matches) != 1:
        raise UIAutomationError(f"OCR target is ambiguous: {len(matches)} exact matches found in the selected window")

    # Re-resolve the window immediately before acting; if identity changed, fail closed.
    previous_process_id = int(window.element_info.process_id)
    window = _window(window_title, process_id)
    if int(window.element_info.process_id) != previous_process_id:
        raise UIAutomationError("The selected window changed during OCR; refusing to click")
    current_rect=window.rectangle()
    if (int(current_rect.left),int(current_rect.top),int(current_rect.width()),int(current_rect.height()))!=(left,top,width,height):
        raise UIAutomationError("The selected window moved or resized during OCR; refusing to click")
    x1, y1, x2, y2, confidence = matches[0]
    click_x = left + (x1 + x2) // 2
    click_y = top + (y1 + y2) // 2
    if not (left <= click_x < left + width and top <= click_y < top + height):
        raise UIAutomationError("OCR produced a click target outside the selected window")
    try:
        _focus_ocr_window(window)
        pyautogui.click(click_x, click_y)
    except Exception as exc:
        raise UIAutomationError(f"Could not click the verified OCR target: {type(exc).__name__}: {exc}") from exc
    return {"matchCount": 1, "confidence": round(confidence, 1)}


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


def window_exists(window_title: str | None = None, process_id: int | None = None) -> bool:
    """Check visible top-level windows using exact identity filters."""
    if (not isinstance(window_title,str) or not window_title.strip()) and process_id is None:
        raise UIAutomationError("Specify an exact windowTitle or a processId to identify the window")
    if window_title is not None and (not isinstance(window_title,str) or len(window_title)>512):
        raise UIAutomationError("windowTitle must be text no longer than 512 characters")
    if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):
        raise UIAutomationError("processId must be a positive integer")
    for window in _desktop().windows(visible_only=True,top_level_only=True):
        if window_title and _title(window)!=window_title:continue
        if process_id is not None and int(window.element_info.process_id)!=process_id:continue
        return True
    return False


def _window_target(window_title: str | None, process_id: int | None = None) -> Any:
    if (not isinstance(window_title,str) or not window_title.strip()) and process_id is None:
        raise UIAutomationError("Specify an exact windowTitle or a processId to identify the window")
    if window_title is not None and (not isinstance(window_title,str) or len(window_title)>512):
        raise UIAutomationError("windowTitle must be text no longer than 512 characters")
    if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):
        raise UIAutomationError("processId must be a positive integer")
    candidates=[window for window in _desktop().windows(visible_only=True,top_level_only=True)
                if (not window_title or _title(window)==window_title)
                and (process_id is None or int(window.element_info.process_id)==process_id)]
    if not candidates:raise UIAutomationError("No visible window matched the configured title and process ID")
    if len(candidates)!=1:raise UIAutomationError(f"The configured window identity matched {len(candidates)} windows; add an exact title or processId")
    return candidates[0]


def activate_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _window_target(window_title,process_id).set_focus()


def minimize_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _window_target(window_title,process_id).minimize()


def restore_window(window_title: str | None = None, process_id: int | None = None) -> None:
    _window_target(window_title,process_id).restore()


def close_window(window_title: str | None = None, process_id: int | None = None) -> None:
    """Send a normal close request; never terminate the process forcibly."""
    _window_target(window_title,process_id).close()


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


def _find_controls(window: Any, criteria: dict[str, str], *, visible_only: bool = True) -> list[Any]:
    """Use pywinauto's UIA-aware Automation ID filter (UIA descendants omit it)."""
    from pywinauto.findwindows import find_elements
    elements = find_elements(parent=window, top_level_only=False, visible_only=visible_only,
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
    allowed = {"Button", "Edit", "Text", "ComboBox", "CheckBox", "RadioButton", "ListItem", "TabItem", "MenuItem",
               "Hyperlink", "TreeItem", "Slider", "Spinner", "SplitButton", "DataGrid", "Table", "List"}
    grouped: dict[tuple[str, str, str], int] = {}
    objects: list[tuple[Any, tuple[str, str, str]]] = []
    all_controls=window.descendants()
    if len(all_controls)>5000:
        raise UIAutomationError("The window accessibility tree exceeds the safe 5,000-control selector limit")
    for control in all_controls:
        info = control.element_info
        control_type = str(getattr(info, "control_type", ""))
        try:
            visible=bool(control.is_visible())
        except Exception:
            visible=False
        try:
            offscreen=bool(control.element_info.element.CurrentIsOffscreen)
        except Exception:
            offscreen=False
        if (not visible and not offscreen) or control_type not in allowed or _is_password(control):
            continue
        name = str(getattr(info, "name", "") or "").strip()[:512]
        automation_id = str(getattr(info, "automation_id", "") or "").strip()[:512]
        if not name and not automation_id:
            continue
        signature = (control_type, name, automation_id)
        if signature not in grouped:
            objects.append((control, signature))
        grouped[signature] = grouped.get(signature, 0) + 1
    result=[]
    for control,signature in objects[:max(1,min(int(limit),300))]:
        control_type=signature[0]
        actions=["wait"]
        if control_type in {"DataGrid","Table","List"}:
            try:
                int(control.iface_grid.CurrentRowCount)
                int(control.iface_grid.CurrentColumnCount)
                actions.insert(0,"read_grid")
            except Exception:
                if control_type=="Table" and getattr(control,"is_table",False):actions.insert(0,"read_grid")
        if control_type=="List":
            try:
                control.iface_selection
                actions.insert(0,"select_many")
            except Exception:
                pass
        if control_type in {"Slider", "Spinner"}:
            try:
                range_value = control.iface_range_value
                if not bool(range_value.CurrentIsReadOnly):
                    actions.insert(0, "set_range_value")
            except Exception:
                pass
        try:
            control.iface_scroll_item
            actions.insert(0, "scroll_into_view")
        except Exception:
            pass
        if control_type=="Edit": actions.extend(["fill","text"])
        elif control_type=="Text": actions.append("text")
        elif control_type=="ComboBox": actions.insert(0,"select")
        elif control_type in {"List", "ListItem"}: actions.insert(0,"select")
        elif control_type=="TreeItem":
            try:
                control.is_selected()
                actions.insert(0,"select")
            except Exception:
                pass
        if control_type=="TreeItem":
            try:
                state=control.get_expand_state()
                from pywinauto.controls.uiawrapper import uia_defs
                collapsed=getattr(uia_defs,"expand_state_collapsed",0)
                expanded=getattr(uia_defs,"expand_state_expanded",1)
                partial=getattr(uia_defs,"expand_state_partially",2)
                if state in {collapsed,partial}:actions.append("expand")
                if state in {expanded,partial}:actions.append("collapse")
            except Exception:
                pass
        elif control_type=="CheckBox": actions[:0]=["check","uncheck"]
        elif control_type=="RadioButton": actions.insert(0,"check")
        elif control_type not in {"Edit","Text","TreeItem"}: actions.insert(0,"click")
        if control_type in {"Button","Hyperlink","MenuItem","SplitButton"}:actions.insert(0,"invoke")
        result.append({"name":signature[1],"automationId":signature[2],"controlType":control_type,
                       "visible":bool(control.is_visible()),
                       "matchCount":grouped[signature],"enabled":bool(getattr(control,"is_enabled",lambda:False)()),
                       "actions":actions})
    return result


def click_activity_at_point(window_title: str, process_id: int, x: int, y: int) -> dict[str, Any] | None:
    """Resolve a click to one unique, non-password accessible control.

    Coordinates are consumed only for this hit test and are never returned or
    retained. Unnamed, ambiguous, password, and out-of-process targets are
    ignored rather than converted into fragile coordinate activities.
    """
    window = _window(window_title, process_id)
    try:
        target = _desktop().from_point(int(x), int(y))
    except Exception as exc:
        raise UIAutomationError(f"Windows UIA could not resolve the clicked control: {type(exc).__name__}: {exc}") from exc
    interactive = {"Button", "Hyperlink", "MenuItem", "SplitButton", "Edit", "ComboBox",
                   "CheckBox", "RadioButton", "ListItem", "TabItem", "TreeItem", "Slider", "Spinner"}
    current = target
    for _ in range(16):
        info = current.element_info
        try:
            if int(info.process_id) != process_id:
                return None
        except Exception:
            return None
        control_type = str(getattr(info, "control_type", ""))
        if control_type in interactive:
            if _is_password(current):
                return None
            name = str(getattr(info, "name", "") or "").strip()[:512]
            automation_id = str(getattr(info, "automation_id", "") or "").strip()[:512]
            if not (name or automation_id):
                return None
            criteria = _criteria(name, automation_id, control_type)
            try:
                matches = _find_controls(window, criteria)
            except Exception as exc:
                raise UIAutomationError(f"Windows UIA could not verify the clicked control: {type(exc).__name__}: {exc}") from exc
            if len(matches) != 1:
                return None
            return {"type": "desktop_ui_click", "windowTitle": window_title,
                    "processId": process_id, "name": name, "automationId": automation_id,
                    "controlType": control_type, "timeoutSeconds": 10}
        try:
            parent = current.parent()
        except Exception:
            return None
        if parent is None or parent == current:
            return None
        current = parent
    return None


def drag_activity_between_points(window_title: str, process_id: int,
                                 source_x: int, source_y: int,
                                 target_x: int, target_y: int) -> dict[str, Any] | None:
    """Resolve a recorded drag to two unique accessible selectors, never coordinates."""
    source = click_activity_at_point(window_title, process_id, source_x, source_y)
    target = click_activity_at_point(window_title, process_id, target_x, target_y)
    if source is None or target is None:
        return None
    source_identity = (source.get("name"), source.get("automationId"), source.get("controlType"))
    target_identity = (target.get("name"), target.get("automationId"), target.get("controlType"))
    if source_identity == target_identity:
        return None
    return {"type":"desktop_ui_drag","windowTitle":window_title,"processId":process_id,
            "sourceName":source["name"],"sourceAutomationId":source["automationId"],
            "sourceControlType":source["controlType"],"targetName":target["name"],
            "targetAutomationId":target["automationId"],"targetControlType":target["controlType"],
            "durationMilliseconds":500,"timeoutSeconds":10}


def key_activity_for_focused_control(window_title: str, process_id: int, key: str) -> dict[str, Any] | None:
    """Resolve one focused, named non-password UIA control for a recorded key."""
    from .desktop_keys import normalize_key
    try:
        canonical="+".join(part.title() for part in key.split("+"))
        normalize_key(canonical)
    except (AttributeError,TypeError,ValueError):
        return None
    window=_window(window_title,process_id)
    focused=[]
    try:
        for control in window.descendants():
            try:
                if control.is_visible() and control.has_keyboard_focus():focused.append(control)
            except Exception:
                continue
    except Exception:
        return None
    if len(focused)!=1:return None
    control=focused[0]
    if _is_password(control):return None
    info=control.element_info
    name=str(getattr(info,"name","") or "").strip()
    automation_id=str(getattr(info,"automation_id","") or "").strip()
    control_type=str(getattr(info,"control_type","") or "").strip()
    if not name and not automation_id:return None
    try:
        criteria=_criteria(name,automation_id,control_type)
        if len(_find_controls(window,criteria))!=1:return None
    except Exception:
        return None
    return {"type":"desktop_ui_press","windowTitle":window_title,"processId":process_id,
            "name":name,"automationId":automation_id,"controlType":control_type,
            "key":canonical,"timeoutSeconds":10}


def text_activity_for_focused_control(window_title: str, process_id: int, text: str) -> dict[str, Any] | None:
    """Resolve typed text only to one focused, uniquely addressable, non-password edit."""
    if not isinstance(text,str) or not 1<=len(text)<=200 or any(not char.isprintable() for char in text):
        return None
    window=_window(window_title,process_id)
    focused=[]
    try:
        for control in window.descendants():
            try:
                if control.is_visible() and control.has_keyboard_focus():focused.append(control)
            except Exception:
                continue
    except Exception:
        return None
    if len(focused)!=1:return None
    control=focused[0]
    if _is_password(control):return None
    info=control.element_info
    name=str(getattr(info,"name","") or "").strip()
    automation_id=str(getattr(info,"automation_id","") or "").strip()
    control_type=str(getattr(info,"control_type","") or "").strip()
    if control_type not in {"Edit","Document"} or (not name and not automation_id):return None
    try:
        if len(_find_controls(window,_criteria(name,automation_id,control_type)))!=1:return None
    except Exception:
        return None
    return {"type":"desktop_recorded_text","windowTitle":window_title,"processId":process_id,
            "name":name,"automationId":automation_id,"controlType":control_type,
            "value":text}


def click(window_title: str, name: str | None, automation_id: str | None,
          control_type: str | None, process_id: int | None = None) -> None:
    _control(window_title, name, automation_id, control_type, process_id).click_input()


def scroll_into_view(window_title: str, name: str | None, automation_id: str | None,
                     control_type: str | None, process_id: int | None = None) -> None:
    """Ask the target's native UIA ScrollItem pattern to reveal one control."""
    window=_window(window_title,process_id)
    criteria=_criteria(name,automation_id,control_type)
    try:
        matches=_find_controls(window,criteria,visible_only=False)
    except Exception as exc:
        raise UIAutomationError(f"Could not inspect the off-screen UIA control: {type(exc).__name__}: {exc}") from exc
    if len(matches)!=1:
        raise UIAutomationError(f"Scroll selector matched {len(matches)} controls; use a unique accessible name and Automation ID")
    control=matches[0]
    try:
        control.iface_scroll_item.ScrollIntoView()
        if not control.is_visible():
            raise UIAutomationError("UIA ScrollItem completed but the control is still not visible")
    except UIAutomationError:
        raise
    except Exception as exc:
        raise UIAutomationError(f"The selected control does not support UIA ScrollItem: {type(exc).__name__}: {exc}") from exc


def drag(window_title: str, source_name: str | None, source_automation_id: str | None,
         source_control_type: str | None, target_name: str | None,
         target_automation_id: str | None, target_control_type: str | None,
         duration_milliseconds: int = 500, process_id: int | None = None) -> None:
    """Drag between two uniquely identified UIA controls in one exact window.

    Screen coordinates are derived transiently from the controls' bounding
    rectangles. They are neither accepted from workflows nor returned/logged.
    """
    if isinstance(duration_milliseconds, bool) or not isinstance(duration_milliseconds, int) or not 100 <= duration_milliseconds <= 5000:
        raise UIAutomationError("durationMilliseconds must be an integer from 100 to 5,000")
    window = _window(window_title, process_id)
    controls = []
    for label, name, automation_id, control_type in (
        ("source", source_name, source_automation_id, source_control_type),
        ("target", target_name, target_automation_id, target_control_type),
    ):
        criteria = _criteria(name, automation_id, control_type)
        try:
            matches = _find_controls(window, criteria)
        except Exception as exc:
            raise UIAutomationError(f"Could not inspect the drag {label} selector: {type(exc).__name__}: {exc}") from exc
        if len(matches) != 1:
            raise UIAutomationError(f"The drag {label} selector matched {len(matches)} controls; use a unique accessible name and Automation ID")
        control = matches[0]
        if _is_password(control):
            raise UIAutomationError("Dragging password controls is blocked")
        try:
            if not control.is_visible() or not control.is_enabled():
                raise UIAutomationError(f"The drag {label} control must be visible and enabled")
            rect = control.rectangle()
            left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
            if right <= left or bottom <= top:
                raise UIAutomationError(f"The drag {label} control has an empty bounding rectangle")
            controls.append(((left + right) // 2, (top + bottom) // 2, control))
        except UIAutomationError:
            raise
        except Exception as exc:
            raise UIAutomationError(f"Could not inspect the drag {label} control bounds: {type(exc).__name__}: {exc}") from exc
    (sx, sy, source), (tx, ty, target) = controls
    if source == target or (sx, sy) == (tx, ty):
        raise UIAutomationError("Drag source and target must be distinct controls with distinct centers")
    try:
        from pywinauto import mouse
        steps = max(4, min(50, math.ceil(duration_milliseconds / 50)))
        last_position = (sx, sy)
        mouse.press(button="left", coords=(sx, sy))
        try:
            for step in range(1, steps + 1):
                x = round(sx + (tx - sx) * step / steps)
                y = round(sy + (ty - sy) * step / steps)
                mouse.move(coords=(x, y))
                last_position = (x, y)
                if step < steps:
                    time.sleep(duration_milliseconds / 1000 / steps)
        finally:
            mouse.release(button="left", coords=last_position)
    except UIAutomationError:
        raise
    except Exception as exc:
        raise UIAutomationError(f"Windows UIA drag failed: {type(exc).__name__}: {exc}") from exc


def invoke(window_title: str, name: str | None, automation_id: str | None,
           control_type: str | None, process_id: int | None = None) -> None:
    """Invoke a control through UIA's InvokePattern without moving the pointer."""
    control=_control(window_title,name,automation_id,control_type,process_id)
    actual=str(getattr(control.element_info,"control_type",""))
    if actual not in {"Button","Hyperlink","MenuItem","SplitButton"}:
        raise UIAutomationError(f"UIA Invoke requires a Button, Hyperlink, MenuItem or SplitButton; matched {actual or 'unknown'}")
    try:
        control.invoke()
    except Exception as exc:
        raise UIAutomationError(f"The uniquely selected {actual} does not support UIA Invoke: {type(exc).__name__}: {exc}") from exc


def press(window_title: str, name: str | None, automation_id: str | None,
          control_type: str | None, key: str, process_id: int | None = None) -> None:
    """Focus one exact, non-password UIA control and send one allowlisted key."""
    control = _control(window_title, name, automation_id, control_type, process_id)
    if _is_password(control):
        raise UIAutomationError("Keyboard actions on password controls are blocked; use the credential vault")
    try:
        _window(window_title, process_id).set_focus()
        control.set_focus()
        if not control.has_keyboard_focus():
            raise UIAutomationError("Windows UIA did not confirm keyboard focus on the selected control")
    except Exception as exc:
        if isinstance(exc, UIAutomationError):
            raise
        raise UIAutomationError(f"Could not focus the uniquely selected UIA control: {type(exc).__name__}: {exc}") from exc
    from .desktop_keys import send_key
    send_key(key)


def fill(window_title: str, name: str | None, automation_id: str | None,
         control_type: str | None, value: str, process_id: int | None = None) -> None:
    control = _control(window_title, name, automation_id, control_type, process_id)
    actual_type = str(getattr(control.element_info, "control_type", ""))
    if actual_type != "Edit":
        raise UIAutomationError(f"Set Text requires an Edit control; matched {actual_type or 'unknown'}")
    if _is_password(control):
        raise UIAutomationError("Writing password controls is blocked; use the credential vault")
    control.set_edit_text(value)


def set_range_value(window_title: str, name: str | None, automation_id: str | None,
                    control_type: str | None, value: float, process_id: int | None = None) -> None:
    """Set a Slider or Spinner through UIA RangeValue and verify the result."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise UIAutomationError("Range value must be a finite number")
    control = _control(window_title, name, automation_id, control_type, process_id)
    actual = str(getattr(control.element_info, "control_type", ""))
    if actual not in {"Slider", "Spinner"}:
        raise UIAutomationError(f"Set Range Value requires a Slider or Spinner; matched {actual or 'unknown'}")
    try:
        pattern = control.iface_range_value
        minimum = float(pattern.CurrentMinimum)
        maximum = float(pattern.CurrentMaximum)
        if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
            raise UIAutomationError("The control reported invalid UIA range bounds")
        if bool(pattern.CurrentIsReadOnly):
            raise UIAutomationError("The selected UIA range control is read-only")
        if value < minimum or value > maximum:
            raise UIAutomationError(f"Requested value is outside the control range ({minimum:g} to {maximum:g})")
        pattern.SetValue(float(value))
        observed = float(pattern.CurrentValue)
        if not math.isfinite(observed) or not math.isclose(observed, float(value), rel_tol=1e-9, abs_tol=1e-7):
            raise UIAutomationError("The UIA range control did not retain the requested value")
    except UIAutomationError:
        raise
    except Exception as exc:
        raise UIAutomationError(f"The selected control does not support a writable UIA RangeValue pattern: {type(exc).__name__}: {exc}") from exc


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


def read_grid(window_title: str, name: str | None, automation_id: str | None,
              control_type: str | None, *, max_rows: int = 100,
              max_columns: int = 30, max_output_chars: int = 50_000,
              process_id: int | None = None) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Read bounded records through the native Windows UIA Grid or Table pattern."""
    import json
    import re
    control = _control(window_title, name, automation_id, control_type, process_id)
    if _is_password(control):
        raise UIAutomationError("Reading a password-marked UIA grid is blocked")
    table_data_rows: list[list[Any]] | None=None
    raw_headers: list[str]=[]
    try:
        grid = control.iface_grid
        total_rows = int(grid.CurrentRowCount)
        total_columns = int(grid.CurrentColumnCount)
    except Exception as grid_error:
        if str(getattr(control.element_info,"control_type",""))!="Table" or not getattr(control,"is_table",False):
            raise UIAutomationError(f"The selected control does not expose the UIA Grid or Table pattern: {type(grid_error).__name__}: {grid_error}") from grid_error
        try:
            table_data_rows=[]
            header_candidates=[]
            for row in control.children(content_only=True):
                children=row.children(content_only=True)
                if children and all(str(child.element_info.control_type)=="Header" for child in children):
                    header_candidates.append(children)
                    continue
                row_name=str(getattr(row.element_info,"name","") or "").strip().lower()
                row_type=str(getattr(row.element_info,"control_type",""))
                if row_type!="Custom" or not (row_name.startswith("row ") or any(str(child.element_info.control_type)=="DataItem" for child in children)):
                    continue
                cells=[child for child in children if str(child.element_info.control_type)!="Header"]
                if cells:table_data_rows.append(cells)
            total_rows=len(table_data_rows)
            total_columns=max((len(row) for row in table_data_rows),default=0)
            header_cells=next((candidate for candidate in header_candidates if len(candidate) in {total_columns,total_columns+1}),[])
            if header_cells and len(header_cells)==total_columns+1:header_cells=header_cells[1:]
            raw_headers=[str(cell.window_text() or "").strip() for cell in header_cells]
        except Exception as exc:
            raise UIAutomationError(f"The UIA Table pattern could not expose its rows and columns: {type(exc).__name__}: {exc}") from exc
    else:
        try:
            table=control.iface_table
            headers=list(table.GetCurrentColumnHeaders())
            raw_headers=[str(getattr(item,"CurrentName","") or "").strip() for item in headers]
        except Exception:
            raw_headers=[]
    if total_rows < 0 or total_columns < 0 or total_rows > 1_000_000 or total_columns > 10_000:
        raise UIAutomationError("The UIA Grid or Table reported invalid dimensions")
    row_count = min(total_rows, max_rows)
    column_count = min(total_columns, max_columns)
    raw_headers=raw_headers[:column_count]
    clean_headers=[]
    used: dict[str,int]={}
    for index in range(column_count):
        base=re.sub(r"\s+"," ",raw_headers[index] if index<len(raw_headers) else "").strip() or f"column_{index+1}"
        base=base[:256]
        used[base]=used.get(base,0)+1
        clean_headers.append(base if used[base]==1 else f"{base}_{used[base]}")
    rows: list[dict[str,str]]=[]
    chars=sum(len(header) for header in clean_headers)
    redacted=0
    for row_index in range(row_count):
        record: dict[str,str]={}
        for column_index, header in enumerate(clean_headers):
            try:
                cell=table_data_rows[row_index][column_index] if table_data_rows is not None else control.cell(row_index,column_index)
                if cell is None:
                    value=""
                elif _is_password(cell):
                    value=""
                    redacted+=1
                else:
                    try:value=cell.get_value()
                    except Exception:
                        try:value=cell.iface_value.CurrentValue
                        except Exception:
                            try:value=cell.window_text()
                            except Exception:value=getattr(cell.element_info,"name","")
                    if str(value).strip().lower()=="(null)":value=""
                    value=re.sub(r"\s+"," ",str(value or "")).strip()
            except Exception as exc:
                raise UIAutomationError(f"Could not read UIA grid cell at row {row_index+1}, column {column_index+1}: {type(exc).__name__}: {exc}") from exc
            chars+=len(value)
            if chars>max_output_chars:
                raise UIAutomationError(f"UIA grid text exceeds the configured output limit of {max_output_chars} characters; lower maxRows or maxColumns")
            record[header]=value
        rows.append(record)
    result=json.dumps(rows,ensure_ascii=False,separators=(",",":"))
    if len(result)>max_output_chars:
        raise UIAutomationError(f"UIA grid JSON exceeds the configured output limit of {max_output_chars} characters; lower maxRows or maxColumns")
    metadata={"totalRows":total_rows,"totalColumns":total_columns,"rowsRead":len(rows),
              "columnsRead":len(clean_headers),"truncated":row_count<total_rows or column_count<total_columns,
              "redactedCells":redacted,"outputChars":len(result)}
    return rows,metadata


def select(window_title: str, name: str | None, automation_id: str | None,
           control_type: str | None, value: str, process_id: int | None = None) -> None:
    control=_control(window_title,name,automation_id,control_type,process_id)
    actual=str(getattr(control.element_info,"control_type",""))
    if actual=="ComboBox":
        control.select(value,exact=True)
        selected=str(control.selected_text())
        if selected!=value:raise UIAutomationError("Windows UIA did not select the exact requested ComboBox option")
    elif actual=="List":
        try:
            options=[item for item in control.descendants(control_type="ListItem")
                     if str(item.window_text()).strip()==value]
        except Exception as exc:
            raise UIAutomationError(f"Could not inspect the selected UIA List options: {type(exc).__name__}: {exc}") from exc
        if not options:raise UIAutomationError(f"No List option with the exact accessible name {value!r} was found")
        if len(options)!=1:raise UIAutomationError(f"List option {value!r} is ambiguous: {len(options)} matches")
        try:
            options[0].select()
            if not options[0].is_selected():raise UIAutomationError("Windows UIA did not select the requested List option")
        except UIAutomationError:raise
        except Exception as exc:raise UIAutomationError(f"Windows UIA could not select the requested List option: {type(exc).__name__}: {exc}") from exc
    elif actual in {"ListItem","TreeItem"}:
        if str(control.window_text())!=value:
            raise UIAutomationError(f"{actual} selection requires its exact accessible name as value")
        control.select()
        if not control.is_selected():raise UIAutomationError("Windows UIA did not select the requested List Item")
    else:
        raise UIAutomationError(f"Select Option requires a ComboBox, ListItem, or TreeItem control; matched {actual or 'unknown'}")


def set_selection(window_title: str, name: str | None, automation_id: str | None,
                  control_type: str | None, values: list[str], mode: str = "replace",
                  process_id: int | None = None) -> list[str]:
    """Set a list's selected options through UIA Selection and SelectionItem patterns."""
    control=_control(window_title,name,automation_id,control_type,process_id)
    actual=str(getattr(control.element_info,"control_type",""))
    if actual!="List":raise UIAutomationError(f"Set List Selection requires a List control; matched {actual or 'unknown'}")
    if not isinstance(values,list) or len(values)>100 or any(not isinstance(value,str) or len(value)>512 for value in values):
        raise UIAutomationError("List selection values must be an array of at most 100 names, each no longer than 512 characters")
    if mode not in {"replace","add","remove"}:raise UIAutomationError("List selection mode must be replace, add, or remove")
    if len(set(values))!=len(values):raise UIAutomationError("List selection values must not contain duplicate names")
    if mode!="replace" and not values:raise UIAutomationError("Add and remove selection modes need at least one option name")
    try:
        selection=control.iface_selection
        can_select_multiple=bool(selection.CurrentCanSelectMultiple)
        options=list(control.descendants(control_type="ListItem"))
    except Exception as exc:
        raise UIAutomationError(f"The selected UIA List does not expose a usable Selection pattern: {type(exc).__name__}: {exc}") from exc
    by_name:dict[str,list[Any]]={}
    for option in options:
        option_name=str(option.window_text() or "").strip()
        if option_name:by_name.setdefault(option_name,[]).append(option)
    targets=[]
    for value in values:
        matches=by_name.get(value,[])
        if not matches:raise UIAutomationError(f"No List option with the exact accessible name {value!r} was found")
        if len(matches)!=1:raise UIAutomationError(f"List option {value!r} is ambiguous: {len(matches)} matches")
        targets.append(matches[0])
    if mode=="replace" and len(targets)>1 and not can_select_multiple:
        raise UIAutomationError("This UIA List supports only one selected item; choose one option or use a multi-select List")
    before_names={str(option.window_text() or "").strip() for option in options if option.is_selected()}
    if not can_select_multiple and mode=="add":
        if before_names and any(value not in before_names for value in values):
            raise UIAutomationError("This UIA List supports only one selected item; add mode would replace the current selection")
    target_names=set(values)
    if mode=="replace":
        for option in options:
            if option.is_selected() and str(option.window_text() or "").strip() not in target_names:
                try:option.iface_selection_item.RemoveFromSelection()
                except Exception as exc:raise UIAutomationError(f"Could not clear an existing List selection: {type(exc).__name__}: {exc}") from exc
    if mode in {"replace","add"}:
        for option in targets:
            if option.is_selected():continue
            try:
                current=[candidate for candidate in options if candidate.is_selected()]
                if current:option.iface_selection_item.AddToSelection()
                else:option.select()
            except Exception as exc:raise UIAutomationError(f"Could not select List option {option.window_text()!r}: {type(exc).__name__}: {exc}") from exc
    else:
        for option in targets:
            if option.is_selected():
                try:option.iface_selection_item.RemoveFromSelection()
                except Exception as exc:raise UIAutomationError(f"Could not remove List option {option.window_text()!r}: {type(exc).__name__}: {exc}") from exc
    selected=[str(option.window_text() or "").strip() for option in options if option.is_selected()]
    expected=(target_names if mode=="replace" else
              before_names|target_names if mode=="add" else before_names-target_names)
    if set(selected)!=expected or (mode=="replace" and set(selected)!=target_names):
        raise UIAutomationError("Windows UIA did not reach the requested List selection")
    return selected


def set_expanded(window_title: str, name: str | None, automation_id: str | None,
                 control_type: str | None, expanded: bool, process_id: int | None = None) -> None:
    control=_control(window_title,name,automation_id,control_type,process_id)
    actual=str(getattr(control.element_info,"control_type",""))
    if actual!="TreeItem":
        raise UIAutomationError(f"Expand or Collapse requires a TreeItem; matched {actual or 'unknown'}")
    try:
        state=control.get_expand_state()
        from pywinauto.controls.uiawrapper import uia_defs
        desired=getattr(uia_defs,"expand_state_expanded",1) if expanded else getattr(uia_defs,"expand_state_collapsed",0)
        leaf=getattr(uia_defs,"expand_state_leaf_node",3)
        if state==leaf:raise UIAutomationError("The selected TreeItem is a leaf and cannot be expanded or collapsed")
        if state==desired:return
        (control.expand if expanded else control.collapse)()
        if control.get_expand_state()!=desired:
            raise UIAutomationError("Windows UIA did not reach the requested TreeItem expansion state")
    except UIAutomationError:
        raise
    except Exception as exc:
        action="expand" if expanded else "collapse"
        raise UIAutomationError(f"Windows UIA could not {action} the TreeItem: {type(exc).__name__}: {exc}") from exc


def _checked(control: Any) -> bool | None:
    actual=str(getattr(control.element_info,"control_type",""))
    if actual not in {"CheckBox","RadioButton"}: return None
    if actual=="RadioButton":
        try:return bool(control.is_selected())
        except Exception as exc:raise UIAutomationError(f"The RadioButton does not expose a readable selected state: {type(exc).__name__}: {exc}") from exc
    try:
        value=control.get_toggle_state()
        if value in {0,False}: return False
        if value in {1,True}: return True
        raise UIAutomationError("The control has an indeterminate toggle state")
    except UIAutomationError: raise
    except Exception as exc: raise UIAutomationError(f"The control does not expose a readable toggle state: {type(exc).__name__}: {exc}") from exc


def set_checked(window_title: str, name: str | None, automation_id: str | None,
                control_type: str | None, checked: bool, process_id: int | None = None) -> None:
    control=_control(window_title,name,automation_id,control_type,process_id)
    actual=str(getattr(control.element_info,"control_type",""))
    if actual not in {"CheckBox","RadioButton"}:
        raise UIAutomationError(f"Set Checked requires a CheckBox or RadioButton; matched {actual or 'unknown'}")
    if actual=="RadioButton":
        if not checked:raise UIAutomationError("A RadioButton cannot be unchecked directly; select a different option")
        try:control.select()
        except Exception as exc:raise UIAutomationError(f"Windows UIA could not select the RadioButton: {type(exc).__name__}: {exc}") from exc
        if _checked(control) is not True:raise UIAutomationError("Windows UIA selection did not select the RadioButton")
        return
    before=_checked(control)
    if before is checked:return
    try:control.toggle()
    except Exception as exc:raise UIAutomationError(f"Windows UIA could not toggle the control: {type(exc).__name__}: {exc}") from exc
    after=_checked(control)
    if after is not checked:raise UIAutomationError("Windows UIA toggle action did not reach the requested state")


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
    state={"exists": True, "visible": bool(control.is_visible()), "enabled": bool(control.is_enabled())}
    checked=_checked(control)
    if checked is not None:state["checked"]=checked
    if str(getattr(control.element_info,"control_type","")) in {"ListItem","TreeItem"}:
        try:state["selected"]=bool(control.is_selected())
        except Exception as exc:raise UIAutomationError(f"The accessible item does not expose its selected state: {type(exc).__name__}: {exc}") from exc
    if str(getattr(control.element_info,"control_type",""))=="TreeItem":
        try:
            from pywinauto.controls.uiawrapper import uia_defs
            expand_state=control.get_expand_state()
            if expand_state==getattr(uia_defs,"expand_state_expanded",1):state["expanded"]=True
            elif expand_state==getattr(uia_defs,"expand_state_collapsed",0):state["expanded"]=False
        except Exception:
            pass
    return state


def status() -> dict[str, Any]:
    if sys.platform != "win32":
        return {"available": False, "adapter": "Windows UI Automation", "reason": "This adapter is Windows-only"}
    try:
        _desktop()
        return {"available": True, "adapter": "Windows UI Automation (UIA)", "reason": None}
    except Exception as exc:
        return {"available": False, "adapter": "Windows UI Automation (UIA)",
                "reason": f"UIA runtime unavailable: {type(exc).__name__}: {exc}"}
