import json
import os
import copy
import hashlib
import io
import subprocess
import sys
import threading
import time
from queue import Queue
from pathlib import Path
import pytest

from openrpa.mcp_server import ProjectMCPServer
from openrpa.active_project import publish_active_project


def make_project(root: Path, activities=None):
    (root / "workflows").mkdir(parents=True)
    (root / "project.json").write_text(json.dumps({
        "format": "openrpa.project", "formatVersion": 1, "name": "MCP fixture",
        "main": "Main", "workflows": {"Main": "workflows/main.workflow.json"},
    }), encoding="utf-8")
    (root / "workflows/main.workflow.json").write_text(json.dumps({
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Main",
        "variables": [], "arguments": [], "activities": activities or [
            {"id": "hello", "type": "log", "level": "info", "message": "hello"}
        ],
    }), encoding="utf-8")


def call(server, name, arguments=None):
    response = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}})
    return response["result"]


def test_tools_are_project_scoped_and_execution_is_opt_in(tmp_path):
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path))
    info = call(server, "openrpa_project_info")["structuredContent"]
    assert info["projectName"] == "MCP fixture"
    assert not info["projectRootExposed"]
    assert "openrpa_run_workflow" not in {item["name"] for item in server._tools()}
    assert "openrpa_update_workflow" not in {item["name"] for item in server._tools()}
    assert "openrpa_create_workflow" not in {item["name"] for item in server._tools()}
    assert "openrpa_stage_workflow_draft" not in {item["name"] for item in server._tools()}
    assert "openrpa_activity_catalog" in {item["name"] for item in server._tools()}
    assert call(server, "openrpa_validate_project")["structuredContent"]["valid"]
    assert call(server, "openrpa_read_workflow", {"name": "Main"})["structuredContent"]["workflow"]["name"] == "Main"
    denied = call(server, "openrpa_update_workflow", {"name": "Main"})
    assert denied["isError"] is True
    assert "--allow-edit" in denied["content"][0]["text"]


def test_persistent_browser_profile_is_reported_and_gated_as_desktop_access(tmp_path):
    make_project(tmp_path,[{"id":"launch","type":"browser_launch","profileName":"Work"}])
    server=ProjectMCPServer(str(tmp_path),allow_run=True,allow_network=True)
    plan=call(server,"openrpa_plan_workflow",{"name":"Main"})["structuredContent"]
    assert plan["requires"]["desktop"] is True
    catalog={item["type"]:item for item in call(server,"openrpa_activity_catalog")["structuredContent"]["activities"]}
    assert catalog["browser_launch"]["conditionalPermissions"]=={"profileName=non-empty":["desktop"]}
    denied=call(server,"openrpa_run_workflow",{"name":"Main"})
    assert denied["isError"] is True and "--allow-desktop" in denied["content"][0]["text"]


def test_desktop_inspection_tools_are_bounded_read_only_and_omit_control_values(tmp_path,monkeypatch):
    from openrpa import desktop_accessibility
    make_project(tmp_path)
    server=ProjectMCPServer(str(tmp_path))
    tools={item["name"]:item for item in server._tools()}
    assert {"openrpa_desktop_status","openrpa_list_desktop_windows","openrpa_list_desktop_controls"}<=tools.keys()
    assert all(tools[name]["annotations"]["readOnlyHint"] for name in ("openrpa_desktop_status","openrpa_list_desktop_windows","openrpa_list_desktop_controls"))
    monkeypatch.setattr(desktop_accessibility,"status",lambda:{"available":True,"adapter":"Test UIA","reason":None})
    monkeypatch.setattr(desktop_accessibility,"list_windows",lambda limit:[{"title":"Untitled - Notepad","processId":4321,"controlType":"Window"}])
    seen=[]
    monkeypatch.setattr(desktop_accessibility,"list_controls",lambda title,pid,limit:(seen.append((title,pid,limit)) or [{"name":"Text editor","automationId":"15","controlType":"Edit","matchCount":1,"actions":["wait","fill","text"]}]))
    windows=call(server,"openrpa_list_desktop_windows",{"limit":5})["structuredContent"]
    controls=call(server,"openrpa_list_desktop_controls",{"windowTitle":"Untitled - Notepad","processId":4321,"limit":12})["structuredContent"]
    assert windows=={"available":True,"adapter":"Test UIA","windows":[{"title":"Untitled - Notepad","processId":4321,"controlType":"Window"}]}
    assert controls["valuesIncluded"] is False and "value" not in controls["controls"][0]
    assert seen==[("Untitled - Notepad",4321,12)]
    assert call(server,"openrpa_list_desktop_controls",{"windowTitle":" "})["isError"] is True
    assert call(server,"openrpa_list_desktop_windows",{"limit":201})["isError"] is True


