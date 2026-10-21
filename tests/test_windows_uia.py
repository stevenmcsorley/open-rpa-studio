from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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
    def __init__(self, name="Save", auto_id="save", control_type="Button", *, password=False, process_id=73):
        self.element_info=Info(name=name,auto_id=auto_id,control_type=control_type,is_password=password,process_id=process_id)
        self.calls=[]
        self.selected=None
    def is_enabled(self): return True
    def is_visible(self): return True
    def click_input(self): self.calls.append(("click",))
    def set_focus(self): self.calls.append(("focus",))
    def has_keyboard_focus(self): return True
    def invoke(self): self.calls.append(("invoke",))
    def set_edit_text(self,value): self.calls.append(("fill",value))
    def get_value(self): return "live-value"
    def window_text(self): return "live-value"
    def select(self,value=None,exact=True): self.calls.append(("select",value,exact));self.selected=value
    def selected_text(self):return self.selected or ""
    def rectangle(self):
        left=10 if self.element_info.automation_id=="source" else 110
        return SimpleNamespace(left=left,top=20,right=left+40,bottom=60)


class RangeControl(Control):
    def __init__(self, value=5.0, minimum=0.0, maximum=10.0, read_only=False):
        super().__init__("Zoom", "zoom", "Slider")
        self.iface_range_value=SimpleNamespace(CurrentMinimum=minimum,CurrentMaximum=maximum,
            CurrentIsReadOnly=read_only,CurrentValue=value,SetValue=self.set_value)
    def set_value(self,value):
        self.calls.append(("set_range_value",value));self.iface_range_value.CurrentValue=value


class ToggleControl(Control):
    def __init__(self,name="Enabled",auto_id="enabled",control_type="CheckBox",checked=False):
        super().__init__(name,auto_id,control_type);self.checked=checked
    def get_toggle_state(self):return int(self.checked)
    def toggle(self):self.checked=not self.checked;self.calls.append(("toggle",))


class TreeControl(Control):
    def __init__(self,name="Documents",auto_id="tree-documents",state=0):
        super().__init__(name,auto_id,"TreeItem");self.state=state;self.selected=False
    def get_expand_state(self):return self.state
    def window_text(self):return self.element_info.name
    def expand(self):self.state=1;self.calls.append(("expand",))
    def collapse(self):self.state=0;self.calls.append(("collapse",))
    def is_selected(self):return self.selected
    def select(self):self.selected=True;self.calls.append(("select",))


class ListOption(Control):
    def __init__(self,name,selected=False):
        super().__init__(name,name,"ListItem");self.selected=selected
        self.iface_selection_item=SimpleNamespace(AddToSelection=self.add_to_selection,RemoveFromSelection=self.remove_from_selection)
    def window_text(self):return self.element_info.name
    def select(self):self.selected=True;self.calls.append(("select",))
    def is_selected(self):return self.selected
    def add_to_selection(self):self.selected=True;self.calls.append(("add",))
    def remove_from_selection(self):self.selected=False;self.calls.append(("remove",))


class ListControl(Control):
    def __init__(self,options,name="Queue",auto_id="queue"):
        super().__init__(name,auto_id,"List");self.options=options;self.iface_selection=SimpleNamespace(CurrentCanSelectMultiple=True)
    def descendants(self,**criteria):
        result=self.options
        if criteria.get("control_type"):result=[item for item in result if item.element_info.control_type==criteria["control_type"]]
        return result


class GridCell(Control):
    def __init__(self,value,password=False):
        super().__init__("","","Text",password=password);self.value=value
    def get_value(self):return self.value


class GridControl(Control):
    def __init__(self,rows,headers):
        super().__init__("Orders","orders","DataGrid")
        self.iface_grid=SimpleNamespace(CurrentRowCount=len(rows),CurrentColumnCount=len(headers))
        self.iface_table=SimpleNamespace(GetCurrentColumnHeaders=lambda:[SimpleNamespace(CurrentName=value) for value in headers])
        self._rows=rows
    def cell(self,row,column):return self._rows[row][column]


class TableRow:
    def __init__(self,name,cells):self.element_info=SimpleNamespace(name=name,control_type="Custom");self._cells=cells
    def children(self,content_only=True):return self._cells


class HeaderCell(Control):
    def window_text(self):return self.element_info.name


