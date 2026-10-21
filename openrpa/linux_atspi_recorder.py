"""Record Linux X11 pointer clicks as uniquely identified AT-SPI activities.

The X11 RECORD monitor sees button coordinates only. They are immediately
resolved against one selected AT-SPI window, and only a unique accessible
control selector is returned. Keyboard, text, screenshot, and clipboard data
are never captured. Native Wayland windows are not recordable by this adapter.
"""
from __future__ import annotations

import queue
import sys
import threading
from collections import Counter
from typing import Any

from .linux_x11_input import X11PointerCapture


class LinuxATSPIDesktopRecorder:
    MAX_EVENTS = 300
    MAX_QUEUED_POINTS = 1000

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._recording = False
        self._window_title = ""
        self._process_id = 0
        self._events: list[dict[str, Any]] = []
        self._truncated = False
        self._ignored_clicks = 0
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue(self.MAX_QUEUED_POINTS)
        self._capture: X11PointerCapture | None = None
        self._worker: threading.Thread | None = None
        self._api: Any = None
        self._record_keyboard = False
        self._ignored_keys = 0

    @staticmethod
    def status() -> dict[str, Any]:
        if not sys.platform.startswith("linux"):
            return {"available": False, "reason": "AT-SPI interaction recording is available only on Linux."}
        try:
            from . import linux_atspi
            linux_atspi._desktop()
        except Exception as exc:
            return {"available": False, "reason": f"AT-SPI is unavailable: {type(exc).__name__}: {exc}",
                    "mode": "atspi-x11", "keyboardCapture": False}
        available, reason = X11PointerCapture.available()
        return {"available": available, "reason": reason, "mode": "atspi-x11",
                "keyboardCapture": available}

    def start(self, window_title: str, process_id: int, record_keyboard: bool = False) -> dict[str, Any]:
        if not sys.platform.startswith("linux"):
            raise RuntimeError(self.status()["reason"])
        if not isinstance(window_title, str) or not window_title.strip() or len(window_title) > 512:
            raise ValueError("Select one accessible application window before recording")
        if not isinstance(process_id, int) or isinstance(process_id, bool) or process_id < 1:
            raise ValueError("The selected application window needs a valid process ID")
        if not isinstance(record_keyboard, bool):
            raise ValueError("recordKeyboard must be a boolean")
        from . import linux_atspi
        api, _, _ = linux_atspi._window(window_title, process_id)
        with self._lock:
            if self._recording:
                raise RuntimeError("Desktop recording is already active")
            self._api = api
            self._window_title = window_title
            self._process_id = process_id
            self._events = []
            self._truncated = False
            self._ignored_clicks = 0
            self._ignored_keys = 0
            self._record_keyboard = record_keyboard
            self._queue = queue.Queue(self.MAX_QUEUED_POINTS)
            self._recording = True
            self._worker = threading.Thread(target=self._process_points, name="openrpa-atspi-click-resolver", daemon=True)
            self._worker.start()
            self._capture = X11PointerCapture(self._enqueue_point, self._enqueue_key, record_keyboard)
        try:
            self._capture.start()
        except Exception:
            with self._lock:
                self._recording = False
            self.stop()
            raise
        return {"recording": True, "windowTitle": self._window_title, "processId": self._process_id,
                "recordKeyboard": self._record_keyboard, "mode": "atspi-x11"}

    def _enqueue_point(self, x: int, y: int) -> None:
        with self._lock:
            if not self._recording:
                return
        try:
            self._queue.put_nowait(("click", (x, y)))
        except queue.Full:
            with self._lock:
                self._truncated = True

    def _enqueue_key(self, key: str) -> None:
        with self._lock:
            if not self._recording or not self._record_keyboard:
                return
        try:
            self._queue.put_nowait(("key", key))
        except queue.Full:
            with self._lock:
                self._truncated = True

    @staticmethod
    def _bounds(api: Any, control: Any) -> tuple[int, int, int, int] | None:
        try:
            rect = control.queryComponent().getExtents(api.DESKTOP_COORDS)
            x, y, width, height = int(rect.x), int(rect.y), int(rect.width), int(rect.height)
            if width <= 0 or height <= 0:
                return None
            return x, y, width, height
        except Exception:
            return None

    def _resolve_point(self, x: int, y: int) -> dict[str, Any] | None:
        from . import linux_atspi
        api, _, window = linux_atspi._window(self._window_title, self._process_id)
        window_bounds = self._bounds(api, window)
        try:
            active = linux_atspi._state(window, ("STATE_ACTIVE",))
        except Exception:
            return None
        if not active or window_bounds is None or not self._contains(window_bounds, x, y):
            return None

        nodes = list(linux_atspi._walk(window))
        selector_counts = self._selector_counts(linux_atspi, api, nodes)
        candidates: list[tuple[int, Any, str, str, str]] = []
        for control in nodes:
            role = linux_atspi._role(control)
            if role not in {"push button", "toggle button", "check box", "radio button", "link", "menu item"}:
                continue
            try:
                if not linux_atspi._visible(control) or not linux_atspi._enabled(control):
                    continue
                if linux_atspi._protected(api, control):
                    continue
            except Exception:
                continue
            bounds = self._bounds(api, control)
            if bounds is None or not self._contains(bounds, x, y):
                continue
            name = linux_atspi._name(control)[:512]
            automation_id = linux_atspi._automation_id(control)[:512]
            control_type = linux_atspi._control_type(control)
            if not name and not automation_id:
                continue
            if selector_counts[(name, automation_id, control_type.lower())] != 1:
                continue
            area = bounds[2] * bounds[3]
            candidates.append((area, control, name, automation_id, control_type))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        smallest = candidates[0][0]
        best = [item for item in candidates if item[0] == smallest]
        if len(best) != 1:
            return None
        _, control, name, automation_id, control_type = best[0]
        role = linux_atspi._role(control)
        if role in {"check box", "radio button"}:
            checked = linux_atspi._state(control, ("STATE_CHECKED",))
            kind = "desktop_ui_check" if checked else "desktop_ui_uncheck"
        else:
            kind = "desktop_ui_invoke"
        return {"type": kind, "windowTitle": self._window_title, "processId": self._process_id,
                "name": name, "automationId": automation_id, "controlType": control_type,
                "timeoutSeconds": 10}

    def _resolve_key(self, key: str) -> dict[str, Any] | None:
        from . import linux_atspi
        api, _, window = linux_atspi._window(self._window_title, self._process_id)
        try:
            if not linux_atspi._state(window, ("STATE_ACTIVE",)):
                return None
        except Exception:
            return None
        nodes = list(linux_atspi._walk(window))
        selector_counts = self._selector_counts(linux_atspi, api, nodes)
        focused: list[tuple[Any, str, str, str]] = []
        for control in nodes:
            if not linux_atspi._interactive(linux_atspi._role(control)):
                continue
            try:
                if (not linux_atspi._visible(control) or not linux_atspi._enabled(control)
                        or linux_atspi._protected(api, control)
                        or not linux_atspi._state(control, ("STATE_FOCUSED",))):
                    continue
            except Exception:
                continue
            name = linux_atspi._name(control)[:512]
            automation_id = linux_atspi._automation_id(control)[:512]
            control_type = linux_atspi._control_type(control)
            if (name or automation_id) and selector_counts[(name, automation_id, control_type.lower())] == 1:
                focused.append((control, name, automation_id, control_type))
        if len(focused) != 1:
            return None
        _, name, automation_id, control_type = focused[0]
        return {"type": "desktop_ui_press", "windowTitle": self._window_title,
                "processId": self._process_id, "name": name, "automationId": automation_id,
                "controlType": control_type, "key": key}

    @staticmethod
    def _selector_counts(linux_atspi: Any, api: Any, nodes: list[Any]) -> Counter[tuple[str, str, str]]:
        counts: Counter[tuple[str, str, str]] = Counter()
        for control in nodes:
            if not linux_atspi._interactive(linux_atspi._role(control)):
                continue
            try:
                if not linux_atspi._visible(control) or linux_atspi._protected(api, control):
                    continue
            except Exception:
                continue
            name = linux_atspi._name(control)[:512]
            automation_id = linux_atspi._automation_id(control)[:512]
            if name or automation_id:
                control_type = linux_atspi._control_type(control)
                counts[(name, automation_id, control_type.lower())] += 1
        return counts

    @staticmethod
    def _contains(bounds: tuple[int, int, int, int], x: int, y: int) -> bool:
        left, top, width, height = bounds
        return left <= x < left + width and top <= y < top + height

    def _process_points(self) -> None:
        while True:
            with self._lock:
                if not self._recording and self._queue.empty():
                    return
            try:
                kind, payload = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                activity = self._resolve_point(*payload) if kind == "click" else self._resolve_key(str(payload))
                with self._lock:
                    if activity is None:
                        if kind == "click":
                            self._ignored_clicks += 1
                        else:
                            self._ignored_keys += 1
                    elif self._recording and len(self._events) < self.MAX_EVENTS:
                        self._events.append(activity)
                    else:
                        self._truncated = True
            except Exception:
                # Never retain input coordinates, raw event data, or provider errors.
                with self._lock:
                    if kind == "click":
                        self._ignored_clicks += 1
                    else:
                        self._ignored_keys += 1
            finally:
                self._queue.task_done()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._recording = False
            capture, worker = self._capture, self._worker
        if capture is not None:
            capture.close()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=3)
        with self._lock:
            self._capture = None
            self._worker = None
            result = {"recording": False, "windowTitle": self._window_title,
                      "processId": self._process_id, "events": list(self._events),
                      "truncated": self._truncated, "ignoredClicks": self._ignored_clicks,
                      "ignoredKeys": self._ignored_keys, "recordKeyboard": self._record_keyboard,
                      "mode": "atspi-x11"}
            self._api = None
            return result

    def close(self) -> None:
        self.stop()