def test_desktop_inspection_reports_unavailable_adapter_without_attempting_control_reads(tmp_path,monkeypatch):
    from openrpa import desktop_accessibility
    make_project(tmp_path)
    server=ProjectMCPServer(str(tmp_path))
    monkeypatch.setattr(desktop_accessibility,"status",lambda:{"available":False,"adapter":"Windows UI Automation (UIA)","reason":"Desktop extra missing"})
    monkeypatch.setattr(desktop_accessibility,"list_windows",lambda *_:pytest.fail("unavailable UIA must not be queried"))
    windows=call(server,"openrpa_list_desktop_windows")["structuredContent"]
    assert windows=={"available":False,"adapter":"Windows UI Automation (UIA)","reason":"Desktop extra missing","windows":[]}


def test_live_browser_mcp_tools_require_all_startup_grants(tmp_path):
    make_project(tmp_path)
    partial=ProjectMCPServer(str(tmp_path),allow_run=True,allow_network=True)
    assert not any(item["name"].startswith("openrpa_browser_") for item in partial._tools())
    denied=call(partial,"openrpa_browser_open",{"url":"https://example.org"})
    assert denied["isError"] is True
    assert "--allow-desktop" in denied["content"][0]["text"]
    full=ProjectMCPServer(str(tmp_path),allow_run=True,allow_network=True,allow_desktop=True)
    private=call(full,"openrpa_browser_open",{"url":"http://127.0.0.1/private"})
    assert private["isError"] is True and "non-public" in private["content"][0]["text"]


def test_live_browser_mcp_tools_open_inspect_act_record_and_audit_without_secrets(tmp_path,monkeypatch):
    from openrpa import mcp_server
    make_project(tmp_path)
    monkeypatch.setattr(mcp_server,"_history_path",lambda _root:tmp_path/"browser-audit.sqlite3")
    class Inspector:
        def __init__(self):self.closed=False;self.actions=[];self.page=type("Page",(),{"title":lambda self:"Item","url":"https://public.example/item?session=private"})()
        def open(self,url,*_args):return {"url":"https://public.example/catalog?token=private#item","title":"Catalog","status":200}
        def navigate(self,url):return {"url":"https://public.example/next?session=private","title":"Next","status":200}
        def snapshot(self,max_chars):return {"url":"https://public.example/next?session=private","title":"Next","text":"Visible product list","controls":[{"selector":"button:Next"}],"contentWarning":"untrusted"}
        def screenshot(self):return b"\xff\xd8\xffsynthetic jpeg image bytes"
        def act(self,action,**kwargs):self.actions.append((action,kwargs));return {"action":action,"url":"https://public.example/item?session=private","title":"Item","selectorKind":kwargs["selector_kind"],**({"selectedCount":len(kwargs.get("values") or [])} if action=="select_many" else {})}
        def start_recording(self):return {"recording":True,"url":"https://public.example/item?session=private"}
        def stop_recording(self):return {"recording":False,"url":"https://public.example/item?session=private","events":[{"type":"browser_click","selector":"button:Next"}],"truncated":False}
        def close(self):self.closed=True
    inspector=Inspector()
    monkeypatch.setattr(mcp_server,"BrowserInspector",lambda:inspector)
    server=ProjectMCPServer(str(tmp_path),allow_run=True,allow_network=True,allow_desktop=True)
    tools={item["name"]:item for item in server._tools()}
    assert {"openrpa_browser_open","openrpa_browser_navigate","openrpa_browser_snapshot","openrpa_browser_screenshot","openrpa_browser_action","openrpa_browser_start_recording","openrpa_browser_stop_recording","openrpa_browser_close"}<=tools.keys()
    opened_result=call(server,"openrpa_browser_open",{"url":"https://public.example/catalog?token=private#item"})
    assert not opened_result.get("isError"),opened_result
    opened=opened_result["structuredContent"]
    assert opened["url"]=="https://public.example/catalog"
    assert "private" not in str(opened)
    snapshot=call(server,"openrpa_browser_snapshot")["structuredContent"]
    assert snapshot["text"]=="Visible product list" and "private" not in str(snapshot)
    screenshot=call(server,"openrpa_browser_screenshot")
    assert screenshot["structuredContent"]["captured"] is True and screenshot["content"][1]["type"]=="image"
    import base64
    assert base64.b64decode(screenshot["content"][1]["data"]).startswith(b"\xff\xd8\xff")
    call(server,"openrpa_browser_action",{"action":"fill","selectorKind":"label","selector":"Search","value":"SENSITIVE FORM VALUE"})
    selected=call(server,"openrpa_browser_action",{"action":"select_many","selectorKind":"role","selector":"listbox:Categories","values":["books","music"]})["structuredContent"]
    assert selected["selectedCount"]==2 and "books" not in str(selected)
    assert inspector.actions[-1][1]["values"]==["books","music"]
    call(server,"openrpa_browser_start_recording")
    recorded=call(server,"openrpa_browser_stop_recording")["structuredContent"]
    assert recorded["events"][0]["type"]=="browser_click"
    audit=server._get_history().list_audit()
    assert all("SENSITIVE FORM VALUE" not in str(row) and "private" not in str(row) and "synthetic jpeg" not in str(row) for row in audit)
    assert all("button:Next" not in str(row) for row in audit)
    assert any("selectorSha256" in row["details"] for row in audit)
    assert any(row["action"]=="browser.mcp.action" for row in audit)
    inspector.open=lambda url,*_args: (_ for _ in ()).throw(RuntimeError(f"Browser failed at {url}"))
    failed=call(server,"openrpa_browser_open",{"url":"https://public.example/path?token=secret"})
    assert failed["isError"] is True
    assert "secret" not in failed["content"][0]["text"] and "[URL]" in failed["content"][0]["text"]
    assert call(server,"openrpa_browser_close")["structuredContent"]=={"closed":True}
    assert inspector.closed