class TableControl(Control):
    def __init__(self,headers,rows):
        super().__init__("Orders","orders","Table");self.is_table=True
        header_cells=[HeaderCell("Top Left Header Cell","","Header"),*[HeaderCell(value,"","Header") for value in headers]]
        self._children=[TableRow("Top Row",header_cells),*[TableRow(f"Row {index}",[HeaderCell(f"Row Header {index}","","Header"),*row]) for index,row in enumerate(rows)]]
    def children(self,content_only=True):return self._children


class Window:
    def __init__(self,title="Research Editor",process_id=73,controls=None):
        self.title=title
        self.element_info=Info(process_id=process_id,control_type="Window")
        self.element_info.process_id=process_id
        self._controls=controls or []
        self.calls=[]
    def window_text(self): return self.title
    def descendants(self,**criteria):
        result=self._controls
        if "title" in criteria: result=[item for item in result if item.element_info.name==criteria["title"]]
        if "auto_id" in criteria: result=[item for item in result if item.element_info.automation_id==criteria["auto_id"]]
        if "control_type" in criteria: result=[item for item in result if item.element_info.control_type==criteria["control_type"]]
        return result
    def set_focus(self):self.calls.append(("activate",))
    def minimize(self):self.calls.append(("minimize",))
    def restore(self):self.calls.append(("restore",))
    def close(self):self.calls.append(("close",))


class Desktop:
    def __init__(self,windows): self._windows=windows
    def windows(self,**_kwargs): return self._windows


def fake_find_controls(window,criteria):
    return window.descendants(**criteria)


@pytest.mark.parametrize("controls,point_control,expected", [
    ([Control()], Control(), True),
    ([Control(), Control()], Control(), False),
    ([Control(password=True)], Control(password=True), False),
    ([Control()], Control(process_id=99), False),
])
def test_desktop_click_hit_test_returns_only_unique_safe_ui_selectors(monkeypatch,controls,point_control,expected):
    window=Window(controls=controls)
    class PointDesktop:
        def from_point(self,x,y):
            assert (x,y)==(120,240)
            return point_control
    monkeypatch.setattr(windows_uia,"_window",lambda *_args:window)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:PointDesktop())
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    result=windows_uia.click_activity_at_point("Research Editor",73,120,240)
    assert (result is not None) is expected
    if result:
        assert result=={"type":"desktop_ui_click","windowTitle":"Research Editor","processId":73,
                        "name":"Save","automationId":"save","controlType":"Button","timeoutSeconds":10}
        assert "120" not in str(result) and "240" not in str(result)


def test_recorded_drag_resolution_requires_two_distinct_unique_controls(monkeypatch):
    source=Control("Source","source","ListItem")
    target=Control("Target","target","ListItem")
    window=Window(controls=[source,target])
    class PointDesktop:
        def windows(self,**_kwargs):return [window]
        def from_point(self,x,y):return source if x<200 else target
    monkeypatch.setattr(windows_uia,"_desktop",lambda:PointDesktop())
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    activity=windows_uia.drag_activity_between_points("Research Editor",73,20,20,240,40)
    assert activity["type"]=="desktop_ui_drag"
    assert activity["sourceAutomationId"]=="source" and activity["targetAutomationId"]=="target"
    assert not any(str(coord) in str(activity) for coord in (20,40,240))


def test_uia_uses_exact_window_and_unique_control_identity(monkeypatch):
    first=Window(controls=[Control()])
    similarly_named=Window("Research Editor — Copy",controls=[Control()])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([first,similarly_named]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    result=windows_uia._control("Research Editor","Save","save","Button",73)
    assert result is first._controls[0]
    assert windows_uia.list_windows()==[{"title":"Research Editor","processId":73,"controlType":"Window"},{"title":"Research Editor — Copy","processId":73,"controlType":"Window"}]


def test_uia_drag_uses_unique_accessible_bounds_and_releases_pointer(monkeypatch):
    source=Control("Source","source","ListItem")
    target=Control("Target","target","ListItem")
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[source,target])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    import pywinauto
    events=[]
    mouse=SimpleNamespace(press=lambda **kw:events.append(("press",kw)),move=lambda **kw:events.append(("move",kw)),release=lambda **kw:events.append(("release",kw)))
    monkeypatch.setattr(pywinauto,"mouse",mouse)
    monkeypatch.setattr(windows_uia.time,"sleep",lambda _seconds:None)
    windows_uia.drag("Research Editor","Source","source","ListItem","Target","target","ListItem",200,73)
    assert events[0]==("press",{"button":"left","coords":(30,40)})
    assert events[-1]==("release",{"button":"left","coords":(130,40)})
    assert all(event[0]!="move" or event[1]["coords"]!=(30,40) for event in events[1:-1])


