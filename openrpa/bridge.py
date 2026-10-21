"""Newline-delimited JSON bridge used by the desktop application."""
from __future__ import annotations
import json
import os
import sys
import tempfile
import threading
import hashlib
import importlib.util
import shutil
import subprocess
import atexit
from pathlib import Path
from typing import Any
from .engine import RunOptions, run_project
from .model import load_project, validate_workflow, validate_workflow_bindings
from .history import RunHistory, read_run, read_runs
from . import ai_providers
from . import ai_connections
from . import api_connections
from .debugger import DebugController
from .browser_inspector import BrowserInspector
from .desktop_recorder import DesktopClickRecorder, create_desktop_recorder, desktop_recorder_status
from .activity_catalog import ACTIVITY_CATALOG
from .active_project import publish_active_project, read_active_project
from .app_paths import app_data_dir
from .orchestration import read_jobs, request_job_cancel

cancel_event = threading.Event()
stdout_lock = threading.Lock()
active_run_lock = threading.Lock()
active_run_id: str | None = None
active_debugger: DebugController | None = None
ai_draft_lock = threading.Lock()
ai_draft_cancellations: dict[str, threading.Event] = {}
api_auth_cancellations: dict[str, threading.Event] = {}
api_auth_lock = threading.Lock()
browser_inspector=BrowserInspector()
desktop_recorder=create_desktop_recorder()
atexit.register(browser_inspector.close)
atexit.register(desktop_recorder.close)

def _history_path() -> Path:
    configured = os.environ.get("OPENRPA_DATA_DIR")
    if configured:
        return Path(configured).expanduser() / "run-history.sqlite3"
    return app_data_dir() / "run-history.sqlite3"

def _mcp_history_path(root: Path) -> Path | None:
    """Locate MCP's per-project ledger, which the desktop reads without recovery writes."""
    try:
        project_root = root.resolve()
        project_key = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:16]
        configured = os.environ.get("OPENRPA_DATA_DIR")
        if configured:
            return Path(configured).expanduser() / f"mcp-run-history-{project_key}.sqlite3"
        return app_data_dir() / f"mcp-run-history-{project_key}.sqlite3"
    except (OSError, RuntimeError):
        return None

def _mcp_job_queue_path(root: Path) -> Path:
    project_key = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]
    configured = os.environ.get("OPENRPA_DATA_DIR")
    if configured:
        return Path(configured).expanduser() / f"job-queue-{project_key}.sqlite3"
    return app_data_dir() / f"job-queue-{project_key}.sqlite3"

def _mcp_runs(limit: int) -> list[dict[str, Any]]:
    root = read_active_project()
    path = _mcp_history_path(root) if root else None
    if path is None:
        return []
    return [{**item, "source": "MCP"} for item in read_runs(path, limit)]

def _mcp_run(run_id: str) -> dict[str, Any] | None:
    root = read_active_project()
    path = _mcp_history_path(root) if root else None
    item = read_run(path, run_id) if path else None
    return {**item, "source": "MCP"} if item else None

def _ai_connections_path() -> Path:
    return _history_path().parent / "ai-connections.json"

def _api_connections_path() -> Path:
    return api_connections.default_store_path()

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