def test_live_desktop_mcp_action_is_permission_gated_and_audited_without_values(tmp_path,monkeypatch):
    from openrpa import desktop_accessibility,mcp_server
    make_project(tmp_path)
    monkeypatch.setattr(mcp_server,"_history_path",lambda _root:tmp_path/"desktop-audit.sqlite3")
    monkeypatch.setattr(desktop_accessibility,"status",lambda:{"available":True,"adapter":"Test UIA","reason":None})
    partial=ProjectMCPServer(str(tmp_path),allow_desktop=True)
    assert "openrpa_desktop_action" not in {tool["name"] for tool in partial._tools()}
    denied=call(partial,"openrpa_desktop_action",{"action":"click","windowTitle":"QA Window","automationId":"save"})
    assert denied["isError"] is True and "--allow-run" in denied["content"][0]["text"]
    calls=[];wait_calls=[0]
    monkeypatch.setattr(desktop_accessibility,"fill",lambda *args:calls.append(("fill",args[4])))
    monkeypatch.setattr(desktop_accessibility,"press",lambda *args:calls.append(("press",args[4])))
    monkeypatch.setattr(desktop_accessibility,"read_text",lambda *_args:"controlled QA text")
    monkeypatch.setattr(desktop_accessibility,"control_state",lambda *_args:(wait_calls.__setitem__(0,wait_calls[0]+1) or {"exists":True,"visible":True,"enabled":wait_calls[0]>1}))
    monkeypatch.setattr(desktop_accessibility,"click",lambda *_args:(_ for _ in ()).throw(RuntimeError("selector matched multiple controls")))
    drag_calls=[]
    monkeypatch.setattr(desktop_accessibility,"drag",lambda *args:drag_calls.append(args))
    range_calls=[]
    monkeypatch.setattr(desktop_accessibility,"set_range_value",lambda *args:range_calls.append(args))
    scroll_calls=[]
    monkeypatch.setattr(desktop_accessibility,"scroll_into_view",lambda *args:scroll_calls.append(args))
    monkeypatch.setattr(desktop_accessibility,"read_grid",lambda *_args,**_kwargs:([{"Name":"private cell value"}],{"totalRows":1,"totalColumns":1,"rowsRead":1,"columnsRead":1,"truncated":False,"redactedCells":0,"outputChars":28}))
    launched=[]
    class FakeChild:
        pid=991
        def wait(self):return 0
    monkeypatch.setattr(mcp_server.subprocess,"Popen",lambda command,**kwargs:(launched.append((command,kwargs)) or FakeChild()))
    monkeypatch.setattr(desktop_accessibility,"window_exists",lambda *_args:True)
    monkeypatch.setattr(desktop_accessibility,"list_windows",lambda *_args:[{"title":"QA Window","processId":991}])
    closed=[]
    monkeypatch.setattr(desktop_accessibility,"close_window",lambda *args:closed.append(args))
    server=ProjectMCPServer(str(tmp_path),allow_run=True,allow_desktop=True)
    tools={tool["name"]:tool for tool in server._tools()}
    assert "openrpa_desktop_action" in tools
    assert tools["openrpa_desktop_action"]["annotations"]["destructiveHint"] is True
    assert "drag" in tools["openrpa_desktop_action"]["inputSchema"]["properties"]["action"]["enum"]
    assert "read_grid" in tools["openrpa_desktop_action"]["inputSchema"]["properties"]["action"]["enum"]
    assert "set_range_value" in tools["openrpa_desktop_action"]["inputSchema"]["properties"]["action"]["enum"]
    assert "scroll_into_view" in tools["openrpa_desktop_action"]["inputSchema"]["properties"]["action"]["enum"]
    grid_result=call(server,"openrpa_desktop_action",{"action":"read_grid","windowTitle":"QA Window","processId":73,"automationId":"orders","controlType":"DataGrid","maxRows":5,"maxColumns":4,"maxOutputChars":5000})
    assert grid_result["structuredContent"]["records"]==[{"Name":"private cell value"}]
    drag_result=call(server,"openrpa_desktop_action",{"action":"drag","windowTitle":"QA Window","processId":73,"sourceAutomationId":"source","sourceControlType":"ListItem","targetAutomationId":"target","targetControlType":"ListItem","durationMilliseconds":250})
    assert drag_result.get("structuredContent")=={"action":"drag","completed":True},drag_result
    assert drag_calls==[("QA Window",None,"source","ListItem",None,"target","ListItem",250,73)]
    range_result=call(server,"openrpa_desktop_action",{"action":"set_range_value","windowTitle":"QA Window","processId":73,"automationId":"zoom","controlType":"Slider","numericValue":0.75})
    assert range_result["structuredContent"]=={"action":"set_range_value","completed":True}
    assert range_calls==[("QA Window",None,"zoom","Slider",0.75,73)]
    scrolled=call(server,"openrpa_desktop_action",{"action":"scroll_into_view","windowTitle":"QA Window","processId":73,"automationId":"archive","controlType":"TreeItem"})
    assert scrolled["structuredContent"]=={"action":"scroll_into_view","completed":True}
    assert scroll_calls==[("QA Window",None,"archive","TreeItem",73)]
    invalid_range=call(server,"openrpa_desktop_action",{"action":"set_range_value","windowTitle":"QA Window","automationId":"zoom","controlType":"Slider","numericValue":float("inf")})
    assert invalid_range["isError"] is True
    identity={"windowTitle":"QA Window","processId":73,"name":"Document","automationId":"editor","controlType":"Edit"}
    filled=call(server,"openrpa_desktop_action",{"action":"fill",**identity,"value":"PRIVATE DESKTOP VALUE"})
    assert filled["structuredContent"]=={"action":"fill","completed":True}
    assert calls==[("fill","PRIVATE DESKTOP VALUE")]
    pressed=call(server,"openrpa_desktop_action",{"action":"press",**identity,"key":"Ctrl+S"})
    assert pressed["structuredContent"]["completed"] is True
    read=call(server,"openrpa_desktop_action",{"action":"read_text",**identity})
    assert read["structuredContent"]["text"]=="controlled QA text"
    waited=call(server,"openrpa_desktop_action",{"action":"wait",**identity,"state":"enabled","timeoutSeconds":1})
    assert waited["structuredContent"]["matched"] is True and wait_calls[0]>=2
    launched_result=call(server,"openrpa_desktop_action",{"action":"launch_application","executable":sys.executable,"arguments":["-c","private argument"]})
    assert launched_result["structuredContent"]=={"action":"launch_application","launched":True,"processId":991}
    assert launched[0][0]==[str(Path(sys.executable).resolve()),"-c","private argument"]
    assert launched[0][1]["shell"] is False and launched[0][1]["stdin"] is subprocess.DEVNULL
    wait_window=call(server,"openrpa_desktop_action",{"action":"wait_window","windowTitle":"QA Window","processId":991,"timeoutSeconds":1})
    assert wait_window["structuredContent"]["windows"]==[{"title":"QA Window","processId":991}]
    refused_close=call(server,"openrpa_desktop_action",{"action":"close_window","windowTitle":"QA Window","processId":991})
    assert refused_close["isError"] is True and not closed
    monkeypatch.setattr(desktop_accessibility,"window_exists",lambda *_args:False)
    closed_result=call(server,"openrpa_desktop_action",{"action":"close_window","windowTitle":"QA Window","processId":991,"confirmClose":True})
    assert closed_result["structuredContent"]=={"action":"close_window","closed":True} and closed
    failed=call(server,"openrpa_desktop_action",{"action":"click",**identity})
    assert failed["isError"] is True
    audit=server._get_history().list_audit()
    encoded=str(audit)
    assert "PRIVATE DESKTOP VALUE" not in encoded and "controlled QA text" not in encoded and "private cell value" not in encoded and "private argument" not in encoded and "QA Window" not in encoded and "Document" not in encoded
    assert any(row["action"]=="desktop.mcp.action" and row["details"].get("outcome")=="completed" for row in audit)
    assert any(row["action"]=="desktop.mcp.action" and row["details"].get("outcome")=="failed" for row in audit)