def test_uia_grid_read_returns_bounded_records_unique_headers_and_redacts_password_cells(monkeypatch):
    grid=GridControl([[GridCell("  Alice  "),GridCell("secret",password=True)],[GridCell("Bob"),GridCell("ready")],[GridCell("Carol"),GridCell("later")]], ["Owner","Owner"])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[grid])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    rows,metadata=windows_uia.read_grid("Research Editor","Orders","orders","DataGrid",max_rows=2,max_columns=2,process_id=73)
    assert rows==[{"Owner":"Alice","Owner_2":""},{"Owner":"Bob","Owner_2":"ready"}]
    assert metadata=={"totalRows":3,"totalColumns":2,"rowsRead":2,"columnsRead":2,"truncated":True,"redactedCells":1,"outputChars":len(json.dumps(rows,ensure_ascii=False,separators=(",",":")))}
    assert "secret" not in json.dumps(rows) and "secret" not in json.dumps(metadata)


def test_uia_table_read_uses_accessible_header_and_value_patterns(monkeypatch):
    table=TableControl(["Order ID","Status"],[[GridCell("ORD-100"),GridCell("Ready")],[GridCell("ORD-101"),GridCell("Queued")]])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[table])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    rows,metadata=windows_uia.read_grid("Research Editor","Orders","orders","Table",process_id=73)
    assert rows==[{"Order ID":"ORD-100","Status":"Ready"},{"Order ID":"ORD-101","Status":"Queued"}]
    assert metadata["totalRows"]==2 and metadata["columnsRead"]==2


def test_uia_select_supports_exact_options_from_a_list_container(monkeypatch):
    options=[ListOption("Ready"),ListOption("In Progress"),ListOption("Blocked")]
    control=ListControl(options)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[control])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    windows_uia.select("Research Editor","Queue","queue","List","In Progress",73)
    assert [item.selected for item in options]==[False,True,False]
    assert options[1].calls==[("select",)]


@pytest.mark.parametrize("mode,values,initial,expected",[
    ("replace",["Queued","Blocked"],["Ready"],["Queued","Blocked"]),
    ("add",["Queued"],["Ready"],["Ready","Queued"]),
    ("remove",["Ready"],["Ready","Queued"],["Queued"]),
    ("replace",[],["Ready"],[]),
])
def test_uia_set_selection_replaces_adds_and_removes_exact_list_options(monkeypatch,mode,values,initial,expected):
    options=[ListOption(name,name in initial) for name in ("Ready","Queued","Blocked")]
    control=ListControl(options)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[control])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    selected=windows_uia.set_selection("Research Editor","Queue","queue","List",values,mode,73)
    assert set(selected)==set(expected)
    assert {item.element_info.name for item in options if item.selected}==set(expected)


def test_uia_set_selection_rejects_duplicate_or_missing_names_and_single_select_add(monkeypatch):
    options=[ListOption("Ready",True),ListOption("Queued"),ListOption("Queued")]
    control=ListControl(options)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[control])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    with pytest.raises(windows_uia.UIAutomationError,match="ambiguous"):
        windows_uia.set_selection("Research Editor","Queue","queue","List",["Queued"],"replace",73)
    with pytest.raises(windows_uia.UIAutomationError,match="duplicate names"):
        windows_uia.set_selection("Research Editor","Queue","queue","List",["Ready","Ready"],"replace",73)
    control.options=[ListOption("Ready",True),ListOption("Queued")]
    control.iface_selection.CurrentCanSelectMultiple=False
    with pytest.raises(windows_uia.UIAutomationError,match="would replace"):
        windows_uia.set_selection("Research Editor","Queue","queue","List",["Queued"],"add",73)


@pytest.mark.parametrize("options,value,message",[
    ([ListOption("Ready")],"Missing","No List option"),
    ([ListOption("Ready"),ListOption("Ready")],"Ready","ambiguous"),
])
def test_uia_list_select_fails_closed_for_missing_or_ambiguous_options(monkeypatch,options,value,message):
    control=ListControl(options)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[control])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    with pytest.raises(windows_uia.UIAutomationError,match=message):
        windows_uia.select("Research Editor","Queue","queue","List",value,73)
    assert not any(item.selected for item in options)


