from __future__ import annotations

import sys
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from openrpa import linux_atspi
from openrpa.engine import RunOptions, run_project


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
    def doAction(self,index):
        self.control.activated=True
        checked=getattr(sys.modules.get("pyatspi"),"STATE_CHECKED",None)
        if checked is not None and self.control.role in {"check box","radio button"}:
            if checked in self.control.states.values:self.control.states.values.remove(checked)
            else:self.control.states.values.add(checked)
        return True


class TreeAction:
    nActions=1
    def __init__(self,control):self.control=control
    def getName(self,index):return "expand or collapse"
    def doAction(self,index):
        expanded=getattr(sys.modules.get("pyatspi"),"STATE_EXPANDED",None)
        if expanded is None:return False
        if expanded in self.control.states.values:self.control.states.values.remove(expanded)
        else:self.control.states.values.add(expanded)
        return True


class Selection:
    def __init__(self,control):self.control=control;self.index=None
    def selectChild(self,index):self.index=index;return True


class Accessible:
    def __init__(self,name,role,*,children=(),pid=42,states=(1,2),attrs=None,text="",editable=None):
        self.name=name; self.role=role; self.children=list(children); self.pid=pid
        self.parent=None
        for child in self.children:child.parent=self
        self.states=State(states); self.attrs=attrs or {}; self.text=text; self.activated=False
        self.focused=False
        self.editable=(role=="entry") if editable is None else editable
    def getChildCount(self): return len(self.children)
    def getChildAtIndex(self,index): return self.children[index]
    def get_name(self): return self.name
    def getRoleName(self): return self.role
    def get_process_id(self): return self.pid
    def get_parent(self):return self.parent
    def getState(self): return self.states
    def getAttributes(self): return self.attrs
    def grabFocus(self): self.focused=True; self.states.values.add(6); return True
    def queryEditableText(self):
        if not self.editable: raise RuntimeError("not editable")
        return Editable(self)
    def queryText(self): return Text(self)
    def queryValue(self):
        if not hasattr(self,"value_interface"):raise RuntimeError("no value interface")
        return self.value_interface
    def queryAction(self):
        if self.role=="tree item":return TreeAction(self)
        if self.role not in {"push button","check box","radio button"}: raise RuntimeError("no action interface")
        return Action(self)
    def querySelection(self):
        if self.role not in {"combo box","list box","tree","frame"}:raise RuntimeError("no selection interface")
        if not hasattr(self,"selection"):self.selection=Selection(self)
        return self.selection


class TablePattern:
    def __init__(self,headers,rows):self.headers=headers;self.rows=rows
    def getNRows(self):return len(self.rows)
    def getNColumns(self):return len(self.headers)
    def getColumnHeader(self,index):return self.headers[index]
    def getAccessibleAt(self,row,column):return self.rows[row][column]


class TableAccessible(Accessible):
    def __init__(self,name,headers,rows,attrs=None):
        super().__init__(name,"table",attrs=attrs)
        self.table=TablePattern(headers,rows)
    def queryTable(self):return self.table


def fixture(monkeypatch):
    entry=Accessible("Organisation","text",attrs={"id":"org-name"},states=(1,2,3),text="Old",editable=True)
    button=Accessible("Save","push button",attrs={"id":"save"})
    protected=Accessible("Password","text",attrs={"id":"password"},states=(1,2,3,4),text="secret",editable=True)
    label=Accessible("Status","text",attrs={"id":"status"},text="Ready")
    window=Accessible("Procurement","frame",children=[entry,button,protected,label])
    desktop=Accessible("","desktop",children=[window])
    api=SimpleNamespace(Registry=SimpleNamespace(getDesktop=lambda index:desktop),STATE_VISIBLE=1,
                        STATE_SHOWING=2,STATE_ENABLED=3,STATE_PROTECTED=4,STATE_CHECKED=5,STATE_FOCUSED=6)
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


class RangeValue:
    def __init__(self,value=5.0,minimum=0.0,maximum=10.0,accepted=True):
        self.current=value;self.minimum=minimum;self.maximum=maximum;self.accepted=accepted
    def getMinimumValue(self):return self.minimum
    def getMaximumValue(self):return self.maximum
    def getCurrentValue(self):return self.current
    def setCurrentValue(self,value):
        if self.accepted:self.current=value
        return self.accepted


