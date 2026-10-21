from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from openrpa import bridge
from openrpa import desktop_recorder as recorder_module
from openrpa.desktop_recorder import DesktopClickRecorder


class FakeHook:
    def __init__(self):
        self.handler = None
        self.stopped = threading.Event()
        self.started = threading.Event()
        self.keyboard_enabled = None
        self.mouse_enabled = None
        self.keyboard_id = None
        self.mouse_id = None

    def hook(self, *, keyboard, mouse):
        self.keyboard_enabled = keyboard
        self.mouse_enabled = mouse
        self.keyboard_id=object() if keyboard else None
        self.mouse_id=object() if mouse else None
        self.listen()

    def listen(self):
        self.started.set()
        self.stopped.wait(3)

    def stop(self):
        self.stopped.set()

    def click(self, x, y, event_type="key up", key="LButton"):
        self.handler(SimpleNamespace(current_key=key, event_type=event_type, mouse_x=x, mouse_y=y))
    def drag(self, source_x,source_y,target_x,target_y):
        self.handler(SimpleNamespace(current_key="LButton",event_type="key down",mouse_x=source_x,mouse_y=source_y))
        self.handler(SimpleNamespace(current_key="LButton",event_type="key up",mouse_x=target_x,mouse_y=target_y))

    def key(self, name, pressed=(), event_type="key down"):
        self.handler(SimpleNamespace(current_key=name,event_type=event_type,pressed_key=list(pressed)))


def test_windows_click_recorder_scopes_controls_and_never_records_coordinates(monkeypatch):
    monkeypatch.setattr(recorder_module.sys, "platform", "win32")
    from openrpa import windows_uia
    monkeypatch.setattr(windows_uia, "_window", lambda *_args: object())
    hook = FakeHook()
    resolved = []

    def resolve(title, process_id, x, y):
        resolved.append((title, process_id, x, y))
        if (x, y) == (200, 300):
            return {"type": "desktop_ui_click", "windowTitle": title, "processId": process_id,
                    "name": "Save", "automationId": "save", "controlType": "Button", "timeoutSeconds": 10}
        return None

    def resolve_key(title,process_id,key):
        resolved.append((title,process_id,key))
        return {"type":"desktop_ui_press","windowTitle":title,"processId":process_id,
                "name":"Document","automationId":"document","controlType":"Edit",
                "key":key,"timeoutSeconds":10}

    foreground = [("Target App", 42)]
    recorder = DesktopClickRecorder(hook_factory=lambda: hook, resolver=resolve,keyboard_resolver=resolve_key,foreground=lambda: foreground[0])
    started = recorder.start("Target App", 42)
    assert started == {"recording": True, "windowTitle": "Target App", "processId": 42,"recordKeyboard":True,"mode":"windows-uia"}
    assert hook.started.wait(1)
    assert hook.keyboard_enabled is True and hook.mouse_enabled is True
    hook.click(200, 300)
    hook.key("A",["A"])
    hook.key("Enter",["Enter"])
    hook.click(201, 301, event_type="key down")
    deadline = time.monotonic() + 2
    while len(resolved)<2 and time.monotonic() < deadline:
        time.sleep(.01)
    foreground[0] = ("Other App", 99)
    hook.click(900, 900)
    hook.key("Tab",["Tab"])
    time.sleep(.1)
    result = recorder.stop()
    assert result["recording"] is False
    assert result["events"] == [{"type": "desktop_ui_click", "windowTitle": "Target App", "processId": 42,
                                 "name": "Save", "automationId": "save", "controlType": "Button", "timeoutSeconds": 10},
                                {"type":"desktop_ui_press","windowTitle":"Target App","processId":42,
                                 "name":"Document","automationId":"document","controlType":"Edit","key":"Enter","timeoutSeconds":10}]
    assert result["ignoredClicks"] >= 1
    assert result["ignoredKeys"] >= 1
    assert "200" not in str(result) and "300" not in str(result) and "900" not in str(result)
    assert all(event.get("key")!="A" for event in result["events"])
    assert len(resolved) == 2