def test_uia_control_state_reports_selected_list_items(monkeypatch):
    item=ListOption("Queued",selected=True)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[item])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    state=windows_uia.control_state("Research Editor","Queued","Queued","ListItem",73)
    assert state=={"exists":True,"visible":True,"enabled":True,"selected":True}


def test_uia_grid_read_fails_on_output_overflow_and_missing_grid_pattern(monkeypatch):
    grid=GridControl([[GridCell("x"*200)]],["Value"])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[grid])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    with pytest.raises(windows_uia.UIAutomationError,match="output limit"):
        windows_uia.read_grid("Research Editor","Orders","orders","DataGrid",max_output_chars=100)
    nongrid=Control("Other","other","Table")
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[nongrid])]))
    with pytest.raises(windows_uia.UIAutomationError,match="Grid or Table pattern"):
        windows_uia.read_grid("Research Editor","Other","other","Table")


def test_uia_inspector_advertises_grid_read_only_for_grid_pattern_controls(monkeypatch):
    grid=GridControl([[GridCell("O-1")]], ["Order ID"])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[grid])]))
    controls=windows_uia.list_controls("Research Editor",73)
    assert len(controls)==1 and "read_grid" in controls[0]["actions"]


def test_uia_inspector_advertises_range_setting_only_for_writable_range_controls(monkeypatch):
    writable=RangeControl()
    readonly=RangeControl(read_only=True);readonly.element_info.name="Read only";readonly.element_info.automation_id="read-only"
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[writable,readonly])]))
    controls=windows_uia.list_controls("Research Editor",73)
    actions={item["automationId"]:item["actions"] for item in controls}
    assert "set_range_value" in actions["zoom"]
    assert "set_range_value" not in actions["read-only"]


def test_uia_drag_releases_pointer_when_move_fails(monkeypatch):
    controls=[Control("Source","source","ListItem"),Control("Target","target","ListItem")]
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=controls)]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    import pywinauto
    events=[]
    def fail_move(**kwargs):
        events.append(("move",kwargs))
        raise RuntimeError("controlled move failure")
    monkeypatch.setattr(pywinauto,"mouse",SimpleNamespace(press=lambda **kw:events.append(("press",kw)),move=fail_move,release=lambda **kw:events.append(("release",kw))))
    with pytest.raises(windows_uia.UIAutomationError,match="drag failed"):
        windows_uia.drag("Research Editor","Source","source","ListItem","Target","target","ListItem",100,73)
    assert events[0][0]=="press" and events[-1]==("release",{"button":"left","coords":(30,40)})


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


def test_uia_window_lifecycle_uses_exact_title_or_process_identity(monkeypatch):
    window=Window(controls=[]);other=Window("Other",process_id=73);different_process=Window("Alt",process_id=74)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([window,other,different_process]))
    assert windows_uia.window_exists("Research Editor",73)
    assert windows_uia.window_exists(None,74)
    assert not windows_uia.window_exists("Missing",73)
    windows_uia.activate_window("Research Editor",73)
    windows_uia.minimize_window("Research Editor",73)
    windows_uia.restore_window("Research Editor",73)
    windows_uia.close_window("Research Editor",73)
    assert window.calls==[("activate",),("minimize",),("restore",),("close",)]
    with pytest.raises(windows_uia.UIAutomationError,match="matched 2 windows"):
        windows_uia.activate_window(None,73)


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
        windows_uia.fill("Research Editor","Password","password","Edit","must-not-write")
    assert password.calls==[]
    with pytest.raises(windows_uia.UIAutomationError,match="password"):
        windows_uia.read_text("Research Editor","Password","password","Edit")


