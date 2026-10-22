"""Explicit, selector-only Windows desktop interaction recording."""
from __future__ import annotations

import queue
import sys
import threading
from typing import Any, Callable


class DesktopClickRecorder:
    """Observe bounded interactions in one selected foreground app and resolve through UIA.

    Pointer coordinates are transient and used only for UIA hit testing. An
    optional keyboard hook records only an allowlist of named navigation keys
    and shortcuts; printable keys and typed values are discarded in the hook
    callback and never enter the queue.
    """

    MAX_EVENTS = 300
    MAX_QUEUED_POINTS = 1000

    def __init__(self, *, hook_factory: Callable[[], Any] | None = None,
                 resolver: Callable[[str, int, int, int], dict[str, Any] | None] | None = None,
                 drag_resolver: Callable[[str, int, int, int, int, int], dict[str, Any] | None] | None = None,
                 keyboard_resolver: Callable[[str, int, str], dict[str, Any] | None] | None = None,
                 text_resolver: Callable[[str, int, str], dict[str, Any] | None] | None = None,
                 foreground: Callable[[], tuple[str, int]] | None = None):
        self._hook_factory = hook_factory
        self._resolver = resolver
        self._drag_resolver = drag_resolver
        self._foreground = foreground
        self._keyboard_resolver = keyboard_resolver
        self._text_resolver = text_resolver
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue(self.MAX_QUEUED_POINTS)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._hook: Any = None
        self._hook_thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._window_title = ""
        self._process_id = 0
        self._events: list[dict[str, Any]] = []
        self._recording = False
        self._truncated = False
        self._ignored_clicks = 0
        self._ignored_keys = 0
        self._record_keyboard = True
        self._record_text = False
        self._error: str | None = None
        self._mouse_down: tuple[int,int] | None = None

    @staticmethod
    def status() -> dict[str, Any]:
        if sys.platform != "win32":
            return {"available": False, "reason": "Selector-based desktop action recording currently requires Windows UI Automation."}
        try:
            from pywinauto import win32_hooks  # noqa: F401
            from . import windows_uia
            probe = windows_uia.status()
            if not probe.get("available"):
                return {"available": False, "reason": probe.get("reason") or "Windows UI Automation is unavailable."}
            return {"available": True, "reason": None,"mode":"windows-uia","keyboardCapture":True,"textCapture":True}
        except Exception as exc:
            return {"available": False, "reason": f"Windows UIA recorder unavailable: {type(exc).__name__}: {exc}"}

    def start(self, window_title: str, process_id: int, record_keyboard: bool = True, record_text: bool = False) -> dict[str, Any]:
        if sys.platform != "win32":
            raise RuntimeError(self.status()["reason"])
        if not isinstance(window_title, str) or not window_title.strip() or len(window_title) > 512:
            raise ValueError("Select one visible application window before recording")
        if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id < 1:
            raise ValueError("The selected application window needs a valid process ID")
        if not isinstance(record_keyboard,bool) or not isinstance(record_text,bool):
            raise ValueError("recordKeyboard and recordText must be booleans")
        with self._lock:
            if self._recording:
                raise RuntimeError("Desktop recording is already active")
            from . import windows_uia
            windows_uia._window(window_title, process_id)
            self._window_title = window_title
            self._process_id = process_id
            self._events = []
            self._truncated = False
            self._ignored_clicks = 0
            self._ignored_keys = 0
            self._record_keyboard = record_keyboard
            self._record_text = record_text
            self._error = None
            self._mouse_down = None
            self._stop.clear()
            self._ready.clear()
            self._queue = queue.Queue(self.MAX_QUEUED_POINTS)
            self._recording = True
            self._hook_thread = threading.Thread(target=self._listen, name="openrpa-desktop-hook", daemon=True)
            self._hook_thread.start()
        if not self._ready.wait(3):
            self.stop()
            raise RuntimeError("Windows desktop input hook did not become ready within 3 seconds")
        if self._error:
            error = self._error
            self.stop()
            raise RuntimeError(error)
        self._worker = threading.Thread(target=self._process_events, name="openrpa-desktop-recorder", daemon=True)
        self._worker.start()
        return {"recording": True, "windowTitle": self._window_title, "processId": self._process_id,
                "recordKeyboard": self._record_keyboard,"recordText":self._record_text,"mode":"windows-uia"}

    def _listen(self) -> None:
        try:
            factory = self._hook_factory
            if factory is None:
                from pywinauto.win32_hooks import Hook
                factory = Hook
            hook = factory()
            hook.handler = self._on_hook_event
            self._hook = hook
            listen=getattr(hook,"listen",None)
            if callable(listen):
                def listen_after_registration() -> Any:
                    if getattr(hook,"mouse_id",None) is None:
                        raise RuntimeError("Windows did not register the mouse event hook")
                    if (self._record_keyboard or self._record_text) and getattr(hook,"keyboard_id",None) is None:
                        raise RuntimeError("Windows did not register the keyboard event hook")
                    self._ready.set()
                    return listen()
                hook.listen=listen_after_registration
            else:
                # Lightweight hook doubles used in tests may signal readiness
                # from hook(); the real pywinauto Hook exposes listen().
                self._ready.set()
            hook.hook(keyboard=self._record_keyboard or self._record_text, mouse=True)
        except Exception as exc:
            self._error = f"Windows desktop input hook failed: {type(exc).__name__}: {exc}"
            self._ready.set()
        finally:
            self._stop.set()

    def _on_hook_event(self, event: Any) -> None:
        event_type=getattr(event,"event_type",None)
        if getattr(event,"current_key",None)=="LButton" and event_type in {"key down","key up"}:
            point=(int(event.mouse_x),int(event.mouse_y))
            if event_type=="key down":
                with self._lock:
                    if self._recording:self._mouse_down=point
                return
            with self._lock:
                start=self._mouse_down
                self._mouse_down=None
            if start is not None and (abs(point[0]-start[0])>6 or abs(point[1]-start[1])>6):
                queued=("drag",(*start,*point))
            else:
                queued=("click",point)
        elif self._record_keyboard or self._record_text:
            key=None
            if self._record_keyboard:
                from .desktop_keys import recordable_key_from_event
                key=recordable_key_from_event(event)
            if key is not None:
                queued=("key",key)
            elif self._record_text:
                from .desktop_keys import recordable_text_from_event
                text=recordable_text_from_event(event)
                if text is None:return
                queued=("text",text)
            else:return
        else:return
        with self._lock:
            if not self._recording or len(self._events) >= self.MAX_EVENTS:
                self._truncated = True
                return
        try:
            self._queue.put_nowait(queued)
        except queue.Full:
            with self._lock:
                self._truncated = True

    def _foreground_identity(self) -> tuple[str, int]:
        if self._foreground is not None:
            return self._foreground()
        import win32gui
        import win32process
        hwnd = win32gui.GetForegroundWindow()
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        return str(win32gui.GetWindowText(hwnd) or ""), int(process_id)

    def _process_events(self) -> None:
        resolver = self._resolver
        key_resolver=self._keyboard_resolver
        text_resolver=self._text_resolver
        drag_resolver=self._drag_resolver
        if resolver is None:
            from .windows_uia import click_activity_at_point
            resolver = click_activity_at_point
        if key_resolver is None:
            from .windows_uia import key_activity_for_focused_control
            key_resolver=key_activity_for_focused_control
        if text_resolver is None:
            from .windows_uia import text_activity_for_focused_control
            text_resolver=text_activity_for_focused_control
        if drag_resolver is None:
            from .windows_uia import drag_activity_between_points
            drag_resolver=drag_activity_between_points
        while not self._stop.is_set() or not self._queue.empty():
            try:
                kind,payload=self._queue.get(timeout=.05)
            except queue.Empty:
                continue
            try:
                title, process_id = self._foreground_identity()
                if title != self._window_title or process_id != self._process_id:
                    with self._lock:
                        if kind=="key":self._ignored_keys+=1
                        else:self._ignored_clicks+=1
                    continue
                if kind=="click":
                    x,y=payload
                    activity=resolver(self._window_title,self._process_id,x,y)
                elif kind=="drag":
                    source_x,source_y,target_x,target_y=payload
                    activity=drag_resolver(self._window_title,self._process_id,source_x,source_y,target_x,target_y)
                else:
                    activity=(text_resolver(self._window_title,self._process_id,str(payload)) if kind=="text"
                              else key_resolver(self._window_title,self._process_id,str(payload)))
                with self._lock:
                    if activity is None:
                        if kind in {"key","text"}:self._ignored_keys+=1
                        else:self._ignored_clicks+=1
                    elif len(self._events) < self.MAX_EVENTS:
                        if kind=="text" and self._events and self._events[-1].get("type")=="desktop_recorded_text" and all(self._events[-1].get(key)==activity.get(key) for key in ("windowTitle","processId","name","automationId","controlType")) and len(self._events[-1].get("value",""))<10000:
                            self._events[-1]["value"]+=str(activity.get("value",""))
                        else:self._events.append(activity)
                    else:
                        self._truncated = True
            except Exception:
                # Never persist hook coordinates, raw key events or adapter errors.
                with self._lock:
                    if kind in {"key","text"}:self._ignored_keys+=1
                    else:self._ignored_clicks+=1
            finally:
                self._queue.task_done()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._recording = False
            hook = self._hook
            hook_thread = self._hook_thread
            worker = self._worker
        self._stop.set()
        if hook is not None:
            try:
                hook.stop()
            except Exception:
                pass
        if hook_thread is not None and hook_thread is not threading.current_thread():
            hook_thread.join(timeout=3)
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=3)
        with self._lock:
            self._hook = None
            self._hook_thread = None
            self._worker = None
            return {"recording": False, "windowTitle": self._window_title,
                    "processId": self._process_id, "events": list(self._events),
                    "truncated": self._truncated, "ignoredClicks": self._ignored_clicks,
                    "ignoredKeys": self._ignored_keys,"recordKeyboard":self._record_keyboard,"recordText":self._record_text,"mode":"windows-uia"}

    def close(self) -> None:
        self.stop()


def create_desktop_recorder() -> Any:
    """Select the semantic recorder for the active desktop platform."""
    if sys.platform.startswith("linux"):
        from .linux_atspi_recorder import LinuxATSPIDesktopRecorder
        return LinuxATSPIDesktopRecorder()
    return DesktopClickRecorder()


def desktop_recorder_status() -> dict[str,Any]:
    if sys.platform.startswith("linux"):
        from .linux_atspi_recorder import LinuxATSPIDesktopRecorder
        return LinuxATSPIDesktopRecorder.status()
    return DesktopClickRecorder.status()
