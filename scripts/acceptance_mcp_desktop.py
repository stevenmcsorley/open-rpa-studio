"""Exercise live MCP desktop actions against a disposable WinForms app."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

TITLE="OpenRPA Desktop MCP Acceptance"
LAUNCHED_TITLE="OpenRPA MCP Launched Acceptance"


def main() -> int:
    if sys.platform!="win32":
        print("This live desktop acceptance script requires Windows UI Automation.",file=sys.stderr)
        return 2
    old_data=os.environ.get("OPENRPA_DATA_DIR")
    old_active=os.environ.get("OPENRPA_ACTIVE_PROJECT_FILE")
    ui:subprocess.Popen[Any]|None=None
    server:Any=None
    launched_pid:int|None=None
    from openrpa import desktop_accessibility
    from openrpa.mcp_server import ProjectMCPServer
    try:
        with tempfile.TemporaryDirectory(prefix="openrpa-mcp-desktop-acceptance-") as temporary:
            root=Path(temporary)
            project_root=root/"project";workflow_dir=project_root/"workflows";workflow_dir.mkdir(parents=True)
            (project_root/"project.json").write_text(json.dumps({"format":"openrpa.project","formatVersion":1,"name":"Desktop MCP Acceptance","main":"Main","workflows":{"Main":"workflows/main.workflow.json"}}),encoding="utf-8")
            (workflow_dir/"main.workflow.json").write_text(json.dumps({"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[]}),encoding="utf-8")
            os.environ["OPENRPA_DATA_DIR"]=str(root/"application-data")
            os.environ["OPENRPA_ACTIVE_PROJECT_FILE"]=str(root/"no-active-project.json")
            ps_script=root/"qa-form.ps1"
            ps_script.write_text(r"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form=New-Object System.Windows.Forms.Form
$form.Text='OpenRPA Desktop MCP Acceptance';$form.Name='OpenRPA Desktop MCP Acceptance';$form.Width=580;$form.Height=340
$editor=New-Object System.Windows.Forms.TextBox
$editor.Name='qaEditor';$editor.AccessibleName='QA Editor';$editor.Text='initial';$editor.Location=New-Object System.Drawing.Point(20,20);$editor.Width=320
$password=New-Object System.Windows.Forms.TextBox
$password.Name='qaPassword';$password.AccessibleName='QA Password';$password.UseSystemPasswordChar=$true;$password.Location=New-Object System.Drawing.Point(20,60);$password.Width=320
$status=New-Object System.Windows.Forms.Label
$status.Name='qaStatus';$status.Text='Ready';$status.Location=New-Object System.Drawing.Point(20,160);$status.Width=440
$button=New-Object System.Windows.Forms.Button
$button.Name='qaApply';$button.AccessibleName='Apply';$button.Text='Apply';$button.Location=New-Object System.Drawing.Point(370,20)
$button.Add_Click({$status.Text='Applied: '+$editor.Text})
$grid=New-Object System.Windows.Forms.DataGridView
$grid.Name='qaGrid';$grid.AccessibleName='QA Orders';$grid.Location=New-Object System.Drawing.Point(20,195);$grid.Width=500;$grid.Height=70;$grid.AllowUserToAddRows=$false
$grid.ColumnCount=2;$grid.Columns[0].Name='Order ID';$grid.Columns[1].Name='Status'
[void]$grid.Rows.Add('ORD-100','Ready');[void]$grid.Rows.Add('ORD-101','Queued')
$queue=New-Object System.Windows.Forms.ListView
$queue.Name='qaQueue';$queue.AccessibleName='QA Queue';$queue.View=[System.Windows.Forms.View]::List;$queue.MultiSelect=$true;$queue.Location=New-Object System.Drawing.Point(20,270);$queue.Width=200;$queue.Height=55
[void]$queue.Items.Add('Ready');[void]$queue.Items.Add('Queued');[void]$queue.Items.Add('Blocked')
$duplicateA=New-Object System.Windows.Forms.Button;$duplicateA.Text='Duplicate';$duplicateA.Location=New-Object System.Drawing.Point(20,100)
$duplicateB=New-Object System.Windows.Forms.Button;$duplicateB.Text='Duplicate';$duplicateB.Location=New-Object System.Drawing.Point(130,100)
$form.Controls.AddRange(@($editor,$password,$status,$button,$grid,$queue,$duplicateA,$duplicateB))
[System.Windows.Forms.Application]::Run($form)
""",encoding="utf-8")
            executable=os.path.join(os.environ.get("SystemRoot",r"C:\Windows"),"System32","WindowsPowerShell","v1.0","powershell.exe")
            ui=subprocess.Popen([executable,"-NoProfile","-STA","-WindowStyle","Hidden","-ExecutionPolicy","Bypass","-File",str(ps_script)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+15
            while time.monotonic()<deadline and not desktop_accessibility.window_exists(TITLE):
                if ui.poll() is not None:raise RuntimeError(f"Test form exited early with code {ui.returncode}")
                time.sleep(0.1)
            if not desktop_accessibility.window_exists(TITLE):raise TimeoutError("The controlled WinForms window did not become accessible")

            server=ProjectMCPServer(str(project_root),allow_run=True,allow_desktop=True)
            def call(name:str,args:dict[str,Any]|None=None)->dict[str,Any]:
                response=server.handle({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args or {}}})
                result=response.get("result",{})
                if result.get("isError"):
                    return {"isError":True,"message":result.get("content",[{}])[0].get("text","")}
                return result.get("structuredContent",{})
            windows=call("openrpa_list_desktop_windows",{"limit":100})["windows"]
            target=next(item for item in windows if item.get("title")==TITLE)
            test_pid=int(target["processId"])
            controls=call("openrpa_list_desktop_controls",{"windowTitle":TITLE,"processId":test_pid,"limit":100})["controls"]
            names={item["name"] for item in controls}
            if not {"QA Editor","Apply","Ready"}<=names:raise AssertionError(f"Required accessible controls were missing: {sorted(names)}")
            if "QA Password" in names:raise AssertionError("Protected password control was exposed by desktop inspection")
            queue_control=next((item for item in controls if item.get("automationId")=="qaQueue" or item.get("name")=="QA Queue"),None)
            if queue_control is None or "select" not in queue_control.get("actions",[]) or "select_many" not in queue_control.get("actions",[]):raise AssertionError(f"The WinForms ListBox did not expose exact option selection: {queue_control}")
            grid_control=next((item for item in controls if item.get("automationId")=="qaGrid" or item.get("name")=="QA Orders"),None)
            if grid_control is None:raise AssertionError(f"The WinForms acceptance grid was missing from UIA inspection: {controls}")
            if "read_grid" not in grid_control.get("actions",[]):
                from openrpa.windows_uia import _control
                wrapper=_control(TITLE,grid_control["name"],grid_control["automationId"],grid_control["controlType"],test_pid)
                tree=[]
                for child in wrapper.children():
                    tree.append({"type":child.element_info.control_type,"name":child.element_info.name,"class":type(child).__name__,"children":[{"type":cell.element_info.control_type,"name":cell.element_info.name,"class":type(cell).__name__} for cell in child.children()]})
                raise AssertionError(f"The WinForms DataGridView accessibility pattern is not recognized: control={grid_control}, wrapper={type(wrapper).__name__}, children={tree}")
            identity={"windowTitle":TITLE,"processId":test_pid}
            call("openrpa_desktop_action",{"action":"activate_window",**identity})
            editor={**identity,"name":"QA Editor","automationId":"qaEditor","controlType":"Edit"}
            fill=call("openrpa_desktop_action",{"action":"fill",**editor,"value":"written through live MCP"})
            if fill!={"action":"fill","completed":True}:raise AssertionError(f"UIA fill failed: {fill}")
            click=call("openrpa_desktop_action",{"action":"invoke",**identity,"name":"Apply","automationId":"qaApply","controlType":"Button"})
            if click.get("completed") is not True:raise AssertionError(f"UIA Invoke failed: {click}")
            read=call("openrpa_desktop_action",{"action":"read_text",**identity,"automationId":"qaStatus","controlType":"Text"})
            if read.get("text")!="Applied: written through live MCP":raise AssertionError(f"UIA readback differed: {read}")
            grid=call("openrpa_desktop_action",{"action":"read_grid",**identity,"name":grid_control["name"],"automationId":grid_control["automationId"],"controlType":grid_control["controlType"],"maxRows":10,"maxColumns":5,"maxOutputChars":5000})
            if grid.get("isError") or grid.get("records")!=[{"Order ID":"ORD-100","Status":"Ready"},{"Order ID":"ORD-101","Status":"Queued"}]:
                from openrpa.windows_uia import _control
                wrapper=_control(TITLE,grid_control["name"],grid_control["automationId"],grid_control["controlType"],test_pid)
                detail=[]
                for row in wrapper.children(content_only=True):
                    if not str(getattr(row.element_info,"name","")).startswith("Row "):continue
                    for cell in row.children(content_only=True):
                        if str(cell.element_info.control_type)!="DataItem":continue
                        item={"name":cell.window_text()}
                        try:item["getValue"]=cell.get_value()
                        except Exception as exc:item["getValueError"]=str(exc)
                        try:item["valuePattern"]=cell.iface_value.CurrentValue
                        except Exception as exc:item["valueError"]=str(exc)
                        try:item["legacyValue"]=cell.iface_legacy_iaccessible.CurrentValue
                        except Exception as exc:item["legacyValueError"]=str(exc)
                        detail.append(item)
                raise AssertionError(f"UIA table-cell value evidence: records={grid}, cells={detail}")
            selected=call("openrpa_desktop_action",{"action":"select",**identity,"name":queue_control["name"],"automationId":queue_control["automationId"],"controlType":queue_control["controlType"],"value":"Queued"})
            if selected.get("isError") or selected.get("completed") is not True:raise AssertionError(f"Native UIA ListBox selection failed through MCP: {selected}")
            from openrpa.windows_uia import _control
            queue_wrapper=_control(TITLE,queue_control["name"],queue_control["automationId"],queue_control["controlType"],test_pid)
            selected_items=[item.window_text() for item in queue_wrapper.descendants(control_type="ListItem") if item.is_selected()]
            if selected_items!=["Queued"]:raise AssertionError(f"MCP ListBox selection did not persist to the requested item: {selected_items}")
            selected_wait=call("openrpa_desktop_action",{"action":"wait",**identity,"name":"Queued","controlType":"ListItem","state":"selected","timeoutSeconds":2})
            if selected_wait.get("isError") or selected_wait.get("matched") is not True or selected_wait.get("state",{}).get("selected") is not True:raise AssertionError(f"UIA selected-state wait did not confirm the selected item: {selected_wait}")
            replaced=call("openrpa_desktop_action",{"action":"select_many",**identity,"name":queue_control["name"],"automationId":queue_control["automationId"],"controlType":queue_control["controlType"],"values":["Queued","Blocked"],"mode":"replace"})
            if replaced.get("isError") or set(replaced.get("selected",[]))!={"Queued","Blocked"}:raise AssertionError(f"MCP could not replace the ListBox selection: {replaced}")
            added=call("openrpa_desktop_action",{"action":"select_many",**identity,"name":queue_control["name"],"automationId":queue_control["automationId"],"controlType":queue_control["controlType"],"values":["Ready"],"mode":"add"})
            if added.get("isError") or set(added.get("selected",[]))!={"Ready","Queued","Blocked"}:raise AssertionError(f"MCP could not add a ListBox selection: {added}")
            removed=call("openrpa_desktop_action",{"action":"select_many",**identity,"name":queue_control["name"],"automationId":queue_control["automationId"],"controlType":queue_control["controlType"],"values":["Queued"],"mode":"remove"})
            if removed.get("isError") or set(removed.get("selected",[]))!={"Ready","Blocked"}:raise AssertionError(f"MCP could not remove a ListBox selection: {removed}")
            waited=call("openrpa_desktop_action",{"action":"wait",**editor,"state":"enabled","timeoutSeconds":2})
            if waited.get("matched") is not True:raise AssertionError(f"UIA state wait failed: {waited}")
            password=call("openrpa_desktop_action",{"action":"fill",**identity,"name":"QA Password","automationId":"qaPassword","controlType":"Edit","value":"blocked-synthetic-value"})
            if not password.get("isError") or "password" not in password.get("message","").lower():raise AssertionError(f"Password fill was not refused: {password}")
            ambiguous=call("openrpa_desktop_action",{"action":"click",**identity,"name":"Duplicate","controlType":"Button"})
            if not ambiguous.get("isError") or "2 matches" not in ambiguous.get("message",""):raise AssertionError(f"Ambiguous control action did not fail closed: {ambiguous}")
            launched_script=root/"mcp-launched-form.ps1"
            launched_script.write_text(r"""
Add-Type -AssemblyName System.Windows.Forms
$form=New-Object System.Windows.Forms.Form
$form.Text='OpenRPA MCP Launched Acceptance';$form.Width=400;$form.Height=160
$text=New-Object System.Windows.Forms.Label;$text.Text='Launched through MCP';$text.Location=New-Object System.Drawing.Point(20,30);$text.Width=300
$form.Controls.Add($text)
[System.Windows.Forms.Application]::Run($form)
""",encoding="utf-8")
            executable=os.path.join(os.environ.get("SystemRoot",r"C:\Windows"),"System32","WindowsPowerShell","v1.0","powershell.exe")
            launched=call("openrpa_desktop_action",{"action":"launch_application","executable":executable,"arguments":["-NoProfile","-STA","-WindowStyle","Hidden","-ExecutionPolicy","Bypass","-File",str(launched_script)]})
            if launched.get("isError"):raise AssertionError(f"Desktop MCP application launch failed: {launched}")
            launched_pid=launched.get("processId")
            if not isinstance(launched_pid,int):raise AssertionError(f"Desktop MCP launch returned no process ID: {launched}")
            waited_window=call("openrpa_desktop_action",{"action":"wait_window","windowTitle":LAUNCHED_TITLE,"processId":launched_pid,"timeoutSeconds":10})
            if waited_window.get("isError") or not waited_window.get("matched"):raise AssertionError(f"MCP-launched window was not discoverable: {waited_window}")
            closed_window=call("openrpa_desktop_action",{"action":"close_window","windowTitle":LAUNCHED_TITLE,"processId":launched_pid,"confirmClose":True,"timeoutSeconds":5})
            if closed_window.get("isError") or not closed_window.get("closed"):raise AssertionError(f"MCP could not normally close its disposable test window: {closed_window}")
            audit=server._get_history().list_audit()
            encoded=str(audit)
            if any(value in encoded for value in ("written through live MCP","Applied:","ORD-100","ORD-101","blocked-synthetic-value","Queued","Blocked","Ready",TITLE,"QA Editor")):
                raise AssertionError("Desktop audit history retained a control label or value")
            if not any(row["action"]=="desktop.mcp.action" and row["details"].get("outcome")=="completed" for row in audit):raise AssertionError("Successful desktop actions were not audited")
            if not any(row["action"]=="desktop.mcp.action" and row["details"].get("outcome")=="failed" for row in audit):raise AssertionError("Failed desktop actions were not audited")
            print(json.dumps({"status":"passed","windowProcessId":target["processId"],"accessibleControls":len(controls),"fillInvokeReadback":read["text"],"gridRows":len(grid["records"]),"gridMetadata":grid["metadata"],"listSelection":selected_items,"selectedStateWait":selected_wait["state"],"multiSelection":{"replace":replaced["selected"],"add":added["selected"],"remove":removed["selected"]},"stateWait":"passed","applicationLaunch":"passed","launchedWindowWait":"passed","normalWindowClose":"passed","passwordFill":"blocked","ambiguousClick":"blocked","audit":"value-free"},ensure_ascii=False))
            desktop_accessibility.close_window(TITLE,test_pid)
            ui.wait(timeout=5);ui=None
    finally:
        if ui is not None and ui.poll() is None:
            try:desktop_accessibility.close_window(TITLE)
            except Exception:pass
            try:ui.wait(timeout=5)
            except subprocess.TimeoutExpired:ui.terminate();ui.wait(timeout=5)
        if launched_pid is not None:
            try:desktop_accessibility.close_window(LAUNCHED_TITLE,launched_pid)
            except Exception:pass
        if old_data is None:os.environ.pop("OPENRPA_DATA_DIR",None)
        else:os.environ["OPENRPA_DATA_DIR"]=old_data
        if old_active is None:os.environ.pop("OPENRPA_ACTIVE_PROJECT_FILE",None)
        else:os.environ["OPENRPA_ACTIVE_PROJECT_FILE"]=old_active
    return 0


if __name__=="__main__":
    raise SystemExit(main())
