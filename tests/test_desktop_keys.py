from __future__ import annotations

from types import SimpleNamespace

import pytest

from openrpa.desktop_keys import normalize_key, recordable_key_from_event, recordable_text_from_event, send_key
from openrpa.model import validate_workflow


@pytest.mark.parametrize(("value", "expected"), [
    ("Enter", ("enter",)), ("pageDown", ("pagedown",)),
    ("Ctrl+Shift+S", ("ctrl", "shift", "s")), ("Alt+Left", ("alt", "left")),
])
def test_normalizes_supported_navigation_keys_and_shortcuts(value, expected):
    assert normalize_key(value) == expected


@pytest.mark.parametrize("value", ["Ctrl+C", "Alt+F4", "Ctrl+Alt+Delete", "type:secret", "A;B"])
def test_rejects_unbounded_or_sensitive_shortcuts(value):
    with pytest.raises(ValueError, match="Unsupported desktop key"):
        normalize_key(value)


def test_sends_only_the_normalized_key_or_allowlisted_chord():
    calls = []
    api = SimpleNamespace(press=lambda key: calls.append(("press", key)),
                          hotkey=lambda *keys: calls.append(("hotkey", *keys)))
    send_key("Enter", pyautogui_module=api)
    send_key("Ctrl+S", pyautogui_module=api)
    assert calls == [("press", "enter"), ("hotkey", "ctrl", "s")]


@pytest.mark.parametrize(("name","pressed","event_type","expected"),[
    ("A",["A"],"key down",None),("A",["Lcontrol","A"],"key down","Ctrl+A"),
    ("Return",["Return"],"key down","Enter"),("Tab",["Lshift","Tab"],"key down","Shift+Tab"),
    ("F4",["Lalt","F4"],"key down",None),("C",["Lcontrol","C"],"key down",None),
    ("Enter",["Enter"],"key up",None),
    ("Enter",None,"key down","Enter"),
])
def test_recorder_filters_printable_and_disallowed_keyboard_events(name,pressed,event_type,expected):
    event=SimpleNamespace(current_key=name,pressed_key=pressed,event_type=event_type)
    assert recordable_key_from_event(event)==expected


@pytest.mark.parametrize(("name","pressed","expected"),[("h",["h"],"h"),("A",["Lshift","A"],"A"),("1",["Lshift","1"],"!"),("Space",["Space"]," "),("A",["Lcontrol","A"],None),("F4",["Lalt","F4"],None),("Return",["Return"],None)])
def test_opt_in_text_capture_extracts_only_bounded_printable_characters(name,pressed,expected):
    assert recordable_text_from_event(SimpleNamespace(current_key=name,pressed_key=pressed,event_type="key down"))==expected


def test_disabling_keyboard_capture_disables_the_recordable_event_set(monkeypatch):
    from openrpa.desktop_recorder import DesktopClickRecorder
    recorder=DesktopClickRecorder()
    recorder._recording=True
    recorder._record_keyboard=False
    recorder._on_hook_event(SimpleNamespace(current_key="Enter",event_type="key down",pressed_key=["Enter"]))
    assert recorder._queue.empty()


def test_semantic_desktop_press_schema_accepts_only_supported_shortcuts():
    base = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Key test",
            "variables": [], "arguments": [], "activities": [{
                "id": "press-enter", "type": "desktop_ui_press", "windowTitle": "Editor",
                "name": "Document", "automationId": "document", "controlType": "Edit", "key": "Enter"}]}
    assert validate_workflow(base) == []
    invalid = {**base, "activities": [{**base["activities"][0], "key": "Alt+F4"}]}
    assert "desktop-uia-key" in {item["code"] for item in validate_workflow(invalid)}
