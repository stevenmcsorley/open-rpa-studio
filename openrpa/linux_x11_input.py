"""Bounded Linux X11 pointer capture used to build AT-SPI selectors.

Only primary-button press coordinates are delivered to the caller. No key
events, screenshots, clipboard contents, or raw event payloads are retained.
The caller must resolve coordinates to a unique accessible control before
creating a workflow activity.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable


class X11PointerCapture:
    def __init__(self, on_click: Callable[[int, int], None],
                 on_navigation_key: Callable[[str], None] | None = None,
                 capture_navigation_keys: bool = False) -> None:
        self._on_click = on_click
        self._on_navigation_key = on_navigation_key
        self._capture_navigation_keys = capture_navigation_keys
        self._pressed_modifiers: set[str] = set()
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._control: Any = None
        self._data: Any = None
        self._context: int | None = None
        self._thread: threading.Thread | None = None
        self._error: str | None = None

    @staticmethod
    def available() -> tuple[bool, str | None]:
        if not os.environ.get("DISPLAY"):
            return False, "Linux desktop recording requires an X11 or XWayland display (DISPLAY is unset)."
        try:
            from Xlib import display
            probe = display.Display()
            try:
                extension = probe.query_extension("RECORD")
                if not extension.present:
                    return False, "The active X11 server does not expose the RECORD input extension."
            finally:
                probe.close()
        except Exception as exc:
            return False, f"X11 pointer recording is unavailable: {type(exc).__name__}: {exc}"
        return True, None

    def start(self) -> None:
        available, reason = self.available()
        if not available:
            raise RuntimeError(reason or "X11 pointer recording is unavailable")
        from Xlib import display, X
        from Xlib.ext import record

        self._control = display.Display()
        self._data = display.Display()
        ranges = [{
            "core_requests": (0, 0),
            "core_replies": (0, 0),
            "ext_requests": (0, 0, 0, 0),
            "ext_replies": (0, 0, 0, 0),
            "delivered_events": (0, 0),
            "device_events": ((X.KeyPress, X.ButtonPress) if self._capture_navigation_keys
                              else (X.ButtonPress, X.ButtonPress)),
            "errors": (0, 0),
            "client_started": False,
            "client_died": False,
        }]
        try:
            self._context = self._control.record_create_context(
                record.FromServerTime, [record.AllClients], ranges)
            self._control.flush()
            self._thread = threading.Thread(target=self._listen, name="openrpa-x11-pointer", daemon=True)
            self._thread.start()
            if not self._ready.wait(3):
                raise RuntimeError("X11 input listener did not become ready within 3 seconds")
            if self._error:
                raise RuntimeError(self._error)
        except Exception:
            self.close()
            raise

    def _listen(self) -> None:
        from Xlib.ext import record
        from Xlib.protocol import rq
        from Xlib import X, XK

        def receive(reply: Any) -> None:
            if reply.category == record.StartOfData:
                self._ready.set()
                return
            if reply.category == record.EndOfData:
                return
            if reply.category != record.FromServer or not reply.data:
                return
            # FromServerTime prefixes each 32-byte core event with a 4-byte
            # server timestamp. The selected range is only ButtonPress.
            try:
                records = list(server_event_records(reply.data))
            except ValueError:
                self._error = "X11 returned a malformed pointer event batch"
                self._ready.set()
                return
            for event_data in records:
                try:
                    event, remainder = rq.EventField(None).parse_binary_value(
                        event_data, self._data.display, None, None)
                    if remainder:
                        continue
                    if event.type == X.ButtonPress and int(event.detail) == 1:
                        self._on_click(int(event.root_x), int(event.root_y))
                    elif self._capture_navigation_keys and event.type in {X.KeyPress, X.KeyRelease}:
                        self._handle_key_event(X, XK, event)
                except Exception:
                    # Do not retain or surface raw input event payloads.
                    continue

        try:
            self._data.record_enable_context(self._context, receive)
        except Exception as exc:
            with self._lock:
                if self._context is not None:
                    self._error = f"X11 input listener failed: {type(exc).__name__}: {exc}"
            self._ready.set()

    def _handle_key_event(self, X: Any, XK: Any, event: Any) -> None:
        from types import SimpleNamespace
        from .desktop_keys import recordable_key_from_event

        keysym = self._data.keycode_to_keysym(int(event.detail), 0)
        key_name = XK.keysym_to_string(keysym) if keysym else None
        special_keys = {
            "Return": "Enter", "Tab": "Tab", "Escape": "Escape", "Space": "Space",
            "Up": "Up", "Down": "Down", "Left": "Left", "Right": "Right",
            "Home": "Home", "End": "End", "Prior": "PageUp", "Next": "PageDown",
            "BackSpace": "Backspace", "Delete": "Delete", "Insert": "Insert",
            **{f"F{number}": f"F{number}" for number in range(1, 13)},
        }
        for symbol_name, canonical in special_keys.items():
            if keysym == XK.string_to_keysym(symbol_name):
                key_name = canonical
                break
        if not key_name:
            return
        modifiers = {
            "Control_L": "lcontrol", "Control_R": "rcontrol",
            "Shift_L": "lshift", "Shift_R": "rshift",
            "Alt_L": "lmenu", "Alt_R": "rmenu",
        }
        if key_name in modifiers:
            modifier = modifiers[key_name]
            if event.type == X.KeyPress:
                self._pressed_modifiers.add(modifier)
            else:
                self._pressed_modifiers.discard(modifier)
            return
        if event.type != X.KeyPress or self._on_navigation_key is None:
            return
        aliases = {"Prior": "PageUp", "Next": "PageDown", "BackSpace": "Backspace",
                   "ISO_Left_Tab": "Tab", "Esc": "Escape"}
        key_name = aliases.get(key_name, key_name)
        # recordable_key_from_event only returns explicitly allowlisted
        # navigation keys and shortcuts; printable symbols resolve to None.
        recorded = recordable_key_from_event(SimpleNamespace(
            event_type="key down", current_key=key_name, pressed_key=tuple(self._pressed_modifiers)))
        if recorded:
            self._on_navigation_key(recorded)

    def close(self) -> None:
        control, data, context, thread = self._control, self._data, self._context, self._thread
        self._context = None
        if control is not None and context is not None:
            try:
                control.record_disable_context(context)
                control.flush()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        if control is not None and context is not None:
            try:
                control.record_free_context(context)
            except Exception:
                pass
        for connection in (data, control):
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        self._control = self._data = self._thread = None


def server_event_records(payload: bytes) -> tuple[bytes, ...]:
    """Split FromServerTime XRecord data and remove its 4-byte time prefix."""
    stride = 36
    if not payload or len(payload) % stride:
        raise ValueError("XRecord server event data has an invalid length")
    return tuple(payload[offset + 4:offset + stride] for offset in range(0, len(payload), stride))
