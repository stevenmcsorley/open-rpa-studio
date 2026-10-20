from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from openrpa import linux_atspi


class State:
    def __init__(self, values): self.values=set(values)
    def contains(self,value): return value in self.values


class Editable:
    def __init__(self,control): self.control=control
    def setTextContents(self,value): self.control.text=value; return True


class Text:
    def __init__(self,control): self.control=control
    def getText(self,start,end): return self.control.text


class Action:
    nActions=1
    def __init__(self,control): self.control=control
    def getName(self,index): return "click"
    def doAction(self,index): self.control.activated=True; return True


class Accessible:
    def __init__(self,name,role,*,children=(),pid=42,states=(1,2),attrs=None,text="",editable=None):
        self.name=name; self.role=role; self.children=list(children); self.pid=pid
        self.states=State(states); self.attrs=attrs or {}; self.text=text; self.activated=False
        self.editable=(role=="entry") if editable is None else editable
    def getChildCount(self): return len(self.children)
    def getChildAtIndex(self,index): return self.children[index]
    def get_name(self): return self.name
    def getRoleName(self): return self.role
    def get_process_id(self): return self.pid
    def getState(self): return self.states
    def getAttributes(self): return self.attrs
    def queryEditableText(self):
        if not self.editable: raise RuntimeError("not editable")
        return Editable(self)
    def queryText(self): return Text(self)
    def queryAction(self):
        if self.role!="push button": raise RuntimeError("no action interface")
        return Action(self)


def fixture(monkeypatch):
    entry=Accessible("Organisation","text",attrs={"id":"org-name"},states=(1,2,3),text="Old",editable=True)
    button=Accessible("Save","push button",attrs={"id":"save"})
    protected=Accessible("Password","text",attrs={"id":"password"},states=(1,2,3,4),text="secret",editable=True)
    label=Accessible("Status","text",attrs={"id":"status"},text="Ready")
    window=Accessible("Procurement","frame",children=[entry,button,protected,label])
    desktop=Accessible("","desktop",children=[window])
    api=SimpleNamespace(Registry=SimpleNamespace(getDesktop=lambda index:desktop),STATE_VISIBLE=1,
                        STATE_SHOWING=2,STATE_ENABLED=3,STATE_PROTECTED=4)
    monkeypatch.setattr(linux_atspi.sys,"platform","linux")
    monkeypatch.setitem(sys.modules,"pyatspi",api)
    return window,entry,button,protected,label


def test_status_and_window_discovery_use_live_accessibility_bus(monkeypatch):
    fixture(monkeypatch)
    assert linux_atspi.status()=={"available":True,"adapter":"AT-SPI accessibility","reason":None}
    assert linux_atspi.list_windows()==[{"title":"Procurement","processId":42,"controlType":"Frame"}]


def test_control_inspection_excludes_passwords_and_values(monkeypatch):
    fixture(monkeypatch)
    controls=linux_atspi.list_controls("Procurement",42)
    assert [row["name"] for row in controls]==["Organisation","Save","Status"]
    assert controls[0]=={"name":"Organisation","automationId":"org-name","controlType":"Entry","matchCount":1,"enabled":True,"actions":["fill","text","wait"]}
    assert "secret" not in str(controls)


def test_actions_and_text_use_atspi_interfaces(monkeypatch):
    _,entry,button,_,label=fixture(monkeypatch)
    linux_atspi.fill("Procurement","Organisation","org-name","Entry","North")
    linux_atspi.click("Procurement","Save","save","Push Button")
    assert entry.text=="North" and button.activated
    assert linux_atspi.read_text("Procurement","Status","status","Text")=="Ready"
    assert linux_atspi.control_state("Procurement","Save","save","Push Button")=={"exists":True,"visible":True,"enabled":False}


def test_protected_values_are_never_read_or_written(monkeypatch):
    fixture(monkeypatch)
    assert all(row["name"]!="Password" for row in linux_atspi.list_controls("Procurement",42))
    with pytest.raises(linux_atspi.ATSPIError,match="No visible accessible control"):
        linux_atspi.read_text("Procurement","Password","password","Entry")
    with pytest.raises(linux_atspi.ATSPIError,match="No visible accessible control"):
        linux_atspi.fill("Procurement","Password","password","Entry","secret")


def test_ambiguous_windows_and_controls_fail_closed(monkeypatch):
    window,entry,_,_,_=fixture(monkeypatch)
    _,desktop=linux_atspi._desktop()
    desktop.children.append(Accessible("Procurement","frame",pid=43,children=[entry]))
    with pytest.raises(linux_atspi.ATSPIError,match="specify processId"):
        linux_atspi.control_state("Procurement","Organisation",None,"Entry")
    window.children.append(Accessible("Organisation","entry",attrs={"id":"org-name-2"},states=(1,2,3)))
    with pytest.raises(linux_atspi.ATSPIError,match="ambiguous"):
        linux_atspi.fill("Procurement","Organisation",None,"Entry","North",42)


def test_control_count_deduplicates_rows_after_scanning_for_ambiguity(monkeypatch):
    window,_,_,_,_=fixture(monkeypatch)
    window.children.append(Accessible("Save","push button",attrs={"id":"save"}))
    controls=linux_atspi.list_controls("Procurement",42)
    save=next(row for row in controls if row["automationId"]=="save")
    assert save["matchCount"]==2


def test_missing_atspi_dependency_reports_unavailable(monkeypatch):
    monkeypatch.setattr(linux_atspi.sys,"platform","linux")
    monkeypatch.delitem(sys.modules,"pyatspi",raising=False)
    monkeypatch.setattr(linux_atspi,"_module",lambda: (_ for _ in ()).throw(ImportError("not installed")))
    status=linux_atspi.status()
    assert not status["available"] and "runtime unavailable" in status["reason"]