def test_uia_press_focuses_exact_control_and_blocks_password(monkeypatch):
    edit=Control("Document","document","Edit")
    password=Control("Password","password","Edit",password=True)
    window=Window(controls=[edit,password])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([window]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    sent=[]
    monkeypatch.setattr("openrpa.desktop_keys.send_key",lambda key:sent.append(key))
    windows_uia.press("Research Editor","Document","document","Edit","Ctrl+S",73)
    assert window.calls==[("activate",)]
    assert edit.calls==[("focus",)]
    assert sent==["Ctrl+S"]
    with pytest.raises(windows_uia.UIAutomationError,match="password"):
        windows_uia.press("Research Editor","Password","password","Edit","Enter",73)


def test_recorded_key_resolves_only_one_named_non_password_focused_control(monkeypatch):
    edit=Control("Document","document","Edit")
    window=Window(controls=[edit])
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([window]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    assert windows_uia.key_activity_for_focused_control("Research Editor",73,"Ctrl+S")=={
        "type":"desktop_ui_press","windowTitle":"Research Editor","processId":73,
        "name":"Document","automationId":"document","controlType":"Edit","key":"Ctrl+S","timeoutSeconds":10}
    password=Control("Password","password","Edit",password=True)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[password])]))
    assert windows_uia.key_activity_for_focused_control("Research Editor",73,"Enter") is None


def test_uia_invoke_uses_native_pattern_and_rejects_non_invoke_controls(monkeypatch):
    button=Control("Save","save","Button");edit=Control("Name","name","Edit")
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[button,edit])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    windows_uia.invoke("Research Editor","Save","save","Button",73)
    assert button.calls==[("invoke",)]
    assert windows_uia.list_controls("Research Editor",73)[0]["actions"]==["invoke","click","wait"]
    with pytest.raises(windows_uia.UIAutomationError,match="requires a Button"):
        windows_uia.invoke("Research Editor","Name","name","Edit",73)


def test_uia_check_and_select_are_state_aware_and_exact(monkeypatch):
    checkbox=ToggleControl();combo=Control("Department","department","ComboBox")
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[checkbox,combo])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    windows_uia.set_checked("Research Editor","Enabled","enabled","CheckBox",True)
    windows_uia.set_checked("Research Editor","Enabled","enabled","CheckBox",True)
    windows_uia.set_checked("Research Editor","Enabled","enabled","CheckBox",False)
    windows_uia.select("Research Editor","Department","department","ComboBox","Finance")
    assert checkbox.checked is False and checkbox.calls==[("toggle",),("toggle",)]
    assert combo.calls==[("select","Finance",True)]


def test_uia_tree_items_support_verified_expand_collapse_select_and_wait_state(monkeypatch):
    from pywinauto.controls.uiawrapper import uia_defs
    tree=TreeControl(state=uia_defs.expand_state_collapsed)
    monkeypatch.setattr(windows_uia,"_desktop",lambda:Desktop([Window(controls=[tree])]))
    monkeypatch.setattr(windows_uia,"_find_controls",fake_find_controls)
    assert windows_uia.list_controls("Research Editor",73)[0]["actions"]==["select","wait","expand"]
    windows_uia.set_expanded("Research Editor","Documents","tree-documents","TreeItem",True,73)
    assert windows_uia.control_state("Research Editor","Documents","tree-documents","TreeItem",73)["expanded"] is True
    windows_uia.set_expanded("Research Editor","Documents","tree-documents","TreeItem",True,73)
    windows_uia.select("Research Editor","Documents","tree-documents","TreeItem","Documents",73)
    windows_uia.set_expanded("Research Editor","Documents","tree-documents","TreeItem",False,73)
    assert tree.calls==[("expand",),("select",),("collapse",)]
    tree.state=uia_defs.expand_state_leaf_node
    with pytest.raises(windows_uia.UIAutomationError,match="leaf"):
        windows_uia.set_expanded("Research Editor","Documents","tree-documents","TreeItem",True,73)