def test_mcp_server_follows_the_project_open_in_studio_between_calls(tmp_path,monkeypatch):
    pointer=tmp_path/"app-data"/"active-project.json"
    monkeypatch.setenv("OPENRPA_ACTIVE_PROJECT_FILE",str(pointer))
    launch_project=tmp_path/"launch-project"
    studio_project=tmp_path/"studio-project"
    make_project(launch_project,[{"id":"launch","type":"log","level":"info","message":"launch project"}])
    make_project(studio_project,[{"id":"studio","type":"log","level":"info","message":"open Studio project"}])
    manifest=studio_project/"project.json"
    project=json.loads(manifest.read_text(encoding="utf-8"));project["name"]="Open Studio project"
    manifest.write_text(json.dumps(project),encoding="utf-8")

    server=ProjectMCPServer(str(launch_project),allow_edit=True)
    publish_active_project(studio_project)

    info=call(server,"openrpa_project_info")["structuredContent"]
    assert info["projectName"]=="Open Studio project"
    assert info["projectBinding"]=="studio-active"
    assert info["projectRootExposed"] is False
    read=call(server,"openrpa_read_workflow",{"name":"Main"})["structuredContent"]
    assert read["workflow"]["activities"][0]["message"]=="open Studio project"

    draft={"format":"openrpa.workflow","formatVersion":1,"name":"Live MCP edit","variables":[],"arguments":[],"activities":[{"id":"hello","type":"log","level":"info","message":"visible in active Studio"}]}
    staged=call(server,"openrpa_stage_workflow_draft",{"name":"Live MCP edit","workflow":draft})["structuredContent"]
    assert staged["staged"] is True
    assert (studio_project/".openrpa"/"mcp-live-draft.json").is_file()
    assert not (launch_project/".openrpa"/"mcp-live-draft.json").exists()

    # The same already-running MCP server tracks a later project switch in Studio.
    next_project=tmp_path/"next-project"
    make_project(next_project)
    manifest=next_project/"project.json"
    project=json.loads(manifest.read_text(encoding="utf-8"));project["name"]="Next Studio project"
    manifest.write_text(json.dumps(project),encoding="utf-8")
    publish_active_project(next_project)
    assert call(server,"openrpa_project_info")["structuredContent"]["projectName"]=="Next Studio project"


