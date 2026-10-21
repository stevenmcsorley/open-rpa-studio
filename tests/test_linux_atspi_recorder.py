from __future__ import annotations

from types import SimpleNamespace

from openrpa import linux_atspi_recorder
from openrpa.desktop_recorder import create_desktop_recorder, desktop_recorder_status


class FakeCapture:
    instances = []
    availability = (True, None)

    @classmethod
    def available(cls):
        return cls.availability

    def __init__(self, on_click, on_navigation_key=None, capture_navigation_keys=False):
        self.on_click = on_click
        self.on_navigation_key = on_navigation_key
        self.capture_navigation_keys = capture_navigation_keys
        self.closed = False
        self.__class__.instances.append(self)

    def start(self):
        return None

    def close(self):
        self.closed = True


def _patch_recorder(monkeypatch):
    monkeypatch.setattr(linux_atspi_recorder.sys, "platform", "linux")
    monkeypatch.setattr(linux_atspi_recorder, "X11PointerCapture", FakeCapture)
    from openrpa import linux_atspi
    window = SimpleNamespace(name="QA Editor")
    api = SimpleNamespace(DESKTOP_COORDS=0)
    monkeypatch.setattr(linux_atspi, "_window", lambda *_args: (api, None, window))
    return linux_atspi, api, window


def test_linux_recorder_resolves_clicks_into_editable_selector_activities(monkeypatch):
    linux_atspi, _api, _window = _patch_recorder(monkeypatch)
    recorder = linux_atspi_recorder.LinuxATSPIDesktopRecorder()
    monkeypatch.setattr(recorder, "_resolve_point", lambda x, y: {
        "type": "desktop_ui_invoke", "windowTitle": "QA Editor", "processId": 73,
        "name": "Save", "automationId": "save", "controlType": "Push Button", "timeoutSeconds": 10,
    } if (x, y) == (112, 42) else None)
    started = recorder.start("QA Editor", 73)
    assert started == {"recording": True, "windowTitle": "QA Editor", "processId": 73,
                      "recordKeyboard": False, "mode": "atspi-x11"}
    capture = FakeCapture.instances[-1]
    capture.on_click(112, 42)
    capture.on_click(112, 42)
    capture.on_click(800, 900)
    recorder._queue.join()
    result = recorder.stop()
    assert result["events"] == [{"type": "desktop_ui_invoke", "windowTitle": "QA Editor", "processId": 73,
                                "name": "Save", "automationId": "save", "controlType": "Push Button", "timeoutSeconds": 10}] * 2
    assert result["ignoredClicks"] == 1
    assert result["ignoredKeys"] == 0 and result["recordKeyboard"] is False
    assert capture.closed is True
    assert "112" not in str(result)


def test_linux_recorder_records_only_allowlisted_keys_and_rejects_ambiguous_selectors(monkeypatch):
    linux_atspi, _api, _window = _patch_recorder(monkeypatch)
    recorder = linux_atspi_recorder.LinuxATSPIDesktopRecorder()
    started = recorder.start("QA Editor", 73, True)
    assert started["recordKeyboard"] is True
    recorder.stop()

    class Node:
        def __init__(self, name, role, rect):
            self.name = name
            self.role = role
            self.rect = rect
        def queryComponent(self):
            return SimpleNamespace(getExtents=lambda _coords: self.rect)

    rect = SimpleNamespace(x=10, y=20, width=120, height=48)
    window = Node("QA Editor", "frame", rect)
    button = Node("Save", "push button", rect)
    monkeypatch.setattr(linux_atspi, "_window", lambda *_args: (SimpleNamespace(DESKTOP_COORDS=0), None, window))
    nodes = [button]
    monkeypatch.setattr(linux_atspi, "_walk", lambda _window: list(nodes))
    monkeypatch.setattr(linux_atspi, "_role", lambda node: node.role)
    monkeypatch.setattr(linux_atspi, "_name", lambda node: node.name)
    monkeypatch.setattr(linux_atspi, "_automation_id", lambda _node: "save")
    monkeypatch.setattr(linux_atspi, "_control_type", lambda _node: "Push Button")
    monkeypatch.setattr(linux_atspi, "_visible", lambda _node: True)
    monkeypatch.setattr(linux_atspi, "_enabled", lambda _node: True)
    monkeypatch.setattr(linux_atspi, "_state", lambda _node, _states: True)
    monkeypatch.setattr(linux_atspi, "_protected", lambda *_args: False)
    monkeypatch.setattr(linux_atspi, "_controls", lambda *_args: [button])
    monkeypatch.setattr(linux_atspi, "_state", lambda _node, _states: True)
    recorder._window_title, recorder._process_id = "QA Editor", 73
    assert recorder._resolve_point(30, 30)["type"] == "desktop_ui_invoke"
    assert recorder._resolve_point(500, 500) is None
    nodes.append(Node("Save", "push button", rect))
    assert recorder._resolve_point(30, 30) is None