def test_atspi_range_value_uses_native_interface_checks_bounds_and_verifies(monkeypatch):
    window,*_=fixture(monkeypatch)
    api=sys.modules["pyatspi"];api.STATE_READ_ONLY=7
    slider=Accessible("Zoom","slider",attrs={"id":"zoom"})
    slider.value_interface=RangeValue()
    slider.parent=window;window.children.append(slider)
    controls=linux_atspi.list_controls("Procurement",42)
    zoom=next(item for item in controls if item["automationId"]=="zoom")
    assert "set_range_value" in zoom["actions"]
    linux_atspi.set_range_value("Procurement","Zoom","zoom","Slider",7.25,42)
    assert slider.value_interface.current==7.25
    with pytest.raises(linux_atspi.ATSPIError,match="outside the control range"):
        linux_atspi.set_range_value("Procurement","Zoom","zoom","Slider",11,42)
    assert slider.value_interface.current==7.25
    slider.value_interface.accepted=False
    with pytest.raises(linux_atspi.ATSPIError,match="rejected"):
        linux_atspi.set_range_value("Procurement","Zoom","zoom","Slider",6,42)
    slider.states.values.add(api.STATE_READ_ONLY)
    with pytest.raises(linux_atspi.ATSPIError,match="read-only"):
        linux_atspi.set_range_value("Procurement","Zoom","zoom","Slider",6,42)


def test_atspi_spin_button_is_supported_and_snake_case_gi_methods_work(monkeypatch):
    window,*_=fixture(monkeypatch)
    spin=Accessible("Copies","spin button",attrs={"id":"copies"},states=(1,2,3))
    spin.value_interface=SimpleNamespace(get_minimum_value=lambda:1,get_maximum_value=lambda:20,
        get_current_value=lambda:3,set_current_value=lambda value:setattr(spin.value_interface,"current",value) or True)
    spin.value_interface.current=3
    # GI-style current-value methods commonly expose the updated value through a property.
    spin.value_interface.get_current_value=lambda:spin.value_interface.current
    spin.parent=window;window.children.append(spin)
    assert "set_range_value" in next(item for item in linux_atspi.list_controls("Procurement",42) if item["automationId"]=="copies")["actions"]
    linux_atspi.set_range_value("Procurement","Copies","copies","Spin Button",8,42)
    assert spin.value_interface.current==8