def test_mcp_stdio_escapes_unicode_for_legacy_windows_code_pages(tmp_path):
    make_project(tmp_path,[{"id":"hello","type":"log","level":"info","message":"price £528 · current"}])
    server=ProjectMCPServer(str(tmp_path))
    request={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"openrpa_read_workflow","arguments":{"name":"Main"}}}
    output=io.StringIO()
    assert server.serve(io.BytesIO((json.dumps(request)+"\n").encode()),output)==0
    line=output.getvalue().strip()
    assert "\\u00a3" in line and "\\u00b7" in line
    response=json.loads(line)
    assert response["result"]["structuredContent"]["workflow"]["activities"][0]["message"]=="price £528 · current"


def test_api_connections_are_discoverable_and_credentials_are_planned_and_gated(tmp_path,monkeypatch):
    from openrpa import api_connections
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    data=tmp_path/"app-data";data.mkdir()
    monkeypatch.setenv("OPENRPA_API_CONNECTIONS_FILE",str(data/"api-connections.json"))
    profile=api_connections.save_profile(data/"api-connections.json",{"name":"Inventory API","baseUrl":"https://inventory.example/v1","authType":"bearer"})
    make_project(tmp_path/"project",[{"id":"request","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/items"}])
    server=ProjectMCPServer(str(tmp_path/"project"),allow_run=True,allow_network=True,allow_credentials=False)
    names={tool["name"] for tool in server._tools()}
    assert "openrpa_list_api_connections" in names
    connections=call(server,"openrpa_list_api_connections")["structuredContent"]["connections"]
    assert connections==[{"id":profile["id"],"name":"Inventory API","baseUrl":"https://inventory.example/v1","authType":"bearer","credentialStored":False}]
    plan=call(server,"openrpa_plan_workflow",{"name":"Main"})["structuredContent"]
    assert plan["requires"]=={"network":True,"desktop":False,"credentials":True,"destructive":False}
    denied=call(server,"openrpa_run_workflow",{"name":"Main"})
    assert denied["isError"] is True and "--allow-credentials" in denied["content"][0]["text"]


def test_mcp_activity_catalog_is_native_and_labels_required_permissions(tmp_path):
    from openrpa.activity_catalog import ACTIVITY_CATALOG

    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path))
    result = call(server, "openrpa_activity_catalog")["structuredContent"]["activities"]
    assert [item["type"] for item in result] == [item["type"] for item in ACTIVITY_CATALOG]
    by_type = {item["type"]: item for item in result}
    assert by_type["browser_navigate"]["requiredPermissions"] == ["network"]
    assert by_type["http_paginate"]["requiredPermissions"] == ["network"]
    assert by_type["desktop_click"]["requiredPermissions"] == ["desktop"]
    assert by_type["credential_get"]["requiredPermissions"] == ["credentials"]
    assert by_type["file_delete"]["requiredPermissions"] == ["destructive"]


def test_browser_navigation_is_preflighted_as_network_access(tmp_path):
    make_project(tmp_path, [{"id": "navigate", "type": "browser_navigate", "url": "https://example.org"}])
    server = ProjectMCPServer(str(tmp_path), allow_run=True)
    plan = call(server, "openrpa_plan_workflow", {"name": "Main"})["structuredContent"]
    assert plan["requires"]["network"] is True
    result = call(server, "openrpa_run_workflow", {"name": "Main"})
    assert result["isError"] is True
    assert "browser navigation" in result["content"][0]["text"]
    assert "--allow-network" in result["content"][0]["text"]