def test_uia_activity_schema_requires_bounded_exact_selector():
    base={"format":"openrpa.workflow","formatVersion":1,"name":"UIA","variables":[],"arguments":[],"activities":[]}
    good={**base,"activities":[{"id":"click","type":"desktop_ui_click","windowTitle":"Editor","automationId":"save","controlType":"Button","timeoutSeconds":10}]}
    assert validate_workflow(good)==[]
    linux_entry={**base,"activities":[{"id":"fill","type":"desktop_ui_fill","windowTitle":"Editor","automationId":"name","controlType":"Entry","value":"Ada"}]}
    assert validate_workflow(linux_entry)==[]
    select_option={**base,"activities":[{"id":"select","type":"desktop_ui_select","windowTitle":"Editor","automationId":"team","controlType":"Combo Box","value":"Finance"}]}
    list_option={**base,"activities":[{"id":"select-list","type":"desktop_ui_select","windowTitle":"Editor","automationId":"queue","controlType":"List","value":"Ready"}]}
    list_selection={**base,"activities":[{"id":"select-many","type":"desktop_ui_select_many","windowTitle":"Editor","automationId":"queue","controlType":"List","values":["Ready","Queued"],"mode":"replace","result":"selectedItems"}]}
    selected_wait={**base,"activities":[{"id":"wait-selected","type":"desktop_ui_wait","windowTitle":"Editor","automationId":"queue-item","controlType":"ListItem","state":"selected"}]}
    tree_select={**base,"activities":[{"id":"select-tree","type":"desktop_ui_select","windowTitle":"Editor","automationId":"folder","controlType":"Tree Item","value":"Documents"}]}
    check_box={**base,"activities":[{"id":"check","type":"desktop_ui_check","windowTitle":"Editor","automationId":"terms","controlType":"Check Box"}]}
    invoke={**base,"activities":[{"id":"invoke","type":"desktop_ui_invoke","windowTitle":"Editor","automationId":"save","controlType":"Button"}]}
    window_wait={**base,"activities":[{"id":"wait-window","type":"desktop_window_wait","processId":73,"state":"exists","timeoutSeconds":5}]}
    close_window={**base,"activities":[{"id":"close-window","type":"desktop_window_close","windowTitle":"Editor","processId":73,"confirmClose":True}]}
    assert validate_workflow(select_option)==[] and validate_workflow(list_option)==[] and validate_workflow(list_selection)==[] and validate_workflow(selected_wait)==[] and validate_workflow(tree_select)==[] and validate_workflow(check_box)==[]
    list_selection["activities"][0]["controlType"]="Button"
    assert "desktop-uia-select-many-type" in {problem["code"] for problem in validate_workflow(list_selection)}
    selected_wait["activities"][0]["controlType"]="Button"
    assert "desktop-uia-selected-state-type" in {problem["code"] for problem in validate_workflow(selected_wait)}
    assert validate_workflow(invoke)==[] and validate_workflow(window_wait)==[] and validate_workflow(close_window)==[]
    range_value={**base,"activities":[{"id":"range","type":"desktop_ui_set_range_value","windowTitle":"Editor","automationId":"zoom","controlType":"Slider","value":7.5,"timeoutSeconds":10}]}
    assert validate_workflow(range_value)==[]
    range_value["activities"][0]["value"]=float("nan")
    assert "desktop-uia-range-value" in {problem["code"] for problem in validate_workflow(range_value)}
    range_value["activities"][0].update(value=True,controlType="Button")
    assert {"desktop-uia-range-value","desktop-uia-range-type"} <= {problem["code"] for problem in validate_workflow(range_value)}
    tree_expand={**base,"activities":[{"id":"expand","type":"desktop_ui_expand","windowTitle":"Editor","automationId":"folder","controlType":"TreeItem"}]}
    tree_wait={**base,"activities":[{"id":"wait","type":"desktop_ui_wait","windowTitle":"Editor","automationId":"folder","controlType":"TreeItem","state":"expanded"}]}
    assert validate_workflow(tree_expand)==[] and validate_workflow(tree_wait)==[]
    drag={**base,"activities":[{"id":"drag","type":"desktop_ui_drag","windowTitle":"Editor","sourceAutomationId":"row-a","sourceControlType":"ListItem","targetAutomationId":"row-b","targetControlType":"ListItem","durationMilliseconds":500}]}
    assert validate_workflow(drag)==[]
    drag["activities"][0]["durationMilliseconds"]=99
    assert "desktop-uia-drag-duration" in {problem["code"] for problem in validate_workflow(drag)}
    grid_read={**base,"activities":[{"id":"grid","type":"desktop_ui_grid_read","windowTitle":"Editor","automationId":"orders","controlType":"DataGrid","result":"rows","metadataResult":"meta","maxRows":100,"maxColumns":30,"maxOutputChars":50000}]}
    assert validate_workflow(grid_read)==[]
    grid_read["activities"][0]["maxRows"]=501
    assert "desktop-uia-grid-limit" in {problem["code"] for problem in validate_workflow(grid_read)}
    tree_expand["activities"][0]["controlType"]="Button"
    assert "desktop-uia-tree-type" in {problem["code"] for problem in validate_workflow(tree_expand)}
    tree_wait["activities"][0]["controlType"]="Button"
    assert "desktop-uia-tree-state-type" in {problem["code"] for problem in validate_workflow(tree_wait)}
    close_window["activities"][0]["confirmClose"]=False
    assert "desktop-window-close-confirmation" in {problem["code"] for problem in validate_workflow(close_window)}
    invoke["activities"][0]["controlType"]="Edit"
    assert "desktop-uia-invoke-type" in {problem["code"] for problem in validate_workflow(invoke)}
    bad={**base,"activities":[{"id":"bad","type":"desktop_ui_fill","windowTitle":"","name":"","controlType":"Button","value":1,"timeoutSeconds":121}]}
    codes={problem["code"] for problem in validate_workflow(bad)}
    assert {"desktop-uia-window","desktop-uia-selector","desktop-uia-timeout","desktop-uia-fill"}<=codes


