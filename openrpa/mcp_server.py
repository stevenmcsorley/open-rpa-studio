"""Local stdio Model Context Protocol server for a single Open RPA project.

The project root is fixed at process startup. This module deliberately exposes
no network transport and never accepts file paths from an MCP client.
"""
from __future__ import annotations

import json
import sys
import os
import hashlib
import re
import threading
import tempfile
from . import __version__
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .engine import RunOptions, run_project
from .history import RunHistory
from .model import load_project, validate_workflow, validate_workflow_bindings
from .activity_catalog import ACTIVITY_CATALOG

SUPPORTED_PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MAX_FRAME_BYTES = 4_000_000
MAX_RESULT_BYTES = 1_000_000


def _history_path(project_root: Path) -> Path:
    project_key = hashlib.sha256(str(project_root.resolve()).encode("utf-8")).hexdigest()[:16]
    configured = os.environ.get("OPENRPA_DATA_DIR")
    if configured:
        return Path(configured).expanduser() / f"mcp-run-history-{project_key}.sqlite3"
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "OpenRPAStudio" / f"mcp-run-history-{project_key}.sqlite3"


def _walk_activities(workflow: dict[str, Any]):
    def walk(items):
        for activity in items if isinstance(items, list) else []:
            if not isinstance(activity, dict):
                continue
            yield activity
            for branch in ("then", "else", "body", "catch", "finally", "default"):
                yield from walk(activity.get(branch))
            for case in activity.get("cases", []):
                if isinstance(case, dict):
                    yield from walk(case.get("activities"))
    yield from walk(workflow.get("activities"))
    if workflow.get("executionModel") == "flowchart":
        for node in workflow.get("flowchart", {}).get("nodes", []):
            if isinstance(node, dict) and node.get("kind") == "action":
                activity = node.get("activity")
                if isinstance(activity, dict):
                    yield activity
                    yield from walk([activity])
    if workflow.get("executionModel") == "state_machine":
        for state in workflow.get("stateMachine", {}).get("states", []):
            if isinstance(state, dict):
                yield from walk(state.get("activities"))