def test_paginated_api_is_preflighted_as_network_access(tmp_path):
    make_project(tmp_path, [{"id":"api-read","type":"http_paginate","url":"https://api.example.org/items","itemsPath":"items","result":"items"}])
    server=ProjectMCPServer(str(tmp_path),allow_run=True)
    plan=call(server,"openrpa_plan_workflow",{"name":"Main"})["structuredContent"]
    assert plan["requires"]["network"] is True
    result=call(server,"openrpa_run_workflow",{"name":"Main"})
    assert result["isError"] is True
    assert "HTTP" in result["content"][0]["text"]
    assert "--allow-network" in result["content"][0]["text"]


def test_opt_in_edit_requires_current_digest_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_edit=True)
    initial = call(server, "openrpa_read_workflow", {"name": "Main"})["structuredContent"]
    proposed = copy.deepcopy(initial["workflow"])
    proposed["activities"][0]["message"] = "edited by a reviewed agent"
    update = call(server, "openrpa_update_workflow", {"name": "Main", "expectedSha256": initial["sha256"], "workflow": proposed})
    assert update["structuredContent"]["updated"] is True
    saved = call(server, "openrpa_read_workflow", {"name": "Main"})["structuredContent"]
    assert saved["workflow"]["activities"][0]["message"] == "edited by a reviewed agent"
    assert saved["sha256"] == update["structuredContent"]["sha256"]
    stale = call(server, "openrpa_update_workflow", {"name": "Main", "expectedSha256": initial["sha256"], "workflow": initial["workflow"]})
    assert stale["isError"] is True
    invalid = copy.deepcopy(saved["workflow"])
    invalid["activities"][0].pop("type")
    rejected = call(server, "openrpa_update_workflow", {"name": "Main", "expectedSha256": saved["sha256"], "workflow": invalid})
    assert rejected["structuredContent"]["updated"] is False
    assert "type" in json.dumps(rejected["structuredContent"]["problems"])
    assert call(server, "openrpa_read_workflow", {"name": "Main"})["structuredContent"]["sha256"] == saved["sha256"]


def test_live_workflow_draft_is_validated_preview_and_does_not_modify_project(tmp_path):
    make_project(tmp_path)
    server=ProjectMCPServer(str(tmp_path),allow_edit=True)
    names={tool["name"] for tool in server._tools()}
    assert "openrpa_stage_workflow_draft" in names and "openrpa_clear_workflow_draft" in names
    before=call(server,"openrpa_read_workflow",{"name":"Main"})["structuredContent"]["sha256"]
    draft={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"first","type":"log","level":"info","message":"step one"}]}
    staged_result=call(server,"openrpa_stage_workflow_draft",{"name":"Main","workflow":draft})
    assert "structuredContent" in staged_result,staged_result
    staged=staged_result["structuredContent"]
    assert staged["staged"] is True and staged["activityCount"]==1
    preview=json.loads((tmp_path/".openrpa"/"mcp-live-draft.json").read_text(encoding="utf-8"))
    assert preview["draftId"]==staged["draftId"] and preview["status"]=="building" and preview["workflow"]["activities"][0]["message"]=="step one"
    assert call(server,"openrpa_read_workflow",{"name":"Main"})["structuredContent"]["sha256"]==before
    draft["activities"].append({"id":"second","type":"log","level":"info","message":"step two"})
    next_stage=call(server,"openrpa_stage_workflow_draft",{"name":"Main","workflow":draft})["structuredContent"]
    assert next_stage["draftId"]!=staged["draftId"]
    stale_clear=call(server,"openrpa_clear_workflow_draft",{"draftId":staged["draftId"]})["structuredContent"]
    assert stale_clear["cleared"] is False and stale_clear["reason"]=="draft-changed"
    invalid=copy.deepcopy(draft);invalid["activities"].append({"id":"broken","type":"missing"})
    rejected=call(server,"openrpa_stage_workflow_draft",{"name":"Main","workflow":invalid})["structuredContent"]
    assert rejected["staged"] is False and rejected["problems"]
    assert len(json.loads((tmp_path/".openrpa"/"mcp-live-draft.json").read_text(encoding="utf-8"))["workflow"]["activities"])==2
    cleared=call(server,"openrpa_clear_workflow_draft",{"draftId":next_stage["draftId"]})["structuredContent"]
    assert cleared["cleared"] is True and not (tmp_path/".openrpa"/"mcp-live-draft.json").exists()