def test_uia_range_value_sets_native_pattern_and_rejects_unsafe_values(monkeypatch):
    slider=RangeControl()
    monkeypatch.setattr(windows_uia,"_control",lambda *_args:slider)
    windows_uia.set_range_value("Editor","Zoom","zoom","Slider",7.5,73)
    assert slider.calls==[("set_range_value",7.5)]
    with pytest.raises(windows_uia.UIAutomationError,match="outside the control range"):
        windows_uia.set_range_value("Editor","Zoom","zoom","Slider",11,73)
    assert len(slider.calls)==1
    slider.iface_range_value.CurrentIsReadOnly=True
    with pytest.raises(windows_uia.UIAutomationError,match="read-only"):
        windows_uia.set_range_value("Editor","Zoom","zoom","Slider",6,73)
    with pytest.raises(windows_uia.UIAutomationError,match="finite number"):
        windows_uia.set_range_value("Editor","Zoom","zoom","Slider",float("inf"),73)


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
    ({"id":"invoke","type":"desktop_ui_invoke","windowTitle":"Editor","name":"Save","controlType":"Button"},("invoke",)),
    ({"id":"drag","type":"desktop_ui_drag","windowTitle":"Editor","sourceAutomationId":"row-a","sourceControlType":"ListItem","targetAutomationId":"row-b","targetControlType":"ListItem","durationMilliseconds":500},("drag",)),
    ({"id":"grid-read","type":"desktop_ui_grid_read","windowTitle":"Editor","automationId":"orders","controlType":"DataGrid","result":"records","metadataResult":"gridMetadata","maxRows":100,"maxColumns":30,"maxOutputChars":50000},("grid_read",)),
    ({"id":"range","type":"desktop_ui_set_range_value","windowTitle":"Editor","automationId":"zoom","controlType":"Slider","value":7.5},("set_range_value",7.5)),
    ({"id":"wait-window","type":"desktop_window_wait","windowTitle":"Editor","processId":73,"state":"exists","timeoutSeconds":1},("window_exists","Editor",73)),
    ({"id":"activate-window","type":"desktop_window_activate","windowTitle":"Editor","processId":73},("activate_window","Editor",73)),
    ({"id":"minimize-window","type":"desktop_window_minimize","windowTitle":"Editor","processId":73},("minimize_window","Editor",73)),
    ({"id":"restore-window","type":"desktop_window_restore","windowTitle":"Editor","processId":73},("restore_window","Editor",73)),
    ({"id":"close-window","type":"desktop_window_close","windowTitle":"Editor","processId":73,"confirmClose":True,"timeoutSeconds":1},("close_window","Editor",73)),
    ({"id":"fill","type":"desktop_ui_fill","windowTitle":"Editor","automationId":"name","controlType":"Edit","value":"Ada"},("fill","Ada")),
    ({"id":"press","type":"desktop_ui_press","windowTitle":"Editor","automationId":"name","controlType":"Edit","key":"Enter"},("press","Enter")),
    ({"id":"text","type":"desktop_ui_text","windowTitle":"Editor","automationId":"status","controlType":"Text","result":"status"},None),
    ({"id":"select","type":"desktop_ui_select","windowTitle":"Editor","automationId":"team","controlType":"ComboBox","value":"Finance"},("select","Finance")),
    ({"id":"select-many","type":"desktop_ui_select_many","windowTitle":"Editor","automationId":"queue","controlType":"List","values":["Ready","Queued"],"mode":"replace","result":"selectedItems"},("select_many",["Ready","Queued"])),
    ({"id":"wait-selected","type":"desktop_ui_wait","windowTitle":"Editor","automationId":"queue-item","controlType":"ListItem","state":"selected","timeoutSeconds":1},None),
    ({"id":"check","type":"desktop_ui_check","windowTitle":"Editor","automationId":"terms","controlType":"CheckBox"},("checked",True)),
    ({"id":"uncheck","type":"desktop_ui_uncheck","windowTitle":"Editor","automationId":"terms","controlType":"CheckBox"},("checked",False)),
    ({"id":"expand","type":"desktop_ui_expand","windowTitle":"Editor","automationId":"folder","controlType":"TreeItem"},("expanded",True)),
    ({"id":"collapse","type":"desktop_ui_collapse","windowTitle":"Editor","automationId":"folder","controlType":"TreeItem"},("expanded",False)),
])
def test_uia_activities_execute_only_with_permission(monkeypatch,tmp_path,activity,expected_call):
    calls=[]
    window_open=[True]
    def fake_window_exists(*args):
        calls.append(("window_exists",*args));return window_open[0]
    def fake_close_window(*args):
        calls.append(("close_window",*args));window_open[0]=False
    monkeypatch.setattr(windows_uia,"status",lambda:{"available":True,"reason":None})
    monkeypatch.setattr(windows_uia,"control_state",lambda *_args:{"exists":True,"visible":True,"enabled":True,**({"expanded":activity["type"]=="desktop_ui_expand"} if activity["type"] in {"desktop_ui_expand","desktop_ui_collapse"} else {}),**({"selected":activity.get("state")=="selected"} if activity["type"]=="desktop_ui_wait" and activity.get("state") in {"selected","unselected"} else {})})
    monkeypatch.setattr(windows_uia,"click",lambda *_args:calls.append(("click",)))
    monkeypatch.setattr(windows_uia,"drag",lambda *_args:calls.append(("drag",)))
    monkeypatch.setattr(windows_uia,"read_grid",lambda *args,**_kwargs:(calls.append(("grid_read",)) or ([{"order":"O-1"}],{"rowsRead":1})))
    monkeypatch.setattr(windows_uia,"invoke",lambda *_args:calls.append(("invoke",)))
    monkeypatch.setattr(windows_uia,"window_exists",fake_window_exists)
    monkeypatch.setattr(windows_uia,"activate_window",lambda *args:calls.append(("activate_window",*args)))
    monkeypatch.setattr(windows_uia,"minimize_window",lambda *args:calls.append(("minimize_window",*args)))
    monkeypatch.setattr(windows_uia,"restore_window",lambda *args:calls.append(("restore_window",*args)))
    monkeypatch.setattr(windows_uia,"close_window",fake_close_window)
    monkeypatch.setattr(windows_uia,"fill",lambda *_args:calls.append(("fill",_args[4])))
    monkeypatch.setattr(windows_uia,"press",lambda *_args:calls.append(("press",_args[4])))
    monkeypatch.setattr(windows_uia,"read_text",lambda *_args:"ready")
    monkeypatch.setattr(windows_uia,"select",lambda *_args:calls.append(("select",_args[4])))
    monkeypatch.setattr(windows_uia,"set_selection",lambda *args:(calls.append(("select_many",args[4])) or list(args[4])))
    monkeypatch.setattr(windows_uia,"set_range_value",lambda *args:calls.append(("set_range_value",args[4])))
    monkeypatch.setattr(windows_uia,"set_checked",lambda *_args:calls.append(("checked",_args[4])))
    monkeypatch.setattr(windows_uia,"set_expanded",lambda *_args:calls.append(("expanded",_args[4])))
    project={"format":"openrpa.project","formatVersion":1,"name":"UIA","main":"Main","workflows":{"Main":"main.json"}}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"UIA","variables":[],"arguments":[],"activities":[activity]}
    (tmp_path/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    denied=run_project(project,tmp_path,options=RunOptions(allow_desktop=False))
    assert denied.status=="failed" and denied.error["code"]=="desktop-permission-denied"
    success=run_project(project,tmp_path,options=RunOptions(allow_desktop=True))
    assert success.status=="succeeded"
    if expected_call: assert expected_call in calls
    if activity["type"]=="desktop_ui_text": assert success.variables["status"]=="ready"
    if activity["type"]=="desktop_ui_select_many": assert success.variables["selectedItems"]==["Ready","Queued"]
