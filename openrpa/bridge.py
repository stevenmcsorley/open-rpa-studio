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
from .model import load_project, validate_workflow, validate_workflow_bindings
from .history import RunHistory
from . import ai_providers
from . import ai_connections
from .debugger import DebugController
from .browser_inspector import BrowserInspector
from .activity_catalog import ACTIVITY_CATALOG

cancel_event = threading.Event()
stdout_lock = threading.Lock()
active_run_lock = threading.Lock()
active_run_id: str | None = None
active_debugger: DebugController | None = None
ai_draft_lock = threading.Lock()
ai_draft_cancellations: dict[str, threading.Event] = {}
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

def _ai_connections_path() -> Path:
    return _history_path().parent / "ai-connections.json"

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
            condition = item.get("breakpointCondition")
            conditional = isinstance(condition, str) and bool(condition.strip())
            if item.get("breakpoint") is True and not conditional and isinstance(item.get("id"),str):
                found.add(item["id"])
            for branch in ("then","else","body","catch","finally"):
                child=item.get(branch)
                if isinstance(child,list): walk(child)
            if item.get("type")=="switch":
                for case in item.get("cases",[]):
                    if isinstance(case,dict) and isinstance(case.get("activities"),list):walk(case["activities"])
                if isinstance(item.get("default"),list):walk(item["default"])
    activities=workflow.get("activities",[])
    if isinstance(activities,list): walk(activities)
    if workflow.get("executionModel")=="flowchart":
        for node in workflow.get("flowchart",{}).get("nodes",[]):
            condition = node.get("breakpointCondition")
            conditional = isinstance(condition, str) and bool(condition.strip())
            if node.get("breakpoint") is True and not conditional:
                action=node.get("activity")
                target=action.get("id") if node.get("kind")=="action" and isinstance(action,dict) else node.get("id")
                if isinstance(target,str): found.add(target)
            if node.get("kind")=="action" and isinstance(node.get("activity"),dict): walk([node["activity"]])
    if workflow.get("executionModel")=="state_machine":
        for state in workflow.get("stateMachine",{}).get("states",[]):
            condition = state.get("breakpointCondition")
            conditional = isinstance(condition, str) and bool(condition.strip())
            if state.get("breakpoint") is True and not conditional and isinstance(state.get("id"),str):found.add(state["id"])
            activities=state.get("activities",[])
            if isinstance(activities,list):walk(activities)
    return found