def test_create_workflow_is_project_hash_guarded_and_validates_bindings(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_edit=True)
    initial = call(server, "openrpa_project_info")["structuredContent"]
    workflow = {
        "format": "openrpa.workflow", "formatVersion": 1, "name": "ignored supplied name",
        "variables": [], "arguments": [], "activities": [
            {"id": "helper-log", "type": "log", "level": "info", "message": "shared helper"}
        ],
    }
    created = call(server, "openrpa_create_workflow", {
        "name": "Shared Helper", "expectedProjectSha256": initial["projectSha256"], "workflow": workflow,
    })["structuredContent"]
    assert created["created"] is True
    assert created["workflowPath"] == "workflows/shared-helper.workflow.json"
    assert created["projectSha256"] == hashlib.sha256((tmp_path / "project.json").read_bytes()).hexdigest()
    assert call(server, "openrpa_list_workflows")["structuredContent"]["workflows"][-1]["name"] == "Shared Helper"
    saved = call(server, "openrpa_read_workflow", {"name": "Shared Helper"})["structuredContent"]
    assert saved["workflow"]["name"] == "Shared Helper"
    assert saved["sha256"] == created["workflowSha256"]
    assert call(server, "openrpa_validate_project")["structuredContent"]["workflowCount"] == 2
    reopened = ProjectMCPServer(str(tmp_path))
    assert call(reopened, "openrpa_validate_project")["structuredContent"]["workflowCount"] == 2

    stale = call(server, "openrpa_create_workflow", {
        "name": "Second Helper", "expectedProjectSha256": initial["projectSha256"], "workflow": workflow,
    })
    assert stale["isError"] is True
    assert "Project changed since it was read" in stale["content"][0]["text"]
    assert call(server, "openrpa_list_workflows")["structuredContent"]["workflows"][-1]["name"] == "Shared Helper"


def test_create_workflow_rejects_unresolved_invocations_without_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_edit=True)
    project_hash = call(server, "openrpa_project_info")["structuredContent"]["projectSha256"]
    invalid = {
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Unresolved",
        "variables": [], "arguments": [], "activities": [
            {"id": "call-missing", "type": "invoke_workflow", "workflow": "Missing", "inputs": {}}
        ],
    }
    result = call(server, "openrpa_create_workflow", {
        "name": "Unresolved", "expectedProjectSha256": project_hash, "workflow": invalid,
    })["structuredContent"]
    assert result["created"] is False
    assert any(problem.get("code") == "workflow-ref" for problem in result["problems"])
    assert not (tmp_path / "workflows/unresolved.workflow.json").exists()
    assert call(server, "openrpa_validate_project")["structuredContent"]["workflowCount"] == 1


def test_create_workflow_rejects_path_separators(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_edit=True)
    project_hash = call(server, "openrpa_project_info")["structuredContent"]["projectSha256"]
    workflow = {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": []}
    result = call(server, "openrpa_create_workflow", {
        "name": "../escaped", "expectedProjectSha256": project_hash, "workflow": workflow,
    })
    assert result["isError"] is True
    assert "path separators" in result["content"][0]["text"]
    assert call(server, "openrpa_validate_project")["structuredContent"]["workflowCount"] == 1


def test_validate_workflow_draft_bundle_checks_cross_references_without_writing(tmp_path):
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path))
    manifest = (tmp_path / "project.json").read_bytes()
    drafts = {
        "Wrapper": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [
            {"id": "call-helper", "type": "invoke_workflow", "workflow": "Helper", "inputs": {}}
        ]},
        "Helper": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [
            {"id": "helper-log", "type": "log", "level": "info", "message": "draft only"}
        ]},
    }
    result = call(server, "openrpa_validate_workflow_drafts", {"workflows": drafts})["structuredContent"]
    assert result["valid"] is True
    assert result["workflowNames"] == ["Wrapper", "Helper"]
    assert result["problems"] == []
    assert (tmp_path / "project.json").read_bytes() == manifest
    assert not (tmp_path / "workflows/wrapper.workflow.json").exists()
    assert not (tmp_path / "workflows/helper.workflow.json").exists()

    invalid = {"Broken": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [
        {"id": "call-missing", "type": "invoke_workflow", "workflow": "Unknown", "inputs": {}}
    ]}}
    failed = call(server, "openrpa_validate_workflow_drafts", {"workflows": invalid})["structuredContent"]
    assert failed["valid"] is False
    assert any(item.get("workflow") == "Broken" and item.get("code") == "workflow-ref" for item in failed["problems"])
    assert (tmp_path / "project.json").read_bytes() == manifest


def test_nested_destructive_permissions_are_detected(tmp_path):
    make_project(tmp_path, [{"id": "invoke", "type": "invoke_workflow", "workflow": "Cleanup"}])
    (tmp_path / "workflows/cleanup.workflow.json").write_text(json.dumps({
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Cleanup",
        "variables": [], "arguments": [],
        "activities": [{"id": "delete", "type": "file_delete", "path": "output.txt"}],
    }), encoding="utf-8")
    project = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    project["workflows"]["Cleanup"] = "workflows/cleanup.workflow.json"
    (tmp_path / "project.json").write_text(json.dumps(project), encoding="utf-8")
    server = ProjectMCPServer(str(tmp_path), allow_run=True)
    plan = call(server, "openrpa_plan_workflow", {"name": "Main"})["structuredContent"]
    assert plan["requires"]["destructive"] is True
    result = call(server, "openrpa_run_workflow", {"name": "Main"})
    assert result["isError"] is True
    assert "--allow-destructive" in result["content"][0]["text"]


