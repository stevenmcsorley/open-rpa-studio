from __future__ import annotations

import pytest
from types import SimpleNamespace

from openrpa.linux_x11_input import X11PointerCapture, server_event_records


def test_xrecord_parser_strips_each_server_time_prefix():
    first = bytes(range(32))
    second = bytes(range(32, 64))
    payload = b"TIME" + first + b"NEXT" + second
    assert server_event_records(payload) == (first, second)


@pytest.mark.parametrize("payload", [b"", b"short", b"x" * 35, b"x" * 37])
def test_xrecord_parser_rejects_truncated_or_misaligned_events(payload):
    with pytest.raises(ValueError, match="invalid length"):
        server_event_records(payload)


def test_x11_pointer_capture_reports_missing_display(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    available, reason = X11PointerCapture.available()
    assert available is False
    assert "DISPLAY is unset" in reason


def test_x11_keyboard_capture_emits_only_allowlisted_navigation_keys():
    emitted = []
    capture = X11PointerCapture(lambda *_: None, emitted.append, capture_navigation_keys=True)
    mapping = {10: "Control_L", 11: "s", 12: "a", 13: "x", 14: "Tab", 15: "Shift_L"}
    capture._data = SimpleNamespace(keycode_to_keysym=lambda keycode, _index: mapping[keycode])
    x = SimpleNamespace(KeyPress=2, KeyRelease=3)
    xk = SimpleNamespace(keysym_to_string=lambda keysym: keysym, string_to_keysym=lambda name: name)
    def event(kind, keycode):
        capture._handle_key_event(x, xk, SimpleNamespace(type=kind, detail=keycode))
    event(x.KeyPress, 10)
    event(x.KeyPress, 11)
    event(x.KeyRelease, 11)
    event(x.KeyRelease, 10)
    event(x.KeyPress, 10)
    event(x.KeyPress, 12)
    event(x.KeyRelease, 10)
    event(x.KeyPress, 13)
    event(x.KeyPress, 14)
    event(x.KeyRelease, 14)
    event(x.KeyPress, 15)
    event(x.KeyPress, 14)
    assert emitted == ["Ctrl+S", "Ctrl+A", "Tab", "Shift+Tab"]