def test_linux_engine_executes_range_value_activity_through_atspi_adapter(monkeypatch,tmp_path):
    window,*_=fixture(monkeypatch)
    spin=Accessible("Copies","spin button",attrs={"id":"copies"},states=(1,2,3))
    spin.value_interface=RangeValue(value=2,minimum=0,maximum=10)
    spin.parent=window;window.children.append(spin)
    monkeypatch.setattr(linux_atspi.sys,"platform","linux")
    project={"format":"openrpa.project","formatVersion":1,"name":"AT-SPI range","main":"Main","workflows":{"Main":"main.json"}}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"AT-SPI range","variables":[],"arguments":[],"activities":[
        {"id":"set-copies","type":"desktop_ui_set_range_value","windowTitle":"Procurement","processId":42,"name":"Copies","automationId":"copies","controlType":"Spin Button","value":6}]}
    (tmp_path/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    result=run_project(project,tmp_path,options=RunOptions(allow_desktop=True))
    assert result.status=="succeeded",result.error
    assert spin.value_interface.current==6


def test_actions_and_text_use_atspi_interfaces(monkeypatch):
    _,entry,button,_,label=fixture(monkeypatch)
    linux_atspi.fill("Procurement","Organisation","org-name","Entry","North")
    linux_atspi.click("Procurement","Save","save","Push Button")
    assert entry.text=="North" and button.activated
    assert linux_atspi.read_text("Procurement","Status","status","Text")=="Ready"
    assert linux_atspi.control_state("Procurement","Save","save","Push Button")=={"exists":True,"visible":True,"enabled":False}


def test_atspi_grid_read_returns_bounded_rows_and_redacts_protected_cells(monkeypatch):
    headers=[Accessible("Order ID","table column header"),Accessible("Order ID","table column header")]
    rows=[[Accessible("O-1","table cell",text=" O-1 "),Accessible("secret","password text",text="secret",states=(1,2,3,4))],
          [Accessible("O-2","table cell",text="O-2"),Accessible("Ready","table cell",text="Ready")],
          [Accessible("O-3","table cell",text="O-3"),Accessible("Later","table cell",text="Later")]]
    table=TableAccessible("Orders",headers,rows,attrs={"id":"orders"})
    window=Accessible("Procurement","frame",children=[table]);desktop=Accessible("","desktop",children=[window])
    api=SimpleNamespace(Registry=SimpleNamespace(getDesktop=lambda index:desktop),STATE_VISIBLE=1,STATE_SHOWING=2,STATE_ENABLED=3,STATE_PROTECTED=4)
    monkeypatch.setattr(linux_atspi.sys,"platform","linux");monkeypatch.setitem(sys.modules,"pyatspi",api)
    records,metadata=linux_atspi.read_grid("Procurement","Orders","orders","Table",max_rows=2,max_columns=2,process_id=42)
    assert records==[{"Order ID":"O-1","Order ID_2":""},{"Order ID":"O-2","Order ID_2":"Ready"}]
    assert metadata["truncated"] is True and metadata["redactedCells"]==1
    assert "secret" not in str((records,metadata))
    inspected=linux_atspi.list_controls("Procurement",42)
    assert next(row for row in inspected if row["automationId"]=="orders")["actions"]==["read_grid","wait"]


def test_press_focuses_exact_atspi_control_and_blocks_password(monkeypatch):
    _,entry,_,protected,_=fixture(monkeypatch)
    activated=[];sent=[]
    monkeypatch.setattr(linux_atspi,"activate_window",lambda title,pid:activated.append((title,pid)))
    monkeypatch.setattr("openrpa.desktop_keys.send_key",lambda key:sent.append(key))
    linux_atspi.press("Procurement","Organisation","org-name","Entry","Ctrl+S",42)
    assert entry.focused and activated==[("Procurement",42)] and sent==["Ctrl+S"]
    with pytest.raises(linux_atspi.ATSPIError,match="password"):
        linux_atspi.press("Procurement","Password","password","Text","Enter",42)


def test_check_and_select_use_accessible_state_and_selection_interfaces(monkeypatch):
    option=Accessible("Finance","list item")
    combo=Accessible("Department","combo box",children=[Accessible("Human Resources","list item"),option],attrs={"id":"department"})
    checkbox=Accessible("Accept terms","check box",attrs={"id":"terms"})
    window=Accessible("Procurement","frame",children=[combo,checkbox]);desktop=Accessible("","desktop",children=[window])
    api=SimpleNamespace(Registry=SimpleNamespace(getDesktop=lambda index:desktop),STATE_VISIBLE=1,STATE_SHOWING=2,STATE_ENABLED=3,STATE_PROTECTED=4,STATE_CHECKED=5)
    monkeypatch.setattr(linux_atspi.sys,"platform","linux");monkeypatch.setitem(sys.modules,"pyatspi",api)
    assert linux_atspi.control_state("Procurement","Accept terms","terms","Check Box")["checked"] is False
    linux_atspi.set_checked("Procurement","Accept terms","terms","Check Box",True)
    assert linux_atspi.control_state("Procurement","Accept terms","terms","Check Box")["checked"] is True
    linux_atspi.set_checked("Procurement","Accept terms","terms","Check Box",True)
    linux_atspi.select("Procurement","Department","department","Combo Box","Finance")
    assert combo.selection.index==1
    rows=linux_atspi.list_controls("Procurement",42)
    actions={row["name"]:row["actions"] for row in rows}
    assert actions["Department"]==["select","wait"]
    assert actions["Accept terms"]==["check","uncheck","wait"]


def test_tree_item_expand_collapse_selection_and_capability_inspection(monkeypatch):
    item=Accessible("Reports","tree item",attrs={"id":"reports"},states=(1,2))
    tree=Accessible("Navigation","tree",children=[item],attrs={"id":"navigation"})
    window=Accessible("Finance","frame",children=[tree])
    desktop=Accessible("","desktop",children=[window])
    api=SimpleNamespace(Registry=SimpleNamespace(getDesktop=lambda index:desktop),STATE_VISIBLE=1,STATE_SHOWING=2,STATE_ENABLED=3,STATE_PROTECTED=4,STATE_EXPANDED=6)
    monkeypatch.setattr(linux_atspi.sys,"platform","linux");monkeypatch.setitem(sys.modules,"pyatspi",api)
    rows=linux_atspi.list_controls("Finance",42)
    report=next(row for row in rows if row["name"]=="Reports")
    assert "expand" in report["actions"] and "collapse" not in report["actions"]
    linux_atspi.set_expanded("Finance","Reports","reports","Tree Item",True,42)
    assert linux_atspi.control_state("Finance","Reports","reports","Tree Item",42)["expanded"] is True
    linux_atspi.set_expanded("Finance","Reports","reports","Tree Item",True,42)
    report=next(row for row in linux_atspi.list_controls("Finance",42) if row["name"]=="Reports")
    assert "collapse" in report["actions"] and "expand" not in report["actions"]
    linux_atspi.select("Finance","Reports","reports","Tree Item","Reports",42)
    assert tree.selection.index==0
    linux_atspi.set_expanded("Finance","Reports","reports","Tree Item",False,42)
    assert linux_atspi.control_state("Finance","Reports","reports","Tree Item",42)["expanded"] is False


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