def test_api_delete_requires_destructive_permission_in_plan_and_run(tmp_path):
    make_project(tmp_path,[{"id":"remove","type":"api_request","connectionId":"example","method":"DELETE","path":"/records/42"}])
    server=ProjectMCPServer(str(tmp_path),allow_run=True,allow_network=True)
    plan=call(server,"openrpa_plan_workflow",{"name":"Main"})["structuredContent"]
    assert plan["requires"]["network"] is True and plan["requires"]["destructive"] is True
    result=call(server,"openrpa_run_workflow",{"name":"Main"})
    assert result["isError"] is True and "--allow-destructive" in result["content"][0]["text"]


def test_vault_credential_use_has_separate_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path, [{"id": "read-secret", "type": "credential_get", "service": "test", "username": "test", "result": "secret"}])
    server = ProjectMCPServer(str(tmp_path), allow_run=True)
    plan = call(server, "openrpa_plan_workflow", {"name": "Main"})["structuredContent"]
    assert plan["requires"]["credentials"] is True
    result = call(server, "openrpa_run_workflow", {"name": "Main"})
    assert result["isError"] is True
    assert "--allow-credentials" in result["content"][0]["text"]


def test_stdio_protocol_end_to_end(tmp_path):
    make_project(tmp_path)
    repository = Path(__file__).resolve().parents[1]
    manifest_hash=hashlib.sha256((tmp_path / "project.json").read_bytes()).hexdigest()
    env = dict(os.environ, PYTHONPATH=str(repository), OPENRPA_DATA_DIR=str(tmp_path / "data"))
    request_lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "openrpa_list_workflows", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "openrpa_activity_catalog", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "openrpa_validate_workflow_drafts", "arguments": {"workflows": {"Shared Helper": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [{"id": "helper-log", "type": "log", "level": "info", "message": "validated draft"}]}}}}},
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "openrpa_create_workflow", "arguments": {"name": "Shared Helper", "expectedProjectSha256": manifest_hash, "workflow": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [{"id": "helper-log", "type": "log", "level": "info", "message": "created over MCP"}]}}}},
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "openrpa_validate_project", "arguments": {}}},
    ]
    payload = "".join(json.dumps(line) + "\n" for line in request_lines)
    process = subprocess.run([sys.executable, "-m", "openrpa", "mcp", str(tmp_path), "--allow-edit"], cwd=repository,
                             env=env, input=payload, text=True, capture_output=True, timeout=15)
    assert process.returncode == 0, process.stderr
    assert process.stderr == ""
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert [response["id"] for response in responses] == [1, 2, 3, 4, 5, 6, 7]
    assert responses[0]["result"]["serverInfo"]["name"] == "open-rpa-studio"
    assert responses[2]["result"]["structuredContent"]["workflows"][0]["name"] == "Main"
    activities = responses[3]["result"]["structuredContent"]["activities"]
    assert any(item["type"] == "browser_navigate" and item["requiredPermissions"] == ["network"] for item in activities)
    assert responses[4]["result"]["structuredContent"]["valid"] is True
    assert responses[5]["result"]["structuredContent"]["created"] is True
    assert responses[6]["result"]["structuredContent"]["workflowCount"] == 2


def test_run_opt_in_executes_a_real_workflow_and_records_durable_history(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_run=True)
    result = call(server, "openrpa_run_workflow", {"name": "Main"})
    assert result["isError"] is False
    assert result["structuredContent"]["status"] == "succeeded"
    assert result["structuredContent"]["runId"]
    runs = call(server, "openrpa_list_run_history")["structuredContent"]["runs"]
    assert runs[0]["status"] == "succeeded"
    assert "projectPath" not in runs[0]


def test_stdio_cancellation_notification_stops_active_run(tmp_path):
    make_project(tmp_path, [{"id": "loop", "type": "while", "condition": "True", "body": [
        {"id": "wait", "type": "wait", "seconds": 30}
    ]}])
    repository = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(repository), OPENRPA_DATA_DIR=str(tmp_path / "data"))
    process = subprocess.Popen([sys.executable, "-m", "openrpa", "mcp", str(tmp_path), "--allow-run"],
                               cwd=repository, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, bufsize=1)
    responses = Queue()
    def read_stdout():
        for line in process.stdout:
            responses.put(json.loads(line))
    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    try:
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}) + "\n")
        process.stdin.flush()
        assert responses.get(timeout=5)["id"] == 1
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "openrpa_run_workflow", "arguments": {"name": "Main"}}}) + "\n")
        process.stdin.flush()
        time.sleep(0.15)
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7, "reason": "acceptance test"}}) + "\n")
        process.stdin.flush()
        response = responses.get(timeout=5)
        assert response["id"] == 7
        run_result = response["result"]["structuredContent"]
        assert response["result"]["isError"] is False
        assert run_result["status"] == "cancelled"
        assert run_result["runId"]
    finally:
        process.stdin.close()
        process.wait(timeout=5)
        stderr = process.stderr.read()
        process.stdout.close()
        process.stderr.close()
        assert process.returncode == 0, stderr
        assert stderr == ""