def test_windows_recorder_turns_accessible_drag_gesture_into_selector_activity(monkeypatch):
    monkeypatch.setattr(recorder_module.sys,"platform","win32")
    from openrpa import windows_uia
    monkeypatch.setattr(windows_uia,"_window",lambda *_args:object())
    hook=FakeHook();resolved=[]
    def resolve_drag(title,pid,sx,sy,tx,ty):
        resolved.append((title,pid,sx,sy,tx,ty))
        return {"type":"desktop_ui_drag","windowTitle":title,"processId":pid,
                "sourceAutomationId":"row-a","targetAutomationId":"row-b","durationMilliseconds":500}
    recorder=DesktopClickRecorder(hook_factory=lambda:hook,drag_resolver=resolve_drag,foreground=lambda:("Target App",42))
    recorder.start("Target App",42,record_keyboard=False)
    hook.drag(100,200,320,420)
    deadline=time.monotonic()+2
    while not resolved and time.monotonic()<deadline:time.sleep(.01)
    result=recorder.stop()
    assert result["events"]==[{"type":"desktop_ui_drag","windowTitle":"Target App","processId":42,
                              "sourceAutomationId":"row-a","targetAutomationId":"row-b","durationMilliseconds":500}]
    assert resolved==[("Target App",42,100,200,320,420)]
    assert not any(str(coord) in str(result) for coord in (100,200,320,420))


def test_desktop_recorder_requires_windows_and_valid_window(monkeypatch):
    recorder = DesktopClickRecorder()
    monkeypatch.setattr(recorder_module.sys, "platform", "linux")
    assert recorder.status()["available"] is False
    with pytest.raises(RuntimeError, match="requires Windows UI Automation"):
        recorder.start("Editor", 1)
    monkeypatch.setattr(recorder_module.sys, "platform", "win32")
    with pytest.raises(ValueError, match="process ID"):
        recorder.start("Editor", 0)


def test_recorder_reports_ready_only_after_required_os_hooks_register(monkeypatch):
    monkeypatch.setattr(recorder_module.sys,"platform","win32")
    from openrpa import windows_uia
    monkeypatch.setattr(windows_uia,"_window",lambda *_args:object())
    class MissingMouseHook(FakeHook):
        def hook(self,*,keyboard,mouse):
            self.keyboard_id=object() if keyboard else None
            self.mouse_id=None
            self.listen()
    with pytest.raises(RuntimeError,match="did not register the mouse event hook"):
        DesktopClickRecorder(hook_factory=MissingMouseHook).start("Target App",42)


def test_desktop_record_rpc_requires_explicit_desktop_permission(monkeypatch):
    replies = []
    monkeypatch.setattr(bridge, "send", replies.append)
    bridge.handle({"id": 80, "method": "desktop.inspect.record.start",
                   "params": {"allowDesktop": False, "windowTitle": "Editor", "processId": 1}})
    assert "error" in replies[-1]
    assert "explicit desktop permission" in replies[-1]["error"]["message"]


def test_desktop_record_rpc_audits_only_counts_and_target_identity(monkeypatch):
    replies = []
    audits = []
    monkeypatch.setattr(bridge, "send", replies.append)
    monkeypatch.setattr(bridge.history, "audit", lambda action, details: audits.append((action, details)))
    monkeypatch.setattr(bridge.desktop_recorder, "start", lambda title, pid, record_keyboard=True: {"recording": True, "windowTitle": title, "processId": pid,"recordKeyboard":record_keyboard})
    monkeypatch.setattr(bridge.desktop_recorder, "stop", lambda: {"recording": False, "windowTitle": "Editor", "processId": 4,
                                                                    "events": [{"type": "desktop_ui_click", "name": "Save"}],
                                                                    "ignoredClicks": 2, "ignoredKeys":1,"truncated": False})
    bridge.handle({"id": 81, "method": "desktop.inspect.record.start",
                   "params": {"allowDesktop": True, "windowTitle": "Editor", "processId": 4}})
    bridge.handle({"id": 82, "method": "desktop.inspect.record.stop", "params": {}})
    assert replies[-1]["result"]["events"][0]["name"] == "Save"
    assert audits == [
        ("desktop.recorder_start", {"processId": 4, "targetScoped": True, "keyboardCapture": True,"mode":None}),
        ("desktop.recorder_stop", {"processId": 4, "eventCount": 1, "ignoredClicks": 2, "ignoredKeys":1,"truncated": False,"mode":None}),
    ]