def test_linux_recorder_attaches_navigation_key_only_to_unique_focused_control(monkeypatch):
    linux_atspi, _api, _window = _patch_recorder(monkeypatch)

    class Node:
        def __init__(self, name, role):
            self.name = name
            self.role = role
    window = Node("QA Editor", "frame")
    focused = Node("Save", "push button")
    api = SimpleNamespace(DESKTOP_COORDS=0)
    monkeypatch.setattr(linux_atspi, "_window", lambda *_args: (api, None, window))
    monkeypatch.setattr(linux_atspi, "_walk", lambda _window: [focused])
    monkeypatch.setattr(linux_atspi, "_role", lambda node: node.role)
    monkeypatch.setattr(linux_atspi, "_name", lambda node: node.name)
    monkeypatch.setattr(linux_atspi, "_automation_id", lambda _node: "save")
    monkeypatch.setattr(linux_atspi, "_control_type", lambda _node: "Push Button")
    monkeypatch.setattr(linux_atspi, "_interactive", lambda role: role == "push button")
    monkeypatch.setattr(linux_atspi, "_visible", lambda _node: True)
    monkeypatch.setattr(linux_atspi, "_enabled", lambda _node: True)
    monkeypatch.setattr(linux_atspi, "_protected", lambda *_args: False)
    monkeypatch.setattr(linux_atspi, "_state", lambda _node, _states: True)
    recorder = linux_atspi_recorder.LinuxATSPIDesktopRecorder()
    recorder._window_title, recorder._process_id = "QA Editor", 73
    assert recorder._resolve_key("Enter") == {
        "type": "desktop_ui_press", "windowTitle": "QA Editor", "processId": 73,
        "name": "Save", "automationId": "save", "controlType": "Push Button", "key": "Enter",
    }


def test_linux_recorder_status_reports_x11_and_atspi_availability(monkeypatch):
    monkeypatch.setattr(linux_atspi_recorder.sys, "platform", "linux")
    monkeypatch.setattr(linux_atspi_recorder, "X11PointerCapture", FakeCapture)
    FakeCapture.availability = (True, None)
    from openrpa import linux_atspi
    monkeypatch.setattr(linux_atspi, "_desktop", lambda: (object(), object()))
    assert linux_atspi_recorder.LinuxATSPIDesktopRecorder.status() == {
        "available": True, "reason": None, "mode": "atspi-x11", "keyboardCapture": True,
    }
    FakeCapture.availability = (False, "No X11")
    assert linux_atspi_recorder.LinuxATSPIDesktopRecorder.status()["available"] is False


def test_linux_desktop_recorder_factory_reports_semantic_mode(monkeypatch):
    monkeypatch.setattr(linux_atspi_recorder.sys, "platform", "linux")
    monkeypatch.setattr(linux_atspi_recorder, "X11PointerCapture", FakeCapture)
    FakeCapture.availability = (True, None)
    from openrpa import linux_atspi
    monkeypatch.setattr(linux_atspi, "_desktop", lambda: (object(), object()))
    assert create_desktop_recorder().__class__.__name__ == "LinuxATSPIDesktopRecorder"
    status = desktop_recorder_status()
    assert status["mode"] == "atspi-x11"
    assert status["keyboardCapture"] is True


def test_atspi_tree_walk_deduplicates_the_same_object_path(monkeypatch):
    from openrpa import linux_atspi
    class Item:
        def __init__(self, path, children=()):
            self.path = path
            self.children = list(children)
    leaf = Item("/leaf")
    repeated_a = Item("/button", [leaf])
    repeated_b = Item("/button", [Item("/leaf")])
    root = Item("/root", [repeated_a, repeated_b])
    monkeypatch.setattr(linux_atspi, "_children", lambda item: iter(item.children))
    monkeypatch.setattr(linux_atspi, "_pid", lambda _item: 73)
    assert list(linux_atspi._walk(root)) == [repeated_a, leaf]


def test_linux_push_button_control_type_validates_as_invoke():
    from openrpa.model import validate_workflow
    workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "AT-SPI invoke", "variables": [], "arguments": [],
                "activities": [{"id": "save", "type": "desktop_ui_invoke", "windowTitle": "QA Editor", "processId": 73,
                                "name": "Save", "controlType": "Push Button", "timeoutSeconds": 10}]}
    assert validate_workflow(workflow) == []