def _workflow_breakpoint_conditions(workflow: dict[str, Any]) -> dict[str, str]:
    """Collect conditional activity breakpoints without treating graph guards as breakpoints."""
    found: dict[str, str] = {}
    def walk(items: list[dict[str, Any]]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            aid = item.get("id")
            condition = item.get("breakpointCondition")
            if item.get("breakpoint") is True and isinstance(aid, str) and isinstance(condition, str) and condition.strip():
                found[aid] = condition
            for branch in ("then", "else", "body", "catch", "finally"):
                child = item.get(branch)
                if isinstance(child, list): walk(child)
            if item.get("type") == "switch":
                for case in item.get("cases", []):
                    if isinstance(case, dict) and isinstance(case.get("activities"), list): walk(case["activities"])
                if isinstance(item.get("default"), list): walk(item["default"])
    activities = workflow.get("activities", [])
    if isinstance(activities, list): walk(activities)
    if workflow.get("executionModel") == "flowchart":
        for node in workflow.get("flowchart", {}).get("nodes", []):
            node_id = node.get("id")
            condition = node.get("breakpointCondition")
            target = node_id
            if node.get("kind") == "action" and isinstance(node.get("activity"), dict):
                target = node["activity"].get("id")
            if node.get("breakpoint") is True and isinstance(target, str) and isinstance(condition, str) and condition.strip():
                found[target] = condition
            if node.get("kind") == "action" and isinstance(node.get("activity"), dict): walk([node["activity"]])
    if workflow.get("executionModel") == "state_machine":
        for state in workflow.get("stateMachine", {}).get("states", []):
            state_id = state.get("id")
            condition = state.get("breakpointCondition")
            if state.get("breakpoint") is True and isinstance(state_id, str) and isinstance(condition, str) and condition.strip():
                found[state_id] = condition
            if isinstance(state.get("activities"), list): walk(state["activities"])
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
        # The frozen Windows bridge can inherit a legacy console encoding. JSON
        # Unicode escapes keep every protocol frame pipe-safe while clients
        # still decode the original Unicode string values normally.
        sys.stdout.write(json.dumps(message, ensure_ascii=True, default=str) + "\n")
        sys.stdout.flush()


def handle(request: dict[str, Any], ai_cancel: threading.Event | None = None) -> None:
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
            binding_problems=validate_workflow_bindings(params["workflows"])
            if binding_problems:
                raise ValueError(binding_problems[0]["message"])
            for key, workflow in params["workflows"].items():
                problems = validate_workflow(workflow, set(project["workflows"]))
                if problems:
                    raise ValueError(f"{key}: " + problems[0]["message"])
                atomic_json(project_file(root, project["workflows"][key]), workflow)
            atomic_json(root / "project.json", project)
            history.audit("project.save",{"project":project.get("name",""),"workflowCount":len(project.get("workflows",{}))})
            result = {"saved": True}
        elif method == "project.package.export":
            from .package import pack_project
            result=pack_project(params["root"],params["destination"])
            history.audit("project.package.export",{"fileCount":result["files"],"sha256":result["sha256"]})
        elif method == "project.package.import":
            from .package import unpack_project
            result=unpack_project(params["package"],params["destination"])
            history.audit("project.package.import",{"fileCount":result["files"],"projectName":result.get("name",""),"sha256":result["sha256"]})
        elif method == "workflow.validate":
            project = params["project"]
            problems = validate_workflow(params["workflow"], set(project["workflows"]))
            if isinstance(params.get("workflows"),dict):
                owner=params.get("workflowName",params["workflow"].get("name"))
                problems.extend(item for item in validate_workflow_bindings(params["workflows"]) if item.get("workflow")==owner)
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
                debugger=DebugController(
                    _workflow_breakpoints(workflow_value),
                    conditional_breakpoints=_workflow_breakpoint_conditions(workflow_value),
                ) if params.get("debug") else None
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
        elif method == "debug.evaluate_watch":
            if active_debugger is None or active_run_id is None:
                raise ValueError("No debug run is active")
            result = active_debugger.evaluate_watch(params.get("expression"))
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
            from . import desktop_accessibility
            accessibility = desktop_accessibility.status()
            try:
                from .credentials import get_safe_keyring
                get_safe_keyring()
                vault={"available":True,"reason":None}
            except Exception as exc:
                vault={"available":False,"reason":str(exc)}
            result = {"browser": browser, "desktop": desktop, "accessibility": accessibility,"credentialVault":vault}
        elif method == "desktop.inspect.windows":
            if params.get("allowDesktop") is not True:
                raise ValueError("Desktop inspection requires explicit desktop permission in the Studio toolbar")
            from . import desktop_accessibility
            windows=desktop_accessibility.list_windows()
            history.audit("desktop.accessibility_windows_inspected",{"count":len(windows)})
            result={"windows":windows}
        elif method == "desktop.inspect.controls":
            if params.get("allowDesktop") is not True:
                raise ValueError("Desktop inspection requires explicit desktop permission in the Studio toolbar")
            from . import desktop_accessibility
            controls=desktop_accessibility.list_controls(str(params.get("windowTitle","")),params.get("processId"))
            history.audit("desktop.accessibility_controls_inspected",{"count":len(controls)})
            result={"controls":controls}
        elif method == "browser.inspect.open":
            if params.get("allowNetwork") is not True:
                raise ValueError("Browser inspection requires explicit network permission in the Studio toolbar")
            opened=browser_inspector.open(str(params.get("url","")))
            from urllib.parse import urlsplit
            history.audit("browser.inspector_open",{"host":urlsplit(opened["url"]).hostname,"networkPermission":True})
            result=opened
        elif method == "browser.inspect.controls":
            result=browser_inspector.controls()
        elif method == "browser.inspect.record.start":
            if params.get("allowNetwork") is not True:
                raise ValueError("Browser recording requires explicit network permission in the Studio toolbar")
            result=browser_inspector.start_recording()
            history.audit("browser.recorder_start",{"host":__import__("urllib.parse",fromlist=["urlsplit"]).urlsplit(result["url"]).hostname,"networkPermission":True})
        elif method == "browser.inspect.record.stop":
            result=browser_inspector.stop_recording()
            history.audit("browser.recorder_stop",{"eventCount":len(result["events"]),"truncated":result["truncated"]})
        elif method == "browser.inspect.close":
            browser_inspector.close()
            result={"closed":True}
        elif method == "ai.providers":
            result={"providers":ai_providers.catalog()}
        elif method == "ai.connections.list":
            result={"profiles":ai_connections.list_profiles(_ai_connections_path())}
        elif method == "ai.connections.save":
            profile=ai_connections.save_profile(_ai_connections_path(),params.get("profile"))
            history.audit("ai.connection.save",{"profileId":profile["id"],"provider":profile["provider"],"local":bool(ai_providers.PROVIDERS[profile["provider"]]["local"])})
            result={"profile":profile}
        elif method == "ai.connections.delete":
            profile_id=params.get("profileId")
            ai_connections.delete_profile(_ai_connections_path(),profile_id)
            history.audit("ai.connection.delete",{"profileId":profile_id})
            result={"deleted":True,"profileId":profile_id}
        elif method == "credential.store":
            service=params.get("service")
            username=params.get("username")
            secret=params.get("secret")
            if not isinstance(service,str) or not service.strip() or len(service)>200:
                raise ValueError("Credential vault service must contain 1–200 characters")
            if not isinstance(username,str) or not username.strip() or len(username)>200:
                raise ValueError("Credential vault username must contain 1–200 characters")
            if not isinstance(secret,str) or not secret or len(secret)>8192:
                raise ValueError("Credential must contain 1–8,192 characters")
            from .credentials import get_safe_keyring
            vault=get_safe_keyring()
            try:
                vault.set_password(service.strip(),username.strip(),secret)
            except Exception as exc:
                raise ValueError(f"OS credential vault refused to store the credential ({type(exc).__name__})") from None
            history.audit("credential.store",{"service":service.strip(),"username":username.strip(),"secretStored":True})
            result={"stored":True,"service":service.strip(),"username":username.strip()}
        elif method == "ai.models":
            provider=str(params.get("provider","ollama"))
            history.audit("ai.models",{"provider":provider,"local":bool(ai_providers.PROVIDERS.get(provider,{}).get("local"))})
            models=ai_providers.models(provider,params.get("baseUrl"),params.get("credentialService"),params.get("credentialUsername"))
            result={"models":models,"provider":provider}
        elif method == "ai.cancel":
            draft_id=params.get("draftId")
            if not isinstance(draft_id,str) or not draft_id or len(draft_id)>128:
                raise ValueError("AI draft cancellation requires a valid draft ID")
            with ai_draft_lock:
                cancellation=ai_draft_cancellations.get(draft_id)
            if cancellation is not None:
                cancellation.set()
            history.audit("ai.cancel",{"draftId":draft_id,"active":cancellation is not None})
            result={"cancelled":cancellation is not None,"draftId":draft_id}
        elif method == "ai.draft":
            provider=str(params.get("provider","ollama"))
            model=str(params.get("model","")).strip()
            types=[x["type"] for x in ACTIVITY_CATALOG]
            execution_model=str(params.get("executionModel","sequence"))
            history.audit("ai.draft",{"provider":provider,"model":model[:200],"workflowModel":execution_model,"local":bool(ai_providers.PROVIDERS.get(provider,{}).get("local"))})
            compatibility_warnings=[]
            def record_ai_compatibility_fallback(message: str) -> None:
                compatibility_warnings.append(message)
                history.audit("ai.structured_output_fallback",{"provider":provider,"model":model[:200]})
            draft=ai_providers.draft(provider,model,params.get("prompt",""),types,params.get("baseUrl"),
                params.get("credentialService"),params.get("credentialUsername"),execution_model,ai_cancel,
                on_compatibility_fallback=record_ai_compatibility_fallback)
            if ai_cancel is not None and ai_cancel.is_set():
                raise ai_providers.RequestCancelled("Provider request was cancelled")
            payload_key={"sequence":"activities","flowchart":"flowchart","state_machine":"stateMachine"}.get(execution_model)
            if payload_key is None:raise ValueError("AI workflow model must be sequence, flowchart, or state_machine")
            if not isinstance(draft,dict) or set(draft)-{"explanation",payload_key}:
                raise ValueError(f"Model output must contain explanation and {payload_key} only")
            payload=draft.get(payload_key)
            activities=payload if execution_model=="sequence" else ([node.get("activity") for node in payload.get("nodes",[]) if isinstance(node,dict) and node.get("kind")=="action"] if execution_model=="flowchart" and isinstance(payload,dict) else ([state.get("activities",[]) for state in payload.get("states",[]) if isinstance(state,dict)] if execution_model=="state_machine" and isinstance(payload,dict) else []))
            if execution_model=="sequence" and (not isinstance(activities,list) or len(activities)>300):raise ValueError("Model draft must contain no more than 300 activities")
            def count_activities(items: list[Any]) -> int:
                total=0
                for item in items:
                    if not isinstance(item,dict): continue
                    total+=1
                    for branch in ("then","else","body","catch","finally"):
                        if isinstance(item.get(branch),list): total+=count_activities(item[branch])
                    if item.get("type")=="switch":
                        for case in item.get("cases",[]):
                            if isinstance(case,dict) and isinstance(case.get("activities"),list):total+=count_activities(case["activities"])
                        if isinstance(item.get("default"),list):total+=count_activities(item["default"])
                    if total>300: return total
                return total
            activity_lists=[activities] if execution_model in {"sequence","flowchart"} else activities
            if any(not isinstance(items,list) or count_activities(items)>300 for items in activity_lists):raise ValueError("Model draft contains more than 300 activities including nested branches")
            workflow={"format":"openrpa.workflow","formatVersion":1,"name":"AI Draft","variables":[],"arguments":[],"activities":[] if execution_model!="sequence" else activities}
            if execution_model!="sequence":workflow["executionModel"]=execution_model;workflow["flowchart" if execution_model=="flowchart" else "stateMachine"]=payload
            problems=validate_workflow(workflow,set(params.get("workflows",["Main"])))
            result={"explanation":str(draft.get("explanation",""))[:4000],"workflow":workflow,"valid":not problems,"problems":problems,"model":model,"provider":provider,"warnings":compatibility_warnings}
        else:
            raise ValueError(f"Unknown bridge method: {method}")
        send({"id": request.get("id"), "result": result})
    except Exception as exc:
        send({"id": request.get("id"), "error": {"message": str(exc), "type": type(exc).__name__}})





def main() -> None:
    for line in sys.stdin:
        request: Any = None
        try:
            request=json.loads(line)
            if request.get("method")!="ai.draft":
                handle(request)
                continue
            params=request.get("params",{})
            draft_id=params.get("draftId",str(request.get("id","")))
            if not isinstance(draft_id,str) or not draft_id or len(draft_id)>128:
                raise ValueError("AI draft requires a valid draft ID")
            cancellation=threading.Event()
            with ai_draft_lock:
                if draft_id in ai_draft_cancellations:
                    raise ValueError("An AI draft with this ID is already active")
                ai_draft_cancellations[draft_id]=cancellation

            def finish_draft(current_request: dict[str, Any]=request, current_id: str=draft_id,
                             current_cancel: threading.Event=cancellation) -> None:
                try:
                    handle(current_request,current_cancel)
                finally:
                    with ai_draft_lock:
                        if ai_draft_cancellations.get(current_id) is current_cancel:
                            ai_draft_cancellations.pop(current_id,None)

            threading.Thread(target=finish_draft,name="openrpa-ai-draft",daemon=True).start()
        except Exception as exc:
            send({"id":request.get("id") if isinstance(request,dict) else None,
                  "error": {"message": str(exc), "type": type(exc).__name__}})


if __name__ == "__main__":
    main()