class ProjectMCPServer:
    def __init__(self, project_path: str, *, allow_run: bool = False,
                 allow_edit: bool = False,
                 allow_network: bool = False, allow_desktop: bool = False,
                 allow_credentials: bool = False,
                 allow_destructive: bool = False):
        source=Path(project_path).expanduser().resolve()
        if source.is_dir(): source=source/"project.json"
        self.project_path = str(source)
        self.allow_run = allow_run
        self.allow_edit = allow_edit
        self.allow_network = allow_network
        self.allow_desktop = allow_desktop
        self.allow_credentials = allow_credentials
        self.allow_destructive = allow_destructive
        self.project, self.root = load_project(self.project_path)
        self._history_file = _history_path(self.root)
        self._run_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._history: RunHistory | None = None

    def _get_history(self) -> RunHistory:
        with self._history_lock:
            if self._history is None:
                self._history = RunHistory(self._history_file)
            return self._history

    def _workflow(self, name: str) -> dict[str, Any]:
        if not isinstance(name, str) or name not in self.project["workflows"]:
            raise ValueError(f"Unknown workflow name: {name!r}")
        relative = self.project["workflows"][name]
        path = (self.root / relative).resolve()
        path.relative_to(self.root)
        return json.loads(path.read_text(encoding="utf-8"))

    def _workflow_file(self, name: str) -> Path:
        if not isinstance(name, str) or name not in self.project["workflows"]:
            raise ValueError(f"Unknown workflow name: {name!r}")
        path = (self.root / self.project["workflows"][name]).resolve()
        path.relative_to(self.root)
        return path

    def _reachable_types(self, name: str) -> set[str]:
        seen: set[str] = set()
        kinds: set[str] = set()
        def visit(workflow_name: str) -> None:
            if workflow_name in seen:
                return
            seen.add(workflow_name)
            workflow = self._workflow(workflow_name)
            for activity in _walk_activities(workflow):
                kind = activity.get("type", "")
                kinds.add(kind)
                if kind == "invoke_workflow" and isinstance(activity.get("workflow"), str):
                    visit(activity["workflow"])
        visit(name)
        return kinds

    def _tools(self) -> list[dict[str, Any]]:
        tools = [
            {"name": "openrpa_project_info", "description": "Get the fixed project name, workflow names, current project manifest SHA-256, and available MCP permissions. Does not return workflow contents or root paths.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
            {"name": "openrpa_list_workflows", "description": "List workflow names and execution models in the fixed project.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
            {"name": "openrpa_activity_catalog", "description": "List native activity types, descriptions, configuration defaults, and required permission grants available to build workflows. Metadata only; it never executes activities.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
            {"name": "openrpa_read_workflow", "description": "Read one workflow definition. Workflow literals may contain private user data; the MCP client will receive them.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
            {"name": "openrpa_validate_project", "description": "Validate all saved workflows and cross-workflow bindings without executing them.", "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
            {"name": "openrpa_plan_workflow", "description": "Summarize activity types and required network, desktop, credential, or destructive permissions without executing the workflow.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
            {"name": "openrpa_list_run_history", "description": "List recent MCP workflow run statuses and identifiers from the durable local MCP run ledger; runtime variable values are excluded.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}, "additionalProperties": False}, "annotations": {"readOnlyHint": True}},
        ]
        if self.allow_edit:
            tools.append({"name": "openrpa_create_workflow", "description": "Create a new reusable workflow after schema and project-binding validation. Requires the current project.json SHA-256 from openrpa_project_info; editing is unavailable unless enabled when the server starts.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 100}, "expectedProjectSha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "workflow": {"type": "object", "additionalProperties": True}}, "required": ["name", "expectedProjectSha256", "workflow"], "additionalProperties": False}, "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}})
            tools.append({"name": "openrpa_update_workflow", "description": "Replace one declared workflow after validating it. Requires the expected SHA-256 from openrpa_read_workflow; editing is unavailable unless enabled when the server starts.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "expectedSha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "workflow": {"type": "object", "additionalProperties": True}}, "required": ["name", "expectedSha256", "workflow"], "additionalProperties": False}, "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}})
        if self.allow_run:
            tools.append({"name": "openrpa_run_workflow", "description": "Execute a saved workflow in the fixed project. Network, desktop, credentials and destructive activities require separate startup opt-ins.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "inputs": {"type": "object", "additionalProperties": True}}, "required": ["name"], "additionalProperties": False}, "annotations": {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}})
        return tools

    def _create_workflow(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_edit:
            raise PermissionError("Workflow editing is disabled. Restart the MCP server with --allow-edit after reviewing the project and client.")
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Workflow creation is blocked while a workflow run or edit is active for this project.")
        created_file: Path | None = None
        try:
            name=args.get("name")
            proposed=args.get("workflow")
            expected=args.get("expectedProjectSha256")
            if not isinstance(name,str) or not name or len(name)>100 or name.strip()!=name or any(ord(char)<32 for char in name) or "/" in name or "\\" in name:
                raise ValueError("Workflow name must be 1–100 characters, trimmed, and contain no control characters or path separators.")
            if not isinstance(proposed,dict):
                raise ValueError("workflow must be an object")
            encoded_input=json.dumps(proposed,ensure_ascii=False,allow_nan=False)
            if len(encoded_input.encode("utf-8"))>10_000_000:
                raise ValueError("Workflow exceeds 10 MB")
            project_file=Path(self.project_path)
            if not isinstance(expected,str) or not re.fullmatch(r"[a-f0-9]{64}",expected):
                raise ValueError("expectedProjectSha256 must be the current project.json SHA-256 from openrpa_project_info.")
            if hashlib.sha256(project_file.read_bytes()).hexdigest()!=expected:
                raise ValueError("Project changed since it was read. Refresh project info and reapply the create operation.")
            current_project,current_root=load_project(project_file)
            if current_root!=self.root:
                raise ValueError("Project root changed; restart the MCP server for the current project.")
            self.project=current_project
            workflows=current_project["workflows"]
            if any(existing.casefold()==name.casefold() for existing in workflows):
                raise ValueError(f"A workflow named {name!r} already exists.")
            slug=re.sub(r"[^a-z0-9]+","-",name.casefold()).strip("-")
            if not slug:
                slug=f"workflow-{hashlib.sha256(name.encode('utf-8')).hexdigest()[:12]}"
            relative=f"workflows/{slug}.workflow.json"
            final_path=(self.root/relative).resolve()
            try: final_path.relative_to(self.root)
            except ValueError as exc: raise ValueError("Generated workflow path escapes the project root.") from exc
            if relative in workflows.values() or final_path.exists():
                raise ValueError(f"A workflow file for {name!r} already exists; choose a distinct workflow name.")

            candidate=dict(self.project)
            candidate["workflows"]={**workflows,name:relative}
            proposed=dict(proposed)
            proposed["name"]=name
            problems=validate_workflow(proposed,set(candidate["workflows"]))
            if not problems:
                combined={key:self._workflow(key) for key in workflows}
                combined[name]=proposed
                problems.extend(validate_workflow_bindings(combined))
            if problems:
                return {"created":False,"problems":problems}
            data=(json.dumps(proposed,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")
            manifest_data=(json.dumps(candidate,ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")
            if len(manifest_data)>1_000_000:
                raise ValueError("Updated project manifest would exceed 1 MB")
            final_path.parent.mkdir(parents=True,exist_ok=True)
            descriptor,temporary=tempfile.mkstemp(prefix=".openrpa-create-",suffix=".tmp",dir=final_path.parent)
            try:
                with os.fdopen(descriptor,"wb") as stream:
                    stream.write(data);stream.flush();os.fsync(stream.fileno())
                try:
                    template=next((self.root/path for path in workflows.values() if (self.root/path).is_file()),None)
                    if template is not None: os.chmod(temporary,template.stat().st_mode)
                except OSError:
                    pass
                os.replace(temporary,final_path)
                created_file=final_path
            finally:
                if os.path.exists(temporary): os.unlink(temporary)

            descriptor,temporary=tempfile.mkstemp(prefix=".openrpa-project-",suffix=".tmp",dir=self.root)
            try:
                with os.fdopen(descriptor,"wb") as stream:
                    stream.write(manifest_data);stream.flush();os.fsync(stream.fileno())
                try: os.chmod(temporary,project_file.stat().st_mode)
                except OSError: pass
                if hashlib.sha256(project_file.read_bytes()).hexdigest()!=expected:
                    raise ValueError("Project changed during workflow creation. No project manifest update was written; inspect the new workflow file before retrying.")
                os.replace(temporary,project_file)
            finally:
                if os.path.exists(temporary): os.unlink(temporary)

            created_file=None
            self.project=candidate
            workflow_digest=hashlib.sha256(data).hexdigest()
            manifest_digest=hashlib.sha256(manifest_data).hexdigest()
            history_warning=None
            try: self._get_history().audit("workflow.created",{"workflow":name,"workflowSha256":workflow_digest,"source":"mcp"})
            except Exception as exc: history_warning=f"Workflow was created but its audit event could not be saved: {type(exc).__name__}: {exc}"[:512]
            result={"created":True,"workflow":name,"workflowPath":relative,"workflowSha256":workflow_digest,"projectSha256":manifest_digest,"validated":True}
            if history_warning: result["historyWarning"]=history_warning
            return result
        except Exception:
            if created_file is not None:
                try: created_file.unlink(missing_ok=True)
                except OSError: pass
            raise
        finally:
            self._run_lock.release()

    def _update_workflow(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.allow_edit:
            raise PermissionError("Workflow editing is disabled. Restart the MCP server with --allow-edit after reviewing the project and client.")
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Workflow editing is blocked while a workflow run is active for this project.")
        try:
            workflow_name = args.get("name")
            path = self._workflow_file(workflow_name)
            proposed = args.get("workflow")
            expected = args.get("expectedSha256")
            if not isinstance(proposed, dict):
                raise ValueError("workflow must be an object")
            encoded_input = json.dumps(proposed, ensure_ascii=False, allow_nan=False)
            if len(encoded_input.encode("utf-8")) > 10_000_000:
                raise ValueError("Workflow exceeds 10 MB")
            problems = validate_workflow(proposed, set(self.project["workflows"]))
            if not problems:
                workflows = {key: self._workflow(key) for key in self.project["workflows"]}
                workflows[workflow_name] = proposed
                problems.extend(validate_workflow_bindings(workflows))
            if problems:
                return {"updated": False, "problems": problems}
            current = path.read_bytes()
            if not isinstance(expected, str) or hashlib.sha256(current).hexdigest() != expected:
                raise ValueError("Workflow changed since it was read. Read it again and reapply the edit against the new SHA-256.")
            data = (json.dumps(proposed, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
            descriptor, temporary = tempfile.mkstemp(prefix=".openrpa-mcp-", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if path.exists():
                    try:
                        os.chmod(temporary, path.stat().st_mode)
                    except OSError:
                        pass
                if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError("Workflow changed during update. No edit was written; read it again.")
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            digest = hashlib.sha256(data).hexdigest()
            self._get_history().audit("workflow.updated", {"workflow": workflow_name, "workflowSha256": digest, "source": "mcp"})
            return {"updated": True, "workflow": workflow_name, "sha256": digest, "validated": True}
        finally:
            self._run_lock.release()

    def _run_workflow(self, args: dict[str, Any], cancel_event: threading.Event | None) -> dict[str, Any]:
        if not self.allow_run:
            raise PermissionError("Workflow execution is disabled. Restart the MCP server with --allow-run after reviewing the project and client.")
        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("Another MCP project operation is active.")
        try:
            workflow_name = args.get("name")
            workflow = self._workflow(workflow_name)
            types = self._reachable_types(workflow_name)
            if types & {"http_request", "browser_navigate"} and not self.allow_network:
                raise PermissionError("This workflow uses HTTP or browser navigation. Restart with --allow-network only after reviewing its destinations.")
            if any(kind.startswith("desktop_") for kind in types) and not self.allow_desktop:
                raise PermissionError("This workflow controls the desktop. Restart with --allow-desktop only after reviewing its actions.")
            if "credential_get" in types and not self.allow_credentials:
                raise PermissionError("This workflow reads an OS-vault credential. Restart with --allow-credentials only after reviewing its target and data flow.")
            if {"file_delete", "file_move"} & types and not self.allow_destructive:
                raise PermissionError("This workflow contains delete or move activities. Restart with --allow-destructive only after reviewing the affected files.")
            inputs = args.get("inputs", {})
            if not isinstance(inputs, dict) or len(json.dumps(inputs, ensure_ascii=False)) > 100_000:
                raise ValueError("Workflow inputs must be an object no larger than 100 KB.")
            workflow_digest = hashlib.sha256(json.dumps(workflow, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
            history = self._get_history()
            run_id = history.start(str(self.root), str(self.project.get("name", "")), workflow_name, workflow_digest)
            for permitted, label in ((self.allow_network, "network"), (self.allow_desktop, "desktop"), (self.allow_credentials, "credentials"), (self.allow_destructive, "destructive")):
                if permitted:
                    history.audit("permission.granted", {"runId": run_id, "permission": label, "source": "mcp-startup-flag"})
            def record_event(event: dict[str, Any]) -> None:
                durable_event = dict(event)
                if durable_event.get("event") == "debug.paused":
                    durable_event.pop("variables", None)
                    durable_event.pop("editableVariables", None)
                history.event(run_id, durable_event)
                if event.get("event") == "activity-started":
                    history.audit("activity.started", {"runId": run_id, "activityId": event.get("activityId"), "type": event.get("type")})
            try:
                result = run_project(self.project, self.root, workflow_name, inputs=inputs,
                                     options=RunOptions(allow_network=self.allow_network, allow_desktop=self.allow_desktop,
                                                        cancel=cancel_event.is_set if cancel_event else lambda: False,
                                                        event=record_event, audit=history.audit,
                                                        max_log_events=500, max_log_event_chars=4096))
                history.finish(run_id, result.status, {key: getattr(result, key) for key in ("status", "activities", "error")}, result.error)
                output = asdict(result)
                output["runId"] = run_id
                return output
            except Exception as exc:
                history.finish(run_id, "failed", None, {"type": type(exc).__name__, "message": str(exc)[:2000]})
                raise
        finally:
            self._run_lock.release()

    def _call_tool(self, name: str, args: dict[str, Any], cancel_event: threading.Event | None = None) -> Any:
        if name == "openrpa_project_info":
            current_project,current_root=load_project(self.project_path)
            if current_root!=self.root:
                raise ValueError("Project root changed; restart the MCP server for the current project.")
            self.project=current_project
            project_digest=hashlib.sha256(Path(self.project_path).read_bytes()).hexdigest()
            return {"projectName": self.project.get("name", ""), "workflowNames": list(self.project["workflows"]), "projectSha256": project_digest, "permissions": {"edit": self.allow_edit, "run": self.allow_run, "network": self.allow_network, "desktop": self.allow_desktop, "credentials": self.allow_credentials, "destructive": self.allow_destructive}, "transport": "stdio", "projectRootExposed": False}
        if name == "openrpa_list_workflows":
            rows = []
            for workflow_name in self.project["workflows"]:
                workflow = self._workflow(workflow_name)
                rows.append({"name": workflow_name, "executionModel": workflow.get("executionModel", "sequence"), "activityCount": sum(1 for _ in _walk_activities(workflow))})
            return {"workflows": rows}
        if name == "openrpa_activity_catalog":
            activities=[]
            for entry in ACTIVITY_CATALOG:
                kind=entry["type"]
                permissions=[]
                if kind in {"http_request", "browser_navigate"}: permissions.append("network")
                if kind.startswith("desktop_"): permissions.append("desktop")
                if kind == "credential_get": permissions.append("credentials")
                if kind in {"file_delete", "file_move"}: permissions.append("destructive")
                activities.append({**entry, "requiredPermissions": permissions})
            return {"activities": activities}
        if name == "openrpa_read_workflow":
            path = self._workflow_file(args.get("name"))
            raw = path.read_bytes()
            if len(raw) > 10_000_000:
                raise ValueError("Workflow exceeds 10 MB")
            return {"workflow": json.loads(raw.decode("utf-8")), "sha256": hashlib.sha256(raw).hexdigest()}
        if name == "openrpa_update_workflow":
            return self._update_workflow(args)
        if name == "openrpa_create_workflow":
            return self._create_workflow(args)
        if name == "openrpa_validate_project":
            problems = []
            workflows = {}
            for workflow_name in self.project["workflows"]:
                workflow = self._workflow(workflow_name)
                workflows[workflow_name] = workflow
                problems.extend({"workflow": workflow_name, **problem} for problem in validate_workflow(workflow, set(self.project["workflows"])))
            problems.extend({"workflow": "[project]", **problem} for problem in validate_workflow_bindings(workflows))
            return {"valid": not problems, "workflowCount": len(workflows), "problems": problems}
        if name == "openrpa_plan_workflow":
            workflow = self._workflow(args.get("name"))
            kinds_set = self._reachable_types(args.get("name"))
            activities = list(_walk_activities(workflow))
            kinds = sorted(kinds_set)
            return {"workflow": args.get("name"), "activityCount": len(activities), "activityTypes": kinds, "requires": {"network": bool({"http_request", "browser_navigate"} & kinds_set), "desktop": any(kind.startswith("desktop_") for kind in kinds_set), "credentials": "credential_get" in kinds_set, "destructive": bool({"file_delete", "file_move"} & kinds_set)}, "note": "Permission scan includes statically invoked project workflows; expressions and runtime data can still change targets."}
        if name == "openrpa_list_run_history":
            limit = args.get("limit", 20)
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
                raise ValueError("limit must be an integer between 1 and 100")
            history_file = self._history_file
            if self._history is None and not history_file.exists():
                return {"runs": []}
            history = self._get_history()
            columns = ("runId", "projectName", "workflow", "workflowSha256", "status", "startedAt", "endedAt", "error", "recoveryNote")
            return {"runs": [{key: row.get(key) for key in columns} for row in history.list_runs(limit)]}
        if name == "openrpa_run_workflow":
            return self._run_workflow(args, cancel_event)
        raise LookupError(f"Unknown tool: {name}")

    def handle(self, request: Any, cancel_event: threading.Event | None = None) -> dict[str, Any] | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None, "error": {"code": -32600, "message": "Invalid JSON-RPC request"}}
        method = request["method"]
        request_id = request.get("id")
        if request_id is not None and (isinstance(request_id, bool) or not isinstance(request_id, (str, int, float))):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Request id must be a string, number, or null"}}
        if request_id is None:
            if method == "notifications/initialized":
                return None
            return None
        params = request.get("params", {})
        if not isinstance(params, dict):
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "params must be an object"}}
        try:
            if method == "initialize":
                requested = params.get("protocolVersion")
                if requested not in SUPPORTED_PROTOCOLS:
                    raise ValueError(f"Unsupported MCP protocol version; supported versions: {', '.join(SUPPORTED_PROTOCOLS)}")
                result = {"protocolVersion": requested, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "open-rpa-studio", "version": __version__}, "instructions": "This server is bound to one local project. Workflow execution is controlled by startup flags; tools cannot choose arbitrary paths."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self._tools()}
            elif method == "tools/call":
                tool_name = params.get("name")
                args = params.get("arguments", {})
                if not isinstance(args, dict):
                    raise ValueError("Tool arguments must be an object")
                try:
                    value = self._call_tool(tool_name, args, cancel_event)
                    content = [{"type": "text", "text": json.dumps(value, ensure_ascii=False, default=str)}]
                    result = {"content": content, "structuredContent": value, "isError": False}
                except Exception as exc:
                    result = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
            else:
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
            encoded = json.dumps(result, ensure_ascii=False, default=str, allow_nan=False)
            if len(encoded.encode("utf-8")) > MAX_RESULT_BYTES:
                raise ValueError("MCP response exceeds the 1 MB output limit")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except ValueError as exc:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}}

    def serve(self, stdin=None, stdout=None) -> int:
        stdin = stdin or sys.stdin.buffer
        stdout = stdout or sys.stdout
        output_lock = threading.Lock()
        active: dict[Any, threading.Event] = {}
        active_lock = threading.Lock()
        def respond(response: dict[str, Any] | None) -> None:
            if response is not None:
                with output_lock:
                    stdout.write(json.dumps(response, ensure_ascii=False, default=str, allow_nan=False) + "\n")
                    stdout.flush()
        def run_request(request: Any, cancel: threading.Event) -> None:
            request_id = request.get("id") if isinstance(request, dict) else None
            try:
                respond(self.handle(request, cancel))
            finally:
                with active_lock:
                    active.pop(request_id, None)
        while True:
            raw = stdin.readline(MAX_FRAME_BYTES + 1)
            if not raw:
                return 0
            if len(raw) > MAX_FRAME_BYTES:
                while raw and not raw.endswith(b"\n"):
                    raw = stdin.readline(MAX_FRAME_BYTES + 1)
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "MCP frame exceeds 4 MB limit"}}
            else:
                try:
                    request = json.loads(raw)
                    if isinstance(request, dict) and request.get("method") == "notifications/cancelled":
                        params = request.get("params", {})
                        target = params.get("requestId") if isinstance(params, dict) else None
                        with active_lock:
                            cancellation = active.get(target)
                        if cancellation:
                            cancellation.set()
                        response = None
                    elif (isinstance(request, dict) and request.get("method") == "tools/call"
                          and isinstance(request.get("params"), dict)
                          and request["params"].get("name") == "openrpa_run_workflow"
                          and request.get("id") is not None):
                        cancellation = threading.Event()
                        with active_lock:
                            active[request["id"]] = cancellation
                        threading.Thread(target=run_request, args=(request, cancellation), daemon=True).start()
                        response = None
                    else:
                        response = self.handle(request)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
                except Exception as exc:
                    print(f"MCP server error: {type(exc).__name__}: {exc}", file=sys.stderr)
                    response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": "Internal server error"}}
            respond(response)
