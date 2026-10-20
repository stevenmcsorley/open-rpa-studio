"""Newline-delimited JSON bridge used by the desktop application."""
from __future__ import annotations
import json
import os
import sys
import tempfile
import threading
import hashlib
import importlib.util
import atexit
from pathlib import Path
from typing import Any
from .engine import RunOptions, run_project
from .model import load_project, validate_workflow
from .history import RunHistory
from . import ai_providers
from .debugger import DebugController
from .browser_inspector import BrowserInspector

cancel_event = threading.Event()
stdout_lock = threading.Lock()
active_run_lock = threading.Lock()
active_run_id: str | None = None
active_debugger: DebugController | None = None
browser_inspector=BrowserInspector()
atexit.register(browser_inspector.close)

def _history_path() -> Path:
    configured = os.environ.get("OPENRPA_DATA_DIR")
    if configured:
        return Path(configured).expanduser() / "run-history.sqlite3"
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "OpenRPAStudio" / "run-history.sqlite3"

history = RunHistory(_history_path())

def project_file(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = (root / relative).resolve()
    try: path.relative_to(root)
    except ValueError as exc: raise ValueError(f"Project path escapes the project root: {relative}") from exc
    return path

def _workflow_breakpoints(workflow: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            if not isinstance(item,dict):
                continue
            if item.get("breakpoint") is True and isinstance(item.get("id"),str):
                found.add(item["id"])
            for branch in ("then","else","body","catch","finally"):
                child=item.get(branch)
                if isinstance(child,list): walk(child)
    activities=workflow.get("activities",[])
    if isinstance(activities,list): walk(activities)
    if workflow.get("executionModel")=="flowchart":
        for node in workflow.get("flowchart",{}).get("nodes",[]):
            if node.get("breakpoint") is True:
                action=node.get("activity")
                target=action.get("id") if node.get("kind")=="action" and isinstance(action,dict) else node.get("id")
                if isinstance(target,str): found.add(target)
            if node.get("kind")=="action" and isinstance(node.get("activity"),dict): walk([node["activity"]])
    return found

def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".openrpa-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def send(message: dict[str, Any]) -> None:
    with stdout_lock:
        sys.stdout.write(json.dumps(message, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()


def handle(request: dict[str, Any]) -> None:
    global active_run_id, active_debugger
    method = request.get("method")
    params = request.get("params", {})
    try:
        if method == "project.open":
            project, root = load_project(params["path"])
            history.audit("project.open",{"project":project.get("name",""),"workflowCount":len(project.get("workflows",{}))})
            workflows = {}
            for key, rel in project["workflows"].items():
                workflows[key] = json.loads(project_file(root, rel).read_text(encoding="utf-8"))
            result = {"project": project, "root": str(root), "workflows": workflows}
        elif method == "project.create":
            root = Path(params["path"]).expanduser().resolve()
            root.mkdir(parents=True, exist_ok=True)
            project = {"format": "openrpa.project", "formatVersion": 1, "name": params.get("name", "Untitled Project"), "main": "Main", "workflows": {"Main": "workflows/main.workflow.json"}}
            wf_path = project_file(root, project["workflows"]["Main"])
            wf_path.parent.mkdir(parents=True, exist_ok=True)
            workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Main", "variables": [], "arguments": [], "activities": []}
            atomic_json(wf_path, workflow)
            atomic_json(root / "project.json", project)
            history.audit("project.create",{"project":project.get("name",""),"workflowCount":len(project["workflows"])})
            result = {"project": project, "root": str(root), "workflows": {"Main": workflow}}
        elif method == "project.save":
            root = Path(params["root"]).resolve()
            project = params["project"]
            for key, workflow in params["workflows"].items():
                problems = validate_workflow(workflow, set(project["workflows"]))
                if problems:
                    raise ValueError(f"{key}: " + problems[0]["message"])
                atomic_json(project_file(root, project["workflows"][key]), workflow)
            atomic_json(root / "project.json", project)
            history.audit("project.save",{"project":project.get("name",""),"workflowCount":len(project.get("workflows",{}))})
            result = {"saved": True}
        elif method == "workflow.validate":
            project = params["project"]
            problems = validate_workflow(params["workflow"], set(project["workflows"]))
            result = {"valid": not problems, "problems": problems}
        elif method == "workflow.run":
            project = params["project"]
            root = Path(params["root"]).resolve()
            workflow_name = params.get("workflow") or project.get("main")
            with active_run_lock:
                if active_run_id is not None:
                    raise ValueError("A workflow is already running. Stop it and wait for completion before starting another.")
                cancel_event.clear()
                workflow_path = project_file(root, project["workflows"][workflow_name])
                workflow_value = json.loads(workflow_path.read_text(encoding="utf-8"))
                digest = hashlib.sha256(json.dumps(workflow_value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
                run_id = history.start(str(root), str(project.get("name", "")), workflow_name, digest)
                active_run_id = run_id
                debugger=DebugController(_workflow_breakpoints(workflow_value)) if params.get("debug") else None
                active_debugger=debugger
            if params.get("allowNetwork"):
                history.audit("permission.granted", {"runId": run_id, "permission": "network"})
            if params.get("allowDesktop"):
                history.audit("permission.granted", {"runId": run_id, "permission": "desktop"})
            def record_event(e: dict[str, Any]) -> None:
                durable_event=dict(e)
                if durable_event.get("event")=="debug.paused":
                    # Live variable snapshots belong in the debugger UI only; do
                    # not retain arbitrary workflow data in durable run history.
                    durable_event.pop("variables",None)
                    durable_event.pop("editableVariables",None)
                history.event(run_id, durable_event)
                if e.get("event") == "activity-started":
                    history.audit("activity.started", {"runId": run_id, "activityId": e.get("activityId"), "type": e.get("type")})
                elif e.get("event") == "debug.variable-edited":
                    history.audit("debug.variable_edited", {"runId":run_id,"name":e.get("name"),"type":e.get("type")})
                send({"event": "run.event", "data": {**e, "runId": run_id}})
            options = RunOptions(allow_network=bool(params.get("allowNetwork", False)), allow_desktop=bool(params.get("allowDesktop", False)), cancel=cancel_event.is_set, event=record_event, audit=history.audit,debugger=debugger)
            def run_and_reply() -> None:
                global active_run_id, active_debugger
                try:
                    output = run_project(project, root, workflow_name, params.get("inputs"), options).__dict__
                    persisted = {key: output.get(key) for key in ("status", "activities", "error")}
                    output["runId"] = run_id
                    reply={"id":request.get("id"),"result":output}
                except Exception as exc:
                    error = {"message": str(exc), "type": type(exc).__name__}
                    reply={"id":request.get("id"),"error":error}
                finally:
                    try:
                        value=reply.get("result")
                        status=value.get("status","failed") if isinstance(value,dict) else "failed"
                        persisted={key:value.get(key) for key in ("status","activities","error")} if isinstance(value,dict) else None
                        failure=reply.get("error") or (value.get("error") if isinstance(value,dict) else None)
                        history.finish(run_id,status,persisted,failure)
                    except Exception as history_exc:
                        if isinstance(reply.get("result"),dict):
                            reply["result"]["historyWarning"]=f"Run completed but could not be fully saved to history: {history_exc}"
                        else:
                            reply.setdefault("error",{})["historyWarning"]=str(history_exc)
                    with active_run_lock:
                        active_run_id = None
                        active_debugger = None
                    send(reply)
            threading.Thread(target=run_and_reply, name="openrpa-workflow-run", daemon=True).start()
            return
        elif method == "workflow.cancel":
            cancel_event.set()
            if active_debugger is not None:
                active_debugger.wake_for_cancel()
            if active_run_id:
                history.audit("run.cancel_requested", {"runId": active_run_id})
            result = {"cancelled": True}
        elif method in {"debug.pause","debug.resume","debug.step_over","debug.step_into","debug.step_out","debug.set_variable"}:
            if active_debugger is None or active_run_id is None:
                raise ValueError("No debug run is active")
            if method=="debug.set_variable":
                metadata=active_debugger.set_variable(params.get("name"),params.get("value"))
                event={"event":"debug.variable-edited",**metadata}
                history.audit("debug.variable_edited",{"runId":active_run_id,**metadata})
                result={"updated":True,**metadata}
                send({"id":request.get("id"),"result":result})
                send({"event":"run.event","data":{"runId":active_run_id,**event}})
                return
            elif method=="debug.pause": active_debugger.pause()
            elif method=="debug.resume": active_debugger.resume()
            elif method=="debug.step_over": active_debugger.step_over()
            elif method=="debug.step_into": active_debugger.step_into()
            else: active_debugger.step_out()
            history.audit(method,{"runId":active_run_id})
            result={"requested":method.split(".",1)[1],"runId":active_run_id}
        elif method == "run.history":
            result = {"runs": history.list_runs(params.get("limit", 50))}
        elif method == "run.get":
            result = {"run": history.get_run(str(params.get("runId", "")))}
        elif method == "audit.history":
            result = {"events": history.list_audit(params.get("limit", 200))}
        elif method == "activity.catalog":
            result = ACTIVITY_CATALOG
        elif method == "adapter.status":
            browser = {"available": False, "reason": "Optional Playwright package is not installed"}
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as runtime:
                    executable = Path(runtime.chromium.executable_path)
                    if executable.is_file():
                        test_browser=runtime.chromium.launch(headless=True)
                        test_browser.close()
                        browser = {"available": True, "reason": None, "engine": "Chromium", "executablePresent": True}
                    else:
                        browser = {"available": False, "reason": "Playwright is installed, but Chromium is missing; run 'playwright install chromium'", "engine": "Chromium", "executablePresent": False}
            except ImportError:
                pass
            except Exception as exc:
                browser = {"available": False, "reason": f"Playwright runtime probe failed: {type(exc).__name__}: {exc}"}
            desktop = {"available": False, "reason": "Optional PyAutoGUI package is not installed"}
            try:
                import pyautogui
                if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                    desktop = {"available": False, "reason": "PyAutoGUI is installed, but no graphical session is available"}
                else:
                    size = pyautogui.size()
                    desktop = {"available": bool(size.width and size.height), "reason": None, "adapter": "PyAutoGUI coordinate fallback"}
            except ImportError:
                pass
            except Exception as exc:
                desktop = {"available": False, "reason": f"Desktop probe failed: {type(exc).__name__}: {exc}"}
            accessibility = {"available": False, "reason": "AT-SPI accessibility adapter is not implemented"}
            if sys.platform.startswith("linux") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
                try:
                    import gi
                    gi.require_version("Atspi", "2.0")
                    from gi.repository import Atspi  # noqa: F401
                    accessibility = {"available": False, "reason": "AT-SPI bindings exist, but Open RPA has not implemented this adapter"}
                except Exception as exc:
                    accessibility = {"available": False, "reason": f"AT-SPI runtime unavailable: {type(exc).__name__}: {exc}"}
            try:
                from .credentials import get_safe_keyring
                get_safe_keyring()
                vault={"available":True,"reason":None}
            except Exception as exc:
                vault={"available":False,"reason":str(exc)}
            result = {"browser": browser, "desktop": desktop, "accessibility": accessibility,"credentialVault":vault}
        elif method == "browser.inspect.open":
            if params.get("allowNetwork") is not True:
                raise ValueError("Browser inspection requires explicit network permission in the Studio toolbar")
            opened=browser_inspector.open(str(params.get("url","")))
            from urllib.parse import urlsplit
            history.audit("browser.inspector_open",{"host":urlsplit(opened["url"]).hostname,"networkPermission":True})
            result=opened
        elif method == "browser.inspect.controls":
            result=browser_inspector.controls()
        elif method == "browser.inspect.close":
            browser_inspector.close()
            result={"closed":True}
        elif method == "ai.providers":
            result={"providers":ai_providers.catalog()}
        elif method == "ai.models":
            provider=str(params.get("provider","ollama"))
            history.audit("ai.models",{"provider":provider,"local":bool(ai_providers.PROVIDERS.get(provider,{}).get("local"))})
            models=ai_providers.models(provider,params.get("baseUrl"),params.get("credentialService"),params.get("credentialUsername"))
            result={"models":models,"provider":provider}
        elif method == "ai.draft":
            provider=str(params.get("provider","ollama"))
            model=str(params.get("model","")).strip()
            history.audit("ai.draft",{"provider":provider,"model":model[:200],"local":bool(ai_providers.PROVIDERS.get(provider,{}).get("local"))})
            types=[x["type"] for x in ACTIVITY_CATALOG]
            draft=ai_providers.draft(provider,model,params.get("prompt",""),types,params.get("baseUrl"),
                params.get("credentialService"),params.get("credentialUsername"))
            if not isinstance(draft,dict) or set(draft)-{"explanation","activities"}:
                raise ValueError("Model output must be an object containing only explanation and activities")
            activities=draft.get("activities")
            if not isinstance(activities,list) or len(activities)>300: raise ValueError("Model draft must contain no more than 300 activities")
            def count_activities(items: list[Any]) -> int:
                total=0
                for item in items:
                    if not isinstance(item,dict): continue
                    total+=1
                    for branch in ("then","else","body","catch","finally"):
                        if isinstance(item.get(branch),list): total+=count_activities(item[branch])
                    if total>300: return total
                return total
            if count_activities(activities)>300: raise ValueError("Model draft contains more than 300 activities including nested branches")
            workflow={"format":"openrpa.workflow","formatVersion":1,"name":"AI Draft","variables":[],"arguments":[],"activities":activities}
            problems=validate_workflow(workflow,set(params.get("workflows",["Main"])))
            result={"explanation":str(draft.get("explanation",""))[:4000],"workflow":workflow,"valid":not problems,"problems":problems,"model":model,"provider":provider}
        else:
            raise ValueError(f"Unknown bridge method: {method}")
        send({"id": request.get("id"), "result": result})
    except Exception as exc:
        send({"id": request.get("id"), "error": {"message": str(exc), "type": type(exc).__name__}})


ACTIVITY_CATALOG = [
    {"type":"assign","title":"Assign","category":"Variables","description":"Evaluate a safe expression into a variable.","defaults":{"target":"result","value":""}},
    {"type":"credential_get","title":"Get Credential","category":"Security","description":"Read a secret from an approved operating-system credential vault. Never store secrets in the project.","defaults":{"service":"my-service","username":"user","result":"credential"}},
    {"type":"log","title":"Log Message","category":"Workflow","description":"Write a structured execution log entry.","defaults":{"level":"info","message":""}},
    {"type":"if","title":"If","category":"Control Flow","description":"Choose a sequence using a safe boolean expression.","defaults":{"condition":"True","then":[],"else":[]}},
    {"type":"for_each","title":"For Each","category":"Control Flow","description":"Repeat nested activities for each value in a collection.","defaults":{"items":"[]","itemName":"item","body":[]}},
    {"type":"while","title":"While","category":"Control Flow","description":"Repeat a bounded activity sequence while a safe boolean expression is true.","defaults":{"condition":"False","body":[]}},
    {"type":"retry","title":"Retry Scope","category":"Reliability","description":"Retry selected error codes with bounded backoff. Multiple attempts require explicit repeat-safety acknowledgement.","defaults":{"maxAttempts":3,"retryOn":["http-timeout"],"delaySeconds":1,"backoffFactor":2,"repeatSafe":False,"body":[]}},
    {"type":"switch","title":"Switch","category":"Control Flow","description":"Route a value to the first matching case or the default branch.","defaults":{"expression":"value","cases":[{"value":"Approved","activities":[]}],"default":[]}},
    {"type":"try","title":"Try / Catch","category":"Control Flow","description":"Handle an activity failure in a catch sequence.","defaults":{"body":[],"catch":[],"errorName":"error"}},
    {"type":"invoke_workflow","title":"Invoke Workflow","category":"Workflow","description":"Call another project workflow with typed arguments.","defaults":{"workflow":"Main","inputs":{}}},
    {"type":"file_read_text","title":"Read Text File","category":"Files","description":"Read a UTF-8 text file within approved project roots.","defaults":{"path":"input.txt","result":"text"}},
    {"type":"file_write_text","title":"Write Text File","category":"Files","description":"Write a UTF-8 file within approved project roots.","defaults":{"path":"output.txt","text":"{{text}}"}},
    {"type":"file_copy","title":"Copy File","category":"Files","description":"Copy a file within approved project roots.","defaults":{"source":"input.txt","destination":"copy.txt"}},
    {"type":"file_move","title":"Move File","category":"Files","description":"Move a file within approved project roots.","defaults":{"source":"input.txt","destination":"moved.txt"}},
    {"type":"file_delete","title":"Delete File","category":"Files","description":"Delete one file within approved project roots.","defaults":{"path":"temporary.txt","missingOk":False}},
    {"type":"file_list","title":"List Files","category":"Files","description":"List files in an approved project directory.","defaults":{"directory":".","pattern":"*","result":"files"}},
    {"type":"csv_read","title":"Read CSV","category":"Data","description":"Read CSV rows as dictionaries.","defaults":{"path":"input.csv","delimiter":",","result":"rows"}},
    {"type":"csv_write","title":"Write CSV","category":"Data","description":"Write a list of records to CSV.","defaults":{"path":"output.csv","rows":"rows"}},
    {"type":"transform_field","title":"Transform Field","category":"Data","description":"Trim, change case, or regex-replace a field across records.","defaults":{"rows":"rows","field":"name","operation":"trim","result":"rows"}},
    {"type":"json_parse","title":"Parse JSON","category":"Data","description":"Parse JSON text, optionally selecting a dotted path.","defaults":{"text":"{}","result":"data"}},
    {"type":"json_write","title":"Write JSON","category":"Data","description":"Serialize a variable as JSON.","defaults":{"value":"data","path":"output.json"}},
    {"type":"regex_replace","title":"Regex Replace","category":"Text","description":"Apply a regular-expression replacement to text.","defaults":{"text":"text","pattern":"","replacement":"","result":"text"}},
    {"type":"regex_match","title":"Regex Match","category":"Text","description":"Extract a regular-expression match or named capture groups.","defaults":{"text":"text","pattern":"","result":"match"}},
    {"type":"wait","title":"Wait","category":"Workflow","description":"Wait for a bounded duration; cancellation remains responsive.","defaults":{"seconds":1}},
    {"type":"http_request","title":"HTTP Request","category":"Network","description":"Make a request only after explicit network permission at run time.","defaults":{"method":"GET","url":"https://example.invalid","timeoutSeconds":20}},
    {"type":"browser_launch","title":"Launch Browser","category":"Browser","description":"Open Chromium using the optional Playwright runtime.","defaults":{"headless":False}},
    {"type":"browser_navigate","title":"Navigate Browser","category":"Browser","description":"Navigate the controlled browser after per-run network permission.","defaults":{"url":"https://example.invalid","waitUntil":"domcontentloaded"}},
    {"type":"browser_click","title":"Click Web Element","category":"Browser","description":"Click an element selected by role, label, text, test ID or CSS.","defaults":{"selectorKind":"role","selector":"button:Save","timeoutSeconds":15}},
    {"type":"browser_fill","title":"Fill Web Field","category":"Browser","description":"Fill an accessible web field.","defaults":{"selectorKind":"label","selector":"Email","value":"","timeoutSeconds":15}},
    {"type":"browser_select","title":"Select Web Option","category":"Browser","description":"Select an option by its submitted value from an accessible list.","defaults":{"selectorKind":"role","selector":"combobox:Country","value":"","timeoutSeconds":15}},
    {"type":"browser_check","title":"Check Web Option","category":"Browser","description":"Set an accessible checkbox or radio control to checked.","defaults":{"selectorKind":"role","selector":"checkbox:Accept terms","timeoutSeconds":15}},
    {"type":"browser_uncheck","title":"Uncheck Web Option","category":"Browser","description":"Set an accessible checkbox to unchecked.","defaults":{"selectorKind":"role","selector":"checkbox:Accept terms","timeoutSeconds":15}},
    {"type":"browser_text","title":"Read Web Text","category":"Browser","description":"Read text from a selected page element.","defaults":{"selectorKind":"role","selector":"heading:Main","result":"text","timeoutSeconds":15}},
    {"type":"browser_screenshot","title":"Browser Screenshot","category":"Browser","description":"Save a browser screenshot in the project folder.","defaults":{"path":"evidence/page.png","fullPage":True}},
    {"type":"browser_close","title":"Close Browser","category":"Browser","description":"Close the current automation browser.","defaults":{}},
    {"type":"desktop_click","title":"Click Screen Coordinates","category":"Desktop","description":"Click screen coordinates through optional PyAutoGUI; requires per-run approval.","defaults":{"x":0,"y":0}},
    {"type":"desktop_type","title":"Type Text","category":"Desktop","description":"Type into the focused application; requires per-run approval.","defaults":{"text":""}},
    {"type":"desktop_hotkey","title":"Press Hotkey","category":"Desktop","description":"Press a hotkey in the focused application; requires per-run approval.","defaults":{"keys":"CTRL+S"}},
    {"type":"desktop_press","title":"Press Key","category":"Desktop","description":"Press a key in the focused application; requires per-run approval.","defaults":{"key":"ENTER"}},
    {"type":"desktop_screenshot","title":"Desktop Screenshot","category":"Desktop","description":"Capture the desktop screen; requires per-run approval.","defaults":{"path":"evidence/desktop.png"}},
]


def main() -> None:
    for line in sys.stdin:
        try:
            handle(json.loads(line))
        except Exception as exc:
            send({"error": {"message": str(exc), "type": type(exc).__name__}})


if __name__ == "__main__":
    main()
