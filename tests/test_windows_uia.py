from __future__ import annotations

import json
from pathlib import Path

import pytest

from openrpa import windows_uia
from openrpa.engine import RunOptions, run_project
from openrpa.model import validate_workflow
from openrpa import bridge


class Info:
    def __init__(self, *, name="", auto_id="", control_type="Button", process_id=73, is_password=False):
        self.name=name
        self.automation_id=auto_id
        self.control_type=control_type
        self.process_id=process_id
        self.is_password=is_password
        self.element=type("UIAElement",(),{"CurrentIsPassword":int(is_password)})()


class Control:
    def __init__(self, name="Save", auto_id="save", control_type="Button", *, password=False):
        self.element_info=Info(name=name,auto_id=auto_id,control_type=control_type,is_password=password)
        self.calls=[]
    def is_enabled(self): return True
    def is_visible(self): return True
    def click_input(self): self.calls.append(("click",))
    def set_edit_text(self,value): self.calls.append(("fill",value))
    def get_value(self): return "live-value"
    def window_text(self): return "live-value"


class Window:
    def __init__(self,title="Research Editor",process_id=73,controls=None):
        self.title=title
        self.element_info=Info(process_id=process_id,control_type="Window")
        self.element_info.process_id=process_id
        self._controls=controls or []
    def window_text(self): return self.title
    def descendants(self,**criteria):
        result=self._controls
        if "title" in criteria: result=[item for item in result if item.element_info.name==criteria["title"]]
        if "auto_id" in criteria: result=[item for item in result if item.element_info.automation_id==criteria["auto_id"]]
        if "control_type" in criteria: result=[item for item in result if item.element_info.control_type==criteria["control_type"]]
        return result


class Desktop:
    def __init__(self,windows): self._windows=windows
    def windows(self,**_kwargs): return self._windows


def fake_find_controls(window,criteria):
    return window.descendants(**criteria)


def test_uia_uses_exact_window_and_unique_control_identity(monkeypatch):
    first=Window(controls=[Control()])
    similarly_named=Window("Research Editor — Copy",controls=[Control()])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([first,similarly_named]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    result=windows_uia._control("Research Editor","Save","save","Button",73)
    assert result is first._controls[0]
    assert windows_uia.list_windows()==[{"title":"Research Editor","processId":73,"controlType":"Window"},{"title":"Research Editor — Copy","processId":73,"controlType":"Window"}]


def test_uia_rejects_ambiguous_window_and_control_selectors(monkeypatch):
    duplicate_title=[Window(controls=[Control()]),Window(controls=[Control()])]
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop(duplicate_title))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    with pytest.raises(windows_uia.UIAutomationError,match="specify processId"):
        windows_uia._control("Research Editor","Save",None,None)
    unique_window=Window(controls=[Control("Save",""),Control("Save","")])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([unique_window]))
    with pytest.raises(windows_uia.UIAutomationError,match="ambiguous"):
        windows_uia._control("Research Editor","Save",None,None)


def test_uia_inspection_excludes_password_controls_and_never_returns_values(monkeypatch):
    controls=[Control("Customer name","name","Edit"),Control("Password","password","Edit",password=True)]
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=controls)]))
    rows=windows_uia.list_controls("Research Editor",73)
    assert rows==[{"name":"Customer name","automationId":"name","controlType":"Edit","matchCount":1,"enabled":True,"actions":["wait","fill","text"]}]
    assert "live-value" not in json.dumps(rows)


def test_uia_inspection_counts_duplicate_controls_before_paging(monkeypatch):
    duplicate=Control("Save","save","Button")
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[duplicate,Control("Save","save","Button")])]))
    rows=windows_uia.list_controls("Research Editor",73,limit=1)
    assert rows[0]["name"]=="Save" and rows[0]["matchCount"]==2


def test_uia_fill_requires_edit_and_read_blocks_password(monkeypatch):
    edit=Control("Customer name","name","Edit")
    password=Control("Password","password","Edit",password=True)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[edit,password])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    windows_uia.fill("Research Editor","Customer name","name","Edit","Alice")
    assert edit.calls==[("fill","Alice")]
    with pytest.raises(windows_uia.UIAutomationError,match="password"):
        windows_uia.read_text("Research Editor","Password","password","Edit")