def _api_request_connection_problems(workflow: dict[str, Any], profiles: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Ensure AI-generated API calls reference a connection configured locally."""
    known={profile.get("id") for profile in profiles if isinstance(profile,dict)}
    problems=[]
    def visit(value: Any) -> None:
        if isinstance(value,dict):
            if value.get("type")=="api_request" and value.get("connectionId") not in known:
                problems.append({"code":"api-connection-unknown",
                    "message":"API Request must reference one of this computer's saved API connections; create a connection in API Connections and regenerate the draft.",
                    "activityId":str(value.get("id", ""))})
            for child in value.values(): visit(child)
        elif isinstance(value,list):
            for child in value: visit(child)
    visit(workflow)
    return problems

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

def _repair_flowchart_node_id_collisions(graph: Any) -> list[str]:
    """Rename graph nodes that collide with their contained activity IDs.

    Models commonly reuse an action's activity ID for its graph node. Node IDs
    are structural references, so a deterministic rename plus edge rewrites is
    safe; activity IDs (used by logs and breakpoints) remain untouched. Other
    malformed graph IDs are left to normal validation.
    """
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        return []
    nodes = graph["nodes"]
    node_ids = [node.get("id") for node in nodes if isinstance(node, dict) and isinstance(node.get("id"), str)]
    if len(node_ids) != len(set(node_ids)):
        return []
    activity_ids: set[str] = set()
    def visit(activity: Any) -> None:
        if not isinstance(activity, dict):
            return
        identifier = activity.get("id")
        if isinstance(identifier, str):
            activity_ids.add(identifier)
        for branch in ("then", "else", "body", "catch", "finally", "default"):
            children = activity.get(branch)
            if isinstance(children, list):
                for child in children: visit(child)
        cases = activity.get("cases", [])
        if isinstance(cases, list):
            for case in cases:
                if isinstance(case, dict) and isinstance(case.get("activities"), list):
                    for child in case["activities"]: visit(child)
    for node in nodes:
        if isinstance(node, dict) and node.get("kind") == "action":
            visit(node.get("activity"))
    if not activity_ids.intersection(node_ids):
        return []
    reserved = set(node_ids) | activity_ids
    mapping: dict[str, str] = {}
    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, dict) or node.get("id") not in activity_ids:
            continue
        candidate = f"node-{index}"
        suffix = 1
        while candidate in reserved:
            suffix += 1
            candidate = f"node-{index}-{suffix}"
        reserved.add(candidate)
        mapping[node["id"]] = candidate
        node["id"] = candidate
    if not mapping:
        return []
    if graph.get("start") in mapping:
        graph["start"] = mapping[graph["start"]]
    transitions = graph.get("transitions")
    if isinstance(transitions, list):
        for transition in transitions:
            if not isinstance(transition, dict):
                continue
            if transition.get("from") in mapping: transition["from"] = mapping[transition["from"]]
            if transition.get("to") in mapping: transition["to"] = mapping[transition["to"]]
    return ["Adjusted a flowchart node ID that collided with an activity ID; activity IDs were preserved."]

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
            publish_active_project(root)
            history.audit("project.open",{"project":project.get("name",""),"workflowCount":len(project.get("workflows",{}))})
            workflows = {}
            for key, rel in project["workflows"].items():
                workflows[key] = json.loads(project_file(root, rel).read_text(encoding="utf-8"))
            result = {"project": project, "root": str(root), "workflows": workflows}
        elif method == "project.signature":
            root = Path(params["root"]).expanduser().resolve()
            project_path = (root / "project.json").resolve()
            project_path.relative_to(root)
            project, loaded_root = load_project(project_path)
            if loaded_root != root:
                raise ValueError("Project root changed while checking for external edits.")
            digest = hashlib.sha256()
            digest.update(project_path.read_bytes())
            for name, relative in sorted(project["workflows"].items()):
                workflow_path = project_file(root, relative)
                digest.update(name.encode("utf-8"))
                digest.update(b"\0")
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(workflow_path.read_bytes())
            result = {"sha256": digest.hexdigest()}
        elif method == "project.live_draft.read":
            root=Path(params["root"]).expanduser().resolve()
            project_path=(root/"project.json").resolve();project_path.relative_to(root)
            project,loaded_root=load_project(project_path)
            if loaded_root!=root: raise ValueError("Project root changed while reading an MCP draft.")
            draft_path=(root/".openrpa"/"mcp-live-draft.json").resolve();draft_path.relative_to(root)
            try: raw=draft_path.read_bytes()
            except FileNotFoundError: result={"draft":None}
            else:
                if len(raw)>10_000_000: raise ValueError("MCP live draft exceeds 10 MB.")
                payload=json.loads(raw.decode("utf-8"))
                if not isinstance(payload,dict) or payload.get("format")!="openrpa.live-workflow-draft" or payload.get("formatVersion")!=1 or not isinstance(payload.get("workflow"),dict):
                    raise ValueError("MCP live draft has an unsupported format.")
                name=payload.get("name")
                if not isinstance(name,str) or not name or payload["workflow"].get("name")!=name:
                    raise ValueError("MCP live draft has an invalid workflow identity.")
                problems=validate_workflow(payload["workflow"],set(project["workflows"])|{name})
                workflows={key:json.loads(project_file(root,relative).read_text(encoding="utf-8")) for key,relative in project["workflows"].items()}
                workflows[name]=payload["workflow"]
                problems.extend(validate_workflow_bindings(workflows))
                if problems: raise ValueError(f"MCP live draft failed validation: {problems[0]['message']}")
                result={"draft":payload}
        elif method == "project.live_draft.clear":
            root=Path(params["root"]).expanduser().resolve()
            project_path=(root/"project.json").resolve();project_path.relative_to(root)
            _,loaded_root=load_project(project_path)
            if loaded_root!=root: raise ValueError("Project root changed while clearing an MCP draft.")
            draft_path=(root/".openrpa"/"mcp-live-draft.json").resolve();draft_path.relative_to(root)
            try: current=json.loads(draft_path.read_text(encoding="utf-8"))
            except FileNotFoundError: result={"cleared":False}
            else:
                if params.get("draftId") is not None and params["draftId"]!=current.get("draftId"):
                    result={"cleared":False,"reason":"draft-changed"}
                else:
                    draft_path.unlink(missing_ok=True);result={"cleared":True}
        elif method == "project.create":
            root = Path(params["path"]).expanduser().resolve()
            root.mkdir(parents=True, exist_ok=True)
            project = {"format": "openrpa.project", "formatVersion": 1, "name": params.get("name", "Untitled Project"), "main": "Main", "workflows": {"Main": "workflows/main.workflow.json"}}
            wf_path = project_file(root, project["workflows"]["Main"])
            wf_path.parent.mkdir(parents=True, exist_ok=True)
            workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Main", "variables": [], "arguments": [], "activities": []}
            atomic_json(wf_path, workflow)
            atomic_json(root / "project.json", project)
            publish_active_project(root)
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
            if params.get("allowDestructive") is True: history.audit("permission.granted", {"runId":run_id,"permission":"destructive","source":"studio-run-confirmation"})
            options = RunOptions(allow_network=bool(params.get("allowNetwork", False)), allow_desktop=bool(params.get("allowDesktop", False)), allow_destructive=bool(params.get("allowDestructive",False)), cancel=cancel_event.is_set, event=record_event, audit=history.audit,debugger=debugger,api_connections_path=_api_connections_path())
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
            limit = params.get("limit", 50)
            runs = [{**item, "source": "Studio"} for item in history.list_runs(limit)]
            runs.extend(_mcp_runs(limit))
            runs.sort(key=lambda item: item.get("startedAt", ""), reverse=True)
            result = {"runs": runs[:max(1, min(int(limit), 200))]}
        elif method == "jobs.history":
            root = read_active_project()
            limit = params.get("limit", 100)
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
                raise ValueError("limit must be an integer between 1 and 200")
            result = {"jobs": read_jobs(_mcp_job_queue_path(root), str(root), limit) if root else []}
        elif method == "jobs.cancel":
            root = read_active_project()
            job_id = params.get("jobId")
            if root is None or not isinstance(job_id, str) or len(job_id) != 36:
                raise ValueError("A valid job ID and open Studio project are required")
            record = request_job_cancel(_mcp_job_queue_path(root), str(root), job_id)
            if record is None:
                raise ValueError("The job does not exist for the active Studio project")
            history.audit("job.cancel_requested_from_studio", {"jobId": job_id, "status": record["status"]})
            result = {"job": record}
        elif method == "run.get":
            run_id = str(params.get("runId", ""))
            record = history.get_run(run_id)
            if record is not None:
                record["source"] = "Studio"
            else:
                record = _mcp_run(run_id)
            result = {"run": record}
        elif method == "run.export":
            run_id = params.get("runId")
            destination = params.get("destination")
            if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 128:
                raise ValueError("A valid run ID is required for evidence export")
            if not isinstance(destination, str) or not destination.strip():
                raise ValueError("A destination file is required for evidence export")
            record = history.get_run(run_id)
            if record is None:
                record = _mcp_run(run_id)
            if record is None:
                raise ValueError("The selected run no longer exists in durable history")
            envelope = {"format": "openrpa.run-evidence", "formatVersion": 1, "run": record}
            serialized = json.dumps(envelope, ensure_ascii=False, indent=2) + "\n"
            digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            atomic_json(Path(destination).expanduser(), envelope)
            history.audit("run.export", {"runId": run_id, "sha256": digest, "bytes": len(serialized.encode("utf-8"))})
            result = {"sha256": digest, "bytes": len(serialized.encode("utf-8"))}
        elif method == "audit.history":
            result = {"events": history.list_audit(params.get("limit", 200))}
        elif method == "activity.catalog":
            result = ACTIVITY_CATALOG
        elif method == "adapter.status":
            from .browser_runtime import status as browser_runtime_status
            browser = browser_runtime_status()
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
            desktop_recorder_status_value = desktop_recorder_status()
            try:
                from .credentials import get_safe_keyring
                get_safe_keyring()
                vault={"available":True,"reason":None}
            except Exception as exc:
                vault={"available":False,"reason":str(exc)}
            ocr={"available":False,"reason":"Tesseract is not installed or is not on PATH"}
            try:
                from PIL import Image as _PillowImage
                ocr.update({"imageDecoder":"Pillow","imageDecoderVersion":getattr(_PillowImage,"__version__","unknown")})
            except ImportError:
                ocr={"available":False,"reason":"Optional Pillow OCR dependency is not installed"}
            executable=shutil.which("tesseract")
            if executable and ocr.get("imageDecoder"):
                try:
                    version=subprocess.run([executable,"--version"],capture_output=True,text=True,timeout=3,check=False,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                    if version.returncode==0:ocr.update({"available":True,"reason":None,"engine":"Tesseract","version":(version.stdout.splitlines() or [""])[0][:120]})
                    else:ocr.update({"available":False,"reason":"Tesseract was found but its runtime probe failed"})
                except Exception as exc:ocr.update({"available":False,"reason":f"Tesseract runtime probe failed: {type(exc).__name__}"})
            result = {"browser": browser, "desktop": desktop, "accessibility": accessibility,
                      "desktopRecorder": desktop_recorder_status_value,"credentialVault":vault,"ocr":ocr}
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
        elif method == "desktop.inspect.record.start":
            if params.get("allowDesktop") is not True:
                raise ValueError("Desktop recording requires explicit desktop permission in the Studio toolbar")
            record_keyboard=params.get("recordKeyboard",sys.platform=="win32")
            result=desktop_recorder.start(str(params.get("windowTitle","")),params.get("processId"),record_keyboard)
            history.audit("desktop.recorder_start",{"processId":result["processId"],"targetScoped":True,"keyboardCapture":bool(result.get("recordKeyboard",False)),"mode":result.get("mode")})
        elif method == "desktop.inspect.record.stop":
            result=desktop_recorder.stop()
            history.audit("desktop.recorder_stop",{"processId":result["processId"],"eventCount":len(result["events"]),"ignoredClicks":result["ignoredClicks"],"ignoredKeys":result["ignoredKeys"],"truncated":result["truncated"],"mode":result.get("mode")})
        elif method == "browser.inspect.open":
            if params.get("allowNetwork") is not True:
                raise ValueError("Browser inspection requires explicit network permission in the Studio toolbar")
            opened=browser_inspector.open(str(params.get("url","")),str(params.get("browserType","chromium")),str(params.get("channel","chromium")),str(params.get("executablePath","")))
            from urllib.parse import urlsplit
            history.audit("browser.inspector_open",{"host":urlsplit(opened["url"]).hostname,"networkPermission":True})
            result=opened
        elif method == "browser.inspect.probe":
            from .browser_runtime import probe as probe_browser_runtime
            probed=probe_browser_runtime(str(params.get("browserType","chromium")),str(params.get("channel","chromium")),str(params.get("executablePath","")))
            history.audit("browser.runtime_probe",{"browserType":probed["browserType"],"channel":probed["channel"],"success":True,"networkUsed":False})
            result=probed
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
        elif method == "api.connections.list":
            profiles=api_connections.list_profiles(_api_connections_path())
            for profile in profiles:
                profile["credentialStored"]=api_connections.has_oauth_tokens(profile["id"]) if profile["authType"]=="oauth_authorization_code" else api_connections.has_secret(profile["id"]) if profile["authType"]!="none" else False
                profile["clientSecretStored"]=api_connections.has_secret(profile["id"]) if profile["authType"]=="oauth_authorization_code" else False
            result={"profiles":profiles}
        elif method == "api.connections.save":
            store_path=_api_connections_path()
            proposed=params.get("profile")
            previous=None
            if isinstance(proposed,dict) and proposed.get("id"):
                try:previous=api_connections.get_profile(store_path,str(proposed["id"]))
                except ValueError:pass
            profile=api_connections.save_profile(store_path,proposed)
            secret=params.get("secret")
            auth_material_changed=previous is not None and any(previous.get(key)!=profile.get(key) for key in ("authType","baseUrl","tokenUrl","authorizationUrl","clientId","clientAuthMethod","scope","audience"))
            if previous and previous["authType"]!=profile["authType"]:
                # Never reinterpret a credential or OAuth grant under a different API authentication mode.
                api_connections.delete_secret(profile["id"])
            if auth_material_changed:
                api_connections.delete_oauth_tokens(profile["id"])
                if previous and any(previous.get(key)!=profile.get(key) for key in ("clientId","clientAuthMethod")):
                    api_connections.delete_secret(profile["id"])
            if secret is not None and profile["authType"]=="oauth_authorization_code":api_connections.delete_oauth_tokens(profile["id"])
            if secret is not None:api_connections.store_secret(profile["id"],secret)
            history.audit("api.connection.save",{"profileId":profile["id"],"authType":profile["authType"],"credentialProvided":secret is not None,"authorizationReset":auth_material_changed})
            credential_stored=api_connections.has_oauth_tokens(profile["id"]) if profile["authType"]=="oauth_authorization_code" else api_connections.has_secret(profile["id"]) if profile["authType"]!="none" else False
            result={"profile":profile,"credentialStored":credential_stored,"clientSecretStored":api_connections.has_secret(profile["id"]) if profile["authType"]=="oauth_authorization_code" else False}
        elif method == "api.connections.delete":
            profile_id=params.get("profileId")
            api_connections.delete_profile(_api_connections_path(),profile_id)
            history.audit("api.connection.delete",{"profileId":profile_id})
            result={"deleted":True,"profileId":profile_id}
        elif method == "api.connections.test":
            if params.get("allowNetwork") is not True:raise ValueError("Testing an API connection requires enabling Allow network")
            profile=api_connections.get_profile(_api_connections_path(),str(params.get("profileId","")))
            path=str(params.get("path","/")).strip()
            from urllib.parse import urljoin,urlsplit
            if not path.startswith("/") or path.startswith("//") or ".." in path.replace("\\","/").split("/"):
                raise ValueError("Connection test path must start with / and remain inside the configured API host")
            url=urljoin(profile["baseUrl"].rstrip("/")+"/",path.lstrip("/"))
            parts=urlsplit(url);base=urlsplit(profile["baseUrl"])
            if (parts.scheme,parts.hostname,parts.port)!=(base.scheme,base.hostname,base.port):raise ValueError("Connection test cannot change the API host")
            headers=dict(profile["headers"])
            from .network import request as restricted_http_request
            if profile["authType"] in {"bearer","api_key_header","oauth_client_credentials"}:
                secret=api_connections.read_secret(profile["id"])
                if profile["authType"]=="bearer":headers["Authorization"]="Bearer "+secret
                elif profile["authType"]=="api_key_header":headers[profile["apiKeyHeader"]]=secret
                else:
                    token,expires=api_connections.request_oauth_token(profile,secret,restricted_http_request,20)
                    headers["Authorization"]="Bearer "+token
                    history.audit("api.oauth.token",{"connectionId":profile["id"],"host":urlsplit(profile["tokenUrl"]).hostname})
            elif profile["authType"]=="oauth_authorization_code":
                secret=api_connections.read_secret(profile["id"]) if profile["clientAuthMethod"]!="none" else ""
                token=api_connections.authorization_code_access_token(profile,restricted_http_request,secret,20)
                headers["Authorization"]="Bearer "+token
                history.audit("api.oauth.token",{"connectionId":profile["id"],"host":urlsplit(profile["tokenUrl"]).hostname,"grant":"authorization_code"})
            response=restricted_http_request(url,"GET",headers,None,10,65536)
            history.audit("api.connection.test",{"profileId":profile["id"],"host":parts.hostname,"status":response.get("status")})
            result={"status":response.get("status"),"ok":200<=int(response.get("status",0))<300,"contentType":next((value for key,value in response.get("headers",{}).items() if key.lower()=="content-type"),"")[:200]}
        elif method == "api.connections.discover":
            if params.get("allowNetwork") is not True:raise ValueError("Discovering API response fields requires enabling Allow network")
            profile=api_connections.get_profile(_api_connections_path(),str(params.get("profileId","")))
            path=params.get("path","/")
            if not isinstance(path,str) or len(path)>8192 or not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path or ".." in path.replace("\\","/").split("/"):
                raise ValueError("API discovery path must start with / and cannot contain a query, fragment, or traversal; configure query parameters separately")
            query=params.get("query",{})
            if not isinstance(query,dict) or len(query)>100:
                raise ValueError("API discovery query must be an object with at most 100 parameters")
            from urllib.parse import urlencode,urljoin,urlsplit
            query_values=[]
            for key,value in query.items():
                if not isinstance(key,str) or not key or len(key)>256 or isinstance(value,(dict,list)) or value is None:
                    raise ValueError("API discovery query values must be named scalar values")
                if any(term in key.casefold() for term in ("token","secret","password","credential","authorization","cookie","api-key","api_key","apikey")):
                    raise ValueError("Credential-like query parameters are blocked; configure authentication on the saved API connection")
                if isinstance(value,str) and ("{{" in value or "}}" in value):
                    raise ValueError("Replace workflow expressions with concrete values before discovering response fields")
                query_values.append((key,str(value)))
            url=urljoin(profile["baseUrl"].rstrip("/")+"/",path.lstrip("/"))
            parts=urlsplit(url);base=urlsplit(profile["baseUrl"])
            if (parts.scheme,parts.hostname,parts.port)!=(base.scheme,base.hostname,base.port):raise ValueError("API discovery cannot change the saved connection host")
            if query_values:
                from urllib.parse import parse_qsl,urlunsplit
                merged=parse_qsl(parts.query,keep_blank_values=True)+query_values
                url=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(merged),""))
            headers=dict(profile["headers"])
            from .network import request as restricted_http_request
            if profile["authType"] in {"bearer","api_key_header","oauth_client_credentials"}:
                secret=api_connections.read_secret(profile["id"])
                if profile["authType"]=="bearer":headers["Authorization"]="Bearer "+secret
                elif profile["authType"]=="api_key_header":headers[profile["apiKeyHeader"]]=secret
                else:
                    token,expires=api_connections.request_oauth_token(profile,secret,restricted_http_request,10)
                    headers["Authorization"]="Bearer "+token
                    history.audit("api.oauth.token",{"connectionId":profile["id"],"host":urlsplit(profile["tokenUrl"]).hostname})
            elif profile["authType"]=="oauth_authorization_code":
                secret=api_connections.read_secret(profile["id"]) if profile["clientAuthMethod"]!="none" else ""
                token=api_connections.authorization_code_access_token(profile,restricted_http_request,secret,10)
                headers["Authorization"]="Bearer "+token
                history.audit("api.oauth.token",{"connectionId":profile["id"],"host":urlsplit(profile["tokenUrl"]).hostname,"grant":"authorization_code"})
            response=restricted_http_request(url,"GET",headers,None,10,2_000_000)
            status=int(response.get("status",0));content_type=next((value for key,value in response.get("headers",{}).items() if key.lower()=="content-type"),"")[:200]
            result={"status":status,"ok":200<=status<300,"contentType":content_type,"candidates":[]}
            if result["ok"]:
                body=response.get("body","")
                if isinstance(body,str):
                    try:
                        from .api_discovery import discover_response
                        result.update(discover_response(body))
                    except ValueError as exc:
                        result["discoveryError"]=str(exc)
            history.audit("api.response.discover",{"profileId":profile["id"],"host":parts.hostname,"status":status,"candidateCount":len(result.get("candidates",[]))})
        elif method == "api.connections.authorize":
            if params.get("allowNetwork") is not True:raise ValueError("Authorizing an API connection requires enabling Allow network")
            profile=api_connections.get_profile(_api_connections_path(),str(params.get("profileId","")))
            if profile["authType"]!="oauth_authorization_code":raise ValueError("This API connection does not use OAuth authorization code")
            secret=api_connections.read_secret(profile["id"]) if profile["clientAuthMethod"]!="none" else ""
            from .network import request as restricted_http_request
            tokens=api_connections.authorize_with_system_browser(profile,restricted_http_request,secret,180,cancel=ai_cancel)
            api_connections.store_oauth_tokens(profile["id"],tokens)
            history.audit("api.oauth.authorize",{"connectionId":profile["id"],"authorizationHost":urlsplit(profile["authorizationUrl"]).hostname,"tokenHost":urlsplit(profile["tokenUrl"]).hostname,"granted":True})
            result={"authorized":True,"credentialStored":True}
        elif method == "api.connections.authorize.cancel":
            profile_id=str(params.get("profileId",""))
            with api_auth_lock:cancellation=api_auth_cancellations.get(profile_id)
            if cancellation is not None:cancellation.set()
            result={"cancelled":cancellation is not None}
        elif method == "openapi.fetch":
            if params.get("allowNetwork") is not True:raise ValueError("Fetching an OpenAPI URL requires enabling Allow network")
            from urllib.parse import urlsplit
            from .network import request as restricted_http_request
            url=params.get("url")
            if not isinstance(url,str) or not url.strip() or len(url)>2048:raise ValueError("OpenAPI URL must contain 1–2,048 characters")
            url=url.strip();parts=urlsplit(url)
            if parts.scheme!="https" or not parts.hostname or parts.username is not None or parts.password is not None or parts.fragment:
                raise ValueError("OpenAPI documents must use an absolute HTTPS URL without embedded credentials or a fragment")
            host=parts.hostname.lower()
            history.audit("openapi.fetch",{"host":host,"status":"started"})
            response=restricted_http_request(url,"GET",{"Accept":"application/json, application/yaml, text/yaml, text/plain;q=0.9"},None,15,2_000_000)
            status=int(response.get("status",0));body=response.get("body","")
            if status<200 or status>=300 or response.get("redirectBlocked"):
                raise ValueError(f"OpenAPI document fetch failed with HTTP {status}; redirects are not followed")
            if not isinstance(body,str) or not body.strip():raise ValueError("OpenAPI document response was empty")
            size=len(body.encode("utf-8"))
            if size>2_000_000:raise ValueError("OpenAPI document response exceeds the 2 MB limit")
            history.audit("openapi.fetch",{"host":host,"status":status,"bytes":size})
            result={"text":body}
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
            models=ai_providers.models(provider,params.get("baseUrl"),params.get("credentialService"),params.get("credentialUsername"),params.get("credentialMode","bearer"),params.get("credentialHeader","api-key"))
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
            # API profiles contain only non-secret configuration in this local store.
            # Send the smallest useful allowlisted metadata to help the model select
            # an existing connection; the OS-vault credential is never read here.
            saved_api_profiles=api_connections.list_profiles(_api_connections_path(),check_public_destinations=False)
            ai_api_profiles=[{key:profile[key] for key in ("id","name","baseUrl","authType")}
                for profile in saved_api_profiles]
            execution_model=str(params.get("executionModel","sequence"))
            history.audit("ai.draft",{"provider":provider,"model":model[:200],"workflowModel":execution_model,"local":bool(ai_providers.PROVIDERS.get(provider,{}).get("local"))})
            compatibility_warnings=[]
            def record_ai_compatibility_fallback(message: str) -> None:
                compatibility_warnings.append(message)
                history.audit("ai.structured_output_fallback",{"provider":provider,"model":model[:200]})
            draft=ai_providers.draft(provider,model,params.get("prompt",""),types,params.get("baseUrl"),
                params.get("credentialService"),params.get("credentialUsername"),execution_model,ai_cancel,
                on_compatibility_fallback=record_ai_compatibility_fallback,
                api_connections=ai_api_profiles,credential_mode=params.get("credentialMode","bearer"),
                credential_header=params.get("credentialHeader","api-key"),activity_catalog=ACTIVITY_CATALOG)
            if ai_cancel is not None and ai_cancel.is_set():
                raise ai_providers.RequestCancelled("Provider request was cancelled")
            usage=draft.pop("_openrpa_usage",None) if isinstance(draft,dict) else None
            payload_key={"sequence":"activities","flowchart":"flowchart","state_machine":"stateMachine"}.get(execution_model)
            if payload_key is None:raise ValueError("AI workflow model must be sequence, flowchart, or state_machine")
            if not isinstance(draft,dict) or set(draft)-{"explanation",payload_key}:
                raise ValueError(f"Model output must contain explanation and {payload_key} only")
            payload=draft.get(payload_key)
            activities=payload if execution_model=="sequence" else ([node.get("activity") for node in payload.get("nodes",[]) if isinstance(node,dict) and node.get("kind")=="action"] if execution_model=="flowchart" and isinstance(payload,dict) else ([state.get("activities",[]) for state in payload.get("states",[]) if isinstance(state,dict)] if execution_model=="state_machine" and isinstance(payload,dict) else []))
            if execution_model == "flowchart":
                compatibility_warnings.extend(_repair_flowchart_node_id_collisions(payload))
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
            problems.extend(_api_request_connection_problems(workflow,saved_api_profiles))
            if isinstance(usage,dict):
                history.audit("ai.draft.usage",{"provider":provider,"model":model[:200],**usage})
            result={"explanation":str(draft.get("explanation",""))[:4000],"workflow":workflow,"valid":not problems,"problems":problems,"model":model,"provider":provider,"warnings":compatibility_warnings,"usage":usage}
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
            if request.get("method") not in {"ai.draft","api.connections.authorize"}:
                handle(request)
                continue
            params=request.get("params",{})
            is_ai=request.get("method")=="ai.draft"
            operation_id=params.get("draftId",str(request.get("id",""))) if is_ai else str(params.get("profileId",""))
            if not isinstance(operation_id,str) or not operation_id or len(operation_id)>128:
                raise ValueError("AI draft or API authorization requires a valid identifier")
            cancellation=threading.Event()
            lock=ai_draft_lock if is_ai else api_auth_lock
            active=ai_draft_cancellations if is_ai else api_auth_cancellations
            with lock:
                if operation_id in active:
                    raise ValueError("This AI draft or API authorization is already active")
                active[operation_id]=cancellation

            def finish_operation(current_request: dict[str, Any]=request, current_id: str=operation_id,
                                 current_cancel: threading.Event=cancellation, current_ai: bool=is_ai) -> None:
                try:
                    handle(current_request,current_cancel)
                finally:
                    current_lock=ai_draft_lock if current_ai else api_auth_lock
                    current_active=ai_draft_cancellations if current_ai else api_auth_cancellations
                    with current_lock:
                        if current_active.get(current_id) is current_cancel:current_active.pop(current_id,None)

            threading.Thread(target=finish_operation,name="openrpa-ai-draft" if is_ai else "openrpa-api-oauth",daemon=True).start()
        except Exception as exc:
            send({"id":request.get("id") if isinstance(request,dict) else None,
                  "error": {"message": str(exc), "type": type(exc).__name__}})


if __name__ == "__main__":
    main()