def test_uia_activity_schema_requires_bounded_exact_selector():
    base={"format":"openrpa.workflow","formatVersion":1,"name":"UIA","variables":[],"arguments":[],"activities":[]}
    good={**base,"activities":[{"id":"click","type":"desktop_ui_click","windowTitle":"Editor","automationId":"save","controlType":"Button","timeoutSeconds":10}]}
    assert validate_workflow(good)==[]
    linux_entry={**base,"activities":[{"id":"fill","type":"desktop_ui_fill","windowTitle":"Editor","automationId":"name","controlType":"Entry","value":"Ada"}]}
    assert validate_workflow(linux_entry)==[]
    bad={**base,"activities":[{"id":"bad","type":"desktop_ui_fill","windowTitle":"","name":"","controlType":"Button","value":1,"timeoutSeconds":121}]}
    codes={problem["code"] for problem in validate_workflow(bad)}
    assert {"desktop-uia-window","desktop-uia-selector","desktop-uia-timeout","desktop-uia-fill"}<=codes


def test_desktop_inspector_rpc_requires_explicit_permission(monkeypatch):
    replies=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda *_args,**_kwargs:None)
    bridge.handle({"id":30,"method":"desktop.inspect.windows","params":{"allowDesktop":False}})
    assert "error" in replies[-1]
    assert "explicit desktop permission" in replies[-1]["error"]["message"]


def test_desktop_inspector_rpc_returns_metadata_and_audits_counts(monkeypatch):
    replies=[];events=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda action,details:events.append((action,details)))
    monkeypatch.setattr(windows_uia,"list_windows",lambda *_args:[{"title":"Editor","processId":7,"controlType":"Window"}])
    monkeypatch.setattr(windows_uia,"list_controls",lambda *_args:[{"name":"Save","automationId":"save","controlType":"Button","matchCount":1,"enabled":True}])
    bridge.handle({"id":31,"method":"desktop.inspect.windows","params":{"allowDesktop":True}})
    assert replies[-1]["result"]["windows"][0]["processId"]==7
    bridge.handle({"id":32,"method":"desktop.inspect.controls","params":{"allowDesktop":True,"windowTitle":"Editor","processId":7}})
    assert replies[-1]["result"]["controls"][0]["automationId"]=="save"
    assert events==[("desktop.accessibility_windows_inspected",{"count":1}),("desktop.accessibility_controls_inspected",{"count":1})]


@pytest.mark.parametrize("activity,expected_call",[
    ({"id":"click","type":"desktop_ui_click","windowTitle":"Editor","name":"Save","controlType":"Button"},("click",)),
    ({"id":"fill","type":"desktop_ui_fill","windowTitle":"Editor","automationId":"name","controlType":"Edit","value":"Ada"},("fill","Ada")),
    ({"id":"text","type":"desktop_ui_text","windowTitle":"Editor","automationId":"status","controlType":"Text","result":"status"},None),
])
def test_uia_activities_execute_only_with_permission(monkeypatch,tmp_path,activity,expected_call):
    calls=[]
    monkeypatch.setattr(windows_uia,"status",lambda:{"available":True,"reason":None})
    monkeypatch.setattr(windows_uia,"control_state",lambda *_args:{"exists":True,"visible":True,"enabled":True})
    monkeypatch.setattr(windows_uia,"click",lambda *_args:calls.append(("click",)))
    monkeypatch.setattr(windows_uia,"fill",lambda *_args:calls.append(("fill",_args[4])))
    monkeypatch.setattr(windows_uia,"read_text",lambda *_args:"ready")
    project={"format":"openrpa.project","formatVersion":1,"name":"UIA","main":"Main","workflows":{"Main":"main.json"}}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"UIA","variables":[],"arguments":[],"activities":[activity]}
    (tmp_path/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    denied=run_project(project,tmp_path,options=RunOptions(allow_desktop=False))
    assert denied.status=="failed" and denied.error["code"]=="desktop-permission-denied"
    success=run_project(project,tmp_path,options=RunOptions(allow_desktop=True))
    assert success.status=="succeeded"
    if expected_call: assert calls[-1]==expected_call
    if activity["type"]=="desktop_ui_text": assert success.variables["status"]=="ready"
