from __future__ import annotations

import csv
import json
import datetime
import shutil
import time
import tempfile
import os
import io
import copy as copy_module
import zipfile
import sqlite3
import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .expressions import evaluate, interpolate
from .model import WorkflowError, validate_workflow, validate_workflow_bindings
from .network import request as restricted_http_request, EgressDenied, assert_public_url
from .credentials import get_safe_keyring


class RunCancelled(Exception):
    pass


@dataclass
class RunOptions:
    allow_network: bool = False
    allow_desktop: bool = False
    extra_file_roots: tuple[Path, ...] = ()
    cancel: Callable[[], bool] = lambda: False
    event: Callable[[dict[str, Any]], None] = lambda _e: None
    max_log_events: int = 1000
    max_log_event_chars: int = 16384
    audit: Callable[[str, dict[str, Any]], None] = lambda _action, _details: None
    max_duration_seconds: int = 3600
    max_activity_executions: int = 100_000
    debugger: Any | None = None


@dataclass
class RunResult:
    status: str
    variables: dict[str, Any]
    logs: list[dict[str, Any]]
    activities: dict[str, dict[str, Any]]
    error: dict[str, Any] | None = None


class WorkflowEngine:
    def __init__(self, project: dict[str, Any], root: Path, options: RunOptions | None = None):
        self.project = project
        self.root = root.resolve()
        self.options = options or RunOptions()
        limits=project.get("limits",{}) if isinstance(project.get("limits",{}),dict) else {}
        self._max_run_seconds=min(max(int(limits.get("maxRunSeconds",self.options.max_duration_seconds)),1),86_400)
        self._max_activity_executions=min(max(int(limits.get("maxActivityExecutions",self.options.max_activity_executions)),1),1_000_000)
        self._max_loop_items=min(max(int(limits.get("maxLoopItems",100_000)),1),1_000_000)
        self._max_file_bytes=min(max(int(limits.get("maxFileBytes",20_000_000)),1),100_000_000)
        self._activity_executions=0
        self._loop_items_executed=0
        self._run_started=time.monotonic()
        self._browser_runtime: Any = None
        self._browser: Any = None
        self._browser_context: Any = None
        self._browser_page: Any = None
        self._secret_values: set[str] = set()
        self.workflows: dict[str, dict[str, Any]] = {}
        for key, rel in project["workflows"].items():
            path = (self.root / rel).resolve()
            self._assert_path(path, allow_file=True)
            try:
                self.workflows[key] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise WorkflowError(f"Cannot load workflow {key}: {exc}", code="workflow-read-error") from exc
        for key, workflow in self.workflows.items():
            problems = validate_workflow(workflow, set(self.workflows))
            if problems:
                first = problems[0]
                raise WorkflowError(f"{key}: {first['message']}", first.get("activityId"), first["code"])
        self._validate_call_graph()

    def _validate_call_graph(self) -> None:
        calls: dict[str,set[str]]={name:set() for name in self.workflows}
        def visit(name: str, activities: list[dict[str,Any]]) -> None:
            for activity in activities:
                if activity.get("type")=="invoke_workflow" and activity.get("workflow") in calls:
                    calls[name].add(activity["workflow"])
                for branch in ("then","else","body","catch","finally"):
                    if isinstance(activity.get(branch),list): visit(name,activity[branch])
                if activity.get("type")=="switch" and isinstance(activity.get("cases"),list):
                    for case in activity["cases"]:
                        if isinstance(case,dict) and isinstance(case.get("activities"),list):
                            visit(name,case["activities"])
        for name,workflow in self.workflows.items(): visit(name,workflow["activities"])
        for name,workflow in self.workflows.items():
            if workflow.get("executionModel")=="flowchart":
                for node in workflow["flowchart"]["nodes"]:
                    if node["kind"]=="action": visit(name,[node["activity"]])
            if workflow.get("executionModel")=="state_machine":
                for state in workflow["stateMachine"]["states"]:
                    visit(name,state.get("activities",[]))
        active:set[str]=set();complete:set[str]=set()
        def dfs(name:str)->None:
            if name in active: raise WorkflowError(f"Workflow invocation cycle includes '{name}'",code="workflow-cycle")
            if name in complete:return
            active.add(name)
            for child in calls[name]:dfs(child)
            active.remove(name);complete.add(name)
        for name in calls:dfs(name)

    def _assert_path(self, target: Path, allow_file: bool = False) -> None:
        roots = (self.root, *(p.expanduser().resolve() for p in self.options.extra_file_roots))
        for root in roots:
            try:
                target.relative_to(root)
                return
            except ValueError:
                continue
        raise WorkflowError(f"File path escapes approved roots: {target}", code="file-permission-denied")

    def _audit_path(self, target: Path) -> str:
        roots=(self.root,*(item.expanduser().resolve() for item in self.options.extra_file_roots))
        for index,root in enumerate(roots):
            try:relative=target.relative_to(root)
            except ValueError:continue
            return str(relative) if index==0 else str(Path(f"approved-root-{index}")/relative)
        return "[outside-approved-roots]"

    def _path(self, raw: Any, variables: dict[str, Any], for_write: bool = False) -> Path:
        value = interpolate(raw, variables)
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = self.root / path
        path = path.resolve()
        self._assert_path(path)
        if for_write:
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        fd,temporary=tempfile.mkstemp(prefix=".openrpa-write-",dir=path.parent)
        try:
            with os.fdopen(fd,"wb") as stream:
                stream.write(data);stream.flush();os.fsync(stream.fileno())
            if path.exists():
                try: os.chmod(temporary,path.stat().st_mode)
                except OSError: pass
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def run(self, workflow_name: str, inputs: dict[str, Any] | None = None) -> RunResult:
        logs: list[dict[str, Any]] = []
        states: dict[str, dict[str, Any]] = {}
        variables: dict[str, Any] = {}
        try:
            binding_problems=validate_workflow_bindings(self.workflows)
            if binding_problems:
                first=binding_problems[0]
                raise WorkflowError(first["message"],first.get("activityId"),first["code"])
            if workflow_name not in self.workflows:
                raise WorkflowError(f"Unknown workflow '{workflow_name}'", code="workflow-not-found")
            if inputs is not None and not isinstance(inputs,dict):
                raise WorkflowError("Workflow inputs must be an object",code="argument-inputs")
            if len(json.dumps(inputs or {},ensure_ascii=False,default=str))>2_000_000:
                raise WorkflowError("Workflow input data exceeds the 2 MB limit",code="input-size-limit")
            wf = self.workflows[workflow_name]
            variables = {v["name"]: v.get("value") for v in wf.get("variables", [])}
            for spec in wf.get("variables", []):
                if not _matches_type(variables[spec["name"]],spec.get("type","any")):
                    raise WorkflowError(f"Variable '{spec['name']}' does not match declared type {spec.get('type')}",code="variable-type")
            args = {a["name"]: a for a in wf.get("arguments", [])}
            unknown=set(inputs or {})-set(args)
            if unknown:
                raise WorkflowError(f"Unknown input argument(s): {', '.join(sorted(map(str,unknown)))}",code="argument-unknown")
            for name, spec in args.items():
                if name in (inputs or {}):
                    variables[name] = (inputs or {})[name]
                elif "default" in spec:
                    variables[name] = spec["default"]
                elif spec.get("direction", "in") in {"in", "inout"} and spec.get("required", True):
                    raise WorkflowError(f"Missing required input argument '{name}'", code="argument-missing")
                if name in variables and not _matches_type(variables[name],spec.get("type","any")):
                    raise WorkflowError(f"Argument '{name}' does not match declared type {spec.get('type')}",code="argument-type")
            if wf.get("executionModel","sequence")=="flowchart":
                self._flowchart(wf["flowchart"],variables,logs,states,workflow_name)
            elif wf.get("executionModel")=="state_machine":
                self._state_machine(wf["stateMachine"],variables,logs,states,workflow_name)
            else:
                self._sequence(wf["activities"], variables, logs, states, workflow_name)
            return RunResult("succeeded", self._redact_value(variables), logs, self._redact_value(states))
        except RunCancelled:
            return RunResult("cancelled", self._redact_value(variables), logs, self._redact_value(states))
        except Exception as exc:
            aid = getattr(exc, "activity_id", None)
            frames=getattr(exc,"workflow_stack",[])
            safe_frames=[{"workflow":self._redact_text(str(frame.get("workflow","")))[:200],"activityId":self._redact_text(str(frame.get("activityId","")))[:128],"targetWorkflow":self._redact_text(str(frame.get("targetWorkflow","")))[:200]}
                for frame in frames[:40] if isinstance(frame,dict)] if isinstance(frames,list) else []
            message=self._redact_text(str(exc))
            if safe_frames:
                path=" → ".join(f"{frame['workflow']}/{frame['activityId']} → {frame['targetWorkflow']}" for frame in safe_frames)
                message=f"{message} · Call path: {path}"
            error = {"code": getattr(exc, "code", "activity-failed"), "message": message, "activityId": aid,
                "workflow":getattr(exc,"workflow",workflow_name),"workflowStack":safe_frames,"type": type(exc).__name__}
            return RunResult("failed", self._redact_value(variables), logs, self._redact_value(states), error)
        finally:
            self._close_browser()

    def _check_cancel(self) -> None:
        if self.options.cancel():
            raise RunCancelled()
        if time.monotonic()-self._run_started>self._max_run_seconds:
            raise WorkflowError(f"Run exceeded its {self._max_run_seconds} second execution quota",code="run-timeout")

    def _emit(self, event: dict[str, Any], logs: list[dict[str, Any]]) -> None:
        event = self._redact_value(event)
        if len(logs) >= max(1, min(int(self.options.max_log_events), 50000)):
            return
        encoded = json.dumps(event, ensure_ascii=False, default=str)
        if len(encoded) > max(256, min(int(self.options.max_log_event_chars), 65536)):
            event = {"event": str(event.get("event", "event")), "activityId": event.get("activityId"),
                     "truncated": True, "preview": encoded[: max(128, self.options.max_log_event_chars - 128)]}
        logs.append(event)
        self.options.event(event)

    def _redact_text(self, text: str) -> str:
        for secret in self._secret_values:
            if secret:
                text=text.replace(secret,"[REDACTED]")
        return text

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value,str): return self._redact_text(value)
        if isinstance(value,list): return [self._redact_value(item) for item in value]
        if isinstance(value,tuple): return [self._redact_value(item) for item in value]
        if isinstance(value,dict): return {key:self._redact_value(item) for key,item in value.items()}
        return value

    def _debug_snapshot(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Return a redacted debugger view small enough for one event/log record."""
        snapshot: dict[str,Any]={}
        used=0
        omitted=0
        for name,value in list(variables.items())[:100]:
            safe=self._redact_value(value)
            try: encoded=json.dumps(safe,ensure_ascii=False,default=str,separators=(",",":"))
            except Exception: encoded=repr(safe)
            if len(encoded)>min(4096,8000-used):
                snapshot[str(name)[:128]]={"type":type(value).__name__,"truncated":True,"preview":encoded[:400]}
                used+=len(encoded[:400])+100
            else:
                snapshot[str(name)[:128]]=safe
                used+=len(encoded)+len(str(name))+16
            if used>=7800:
                omitted=max(0,len(variables)-len(snapshot))
                break
        if len(variables)>100:
            omitted+=len(variables)-100
        if omitted:
            snapshot["__debugger_note"]={"truncated":True,"omittedVariableCount":omitted,"reason":"Debugger snapshots are bounded to protect the event log."}
        return snapshot

    def _validate_debug_edit(self, workflow_name: str, variables: dict[str,Any], name: str, value: Any) -> None:
        if self._redact_value(variables[name]) != variables[name]:
            raise ValueError("Credential-bearing variables cannot be edited in the debugger")
        workflow=self.workflows.get(workflow_name,{})
        specs={item.get("name"):item for item in [*workflow.get("variables",[]),*workflow.get("arguments",[])] if isinstance(item,dict)}
        spec=specs.get(name)
        if spec and not _matches_type(value,spec.get("type","any")):
            raise ValueError(f"Variable '{name}' must remain type {spec.get('type')}")

    def _debug_editable_variables(self, workflow_name: str, variables: dict[str,Any]) -> list[str]:
        editable=[]
        for name,value in variables.items():
            try:
                encoded=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":"))
                if len(encoded.encode("utf-8"))>65536: continue
                self._validate_debug_edit(workflow_name,variables,name,value)
                editable.append(name)
            except (TypeError,ValueError,RecursionError):
                continue
        return editable

    def _sequence(self, activities: list[dict[str, Any]], variables: dict[str, Any], logs: list[dict[str, Any]], states: dict[str, dict[str, Any]], workflow_name: str, depth: int = 0) -> None:
        for activity in activities:
            self._check_cancel()
            self._activity_executions+=1
            if self._activity_executions>self._max_activity_executions:
                raise WorkflowError(f"Run exceeded its {self._max_activity_executions} activity execution quota",activity.get("id"),"activity-quota")
            aid, kind = activity["id"], activity["type"]
            if self.options.debugger is not None:
                self.options.debugger.before_activity(aid,depth,variables,self.options.cancel,lambda event:self._emit(event,logs),
                    snapshot=self._debug_snapshot,editable=lambda current:self._debug_editable_variables(workflow_name,current),
                    validate_edit=lambda name,value:self._validate_debug_edit(workflow_name,variables,name,value),redact=self._redact_value)
                self._check_cancel()
            started = time.perf_counter()
            state = {"status": "running", "type": kind, "workflow": workflow_name}
            states[aid] = state
            self._emit({"event": "activity-started", "activityId": aid, "type": kind}, logs)
            try:
                self._activity(activity, variables, logs, states, workflow_name, depth)
                if self.options.debugger is not None:
                    self.options.debugger.after_activity(aid,depth)
                state.update(status="succeeded", durationMs=round((time.perf_counter() - started) * 1000, 3))
                self._emit({"event": "activity-completed", "activityId": aid, "type": kind, "durationMs": state["durationMs"]}, logs)
            except RunCancelled:
                state["status"] = "cancelled"
                raise
            except Exception as exc:
                state.update(status="failed", error=str(exc), durationMs=round((time.perf_counter() - started) * 1000, 3))
                if not getattr(exc, "activity_id", None):
                    try:
                        setattr(exc, "activity_id", aid)
                    except Exception:
                        pass
                try:
                    if not getattr(exc,"workflow",None):
                        setattr(exc,"workflow",workflow_name)
                    if kind=="invoke_workflow":
                        frames=list(getattr(exc,"workflow_stack",[]))
                        if len(frames)<40:
                            frames.insert(0,{"workflow":workflow_name,"activityId":aid,"targetWorkflow":str(activity.get("workflow",""))})
                            setattr(exc,"workflow_stack",frames)
                except Exception:
                    pass
                self._emit({"event": "activity-failed", "activityId": aid, "type": kind, "error": str(exc)}, logs)
                raise

    def _flowchart(self, graph: dict[str,Any], variables: dict[str,Any], logs: list[dict[str,Any]], states: dict[str,dict[str,Any]], workflow_name: str) -> None:
        nodes={node["id"]:node for node in graph["nodes"]}
        outgoing:dict[str,list[dict[str,Any]]]={node_id:[] for node_id in nodes}
        for transition in graph["transitions"]: outgoing[transition["from"]].append(transition)
        current=graph["start"]
        visits=0
        while current is not None:
            self._check_cancel()
            visits+=1
            if visits>self._max_activity_executions:
                raise WorkflowError(f"Flowchart exceeded its {self._max_activity_executions} node visit quota",current,"activity-quota")
            node=nodes[current];kind=node["kind"]
            if kind=="action":
                self._sequence([node["activity"]],variables,logs,states,workflow_name)
                edges=outgoing[current]
                current=edges[0]["to"] if edges else None
                continue
            aid=current;node_type=f"flowchart_{kind}"
            if self.options.debugger is not None:
                self.options.debugger.before_activity(aid,0,variables,self.options.cancel,lambda event:self._emit(event,logs),
                    snapshot=self._debug_snapshot,editable=lambda current:self._debug_editable_variables(workflow_name,current),
                    validate_edit=lambda name,value:self._validate_debug_edit(workflow_name,variables,name,value),redact=self._redact_value)
                self._check_cancel()
            states[aid]={"status":"running","type":node_type,"workflow":workflow_name}
            self._emit({"event":"activity-started","activityId":aid,"type":node_type},logs)
            try:
                if kind=="end": next_node=None
                elif kind=="decision":
                    outcome=evaluate(node["condition"],variables)
                    if not isinstance(outcome,bool): raise WorkflowError("Flowchart decision must evaluate to true or false",aid,"flowchart-condition-type")
                    edge=next(edge for edge in outgoing[aid] if edge["when"]==("true" if outcome else "false"))
                    next_node=edge["to"]
                else: next_node=outgoing[aid][0]["to"]
                states[aid].update(status="succeeded",durationMs=0)
                self._emit({"event":"activity-completed","activityId":aid,"type":node_type,"nextNode":next_node},logs)
                if self.options.debugger is not None: self.options.debugger.after_activity(aid,0)
                current=next_node
            except Exception as exc:
                states[aid].update(status="failed",error=str(exc))
                if not getattr(exc,"activity_id",None):
                    try: setattr(exc,"activity_id",aid)
                    except Exception: pass
                self._emit({"event":"activity-failed","activityId":aid,"type":node_type,"error":str(exc)},logs)
                raise

    def _state_machine(self, machine: dict[str,Any], variables: dict[str,Any], logs: list[dict[str,Any]], states: dict[str,dict[str,Any]], workflow_name: str) -> None:
        """Run states in order, choosing the first true guarded transition.

        A transition without a condition is an explicit final fallback. State
        visit limits use the same project execution quota as flowcharts.
        """
        state_map={state["id"]:state for state in machine["states"]}
        outgoing:dict[str,list[dict[str,Any]]]={state_id:[] for state_id in state_map}
        for transition in machine["transitions"]:outgoing[transition["from"]].append(transition)
        current=machine["initial"]
        visits=0
        while current is not None:
            self._check_cancel()
            visits+=1
            if visits>self._max_activity_executions:
                raise WorkflowError(f"State machine exceeded its {self._max_activity_executions} state visit quota",current,"activity-quota")
            state=state_map[current]
            if self.options.debugger is not None:
                self.options.debugger.before_activity(current,0,variables,self.options.cancel,lambda event:self._emit(event,logs),
                    snapshot=self._debug_snapshot,editable=lambda active:self._debug_editable_variables(workflow_name,active),
                    validate_edit=lambda name,value:self._validate_debug_edit(workflow_name,variables,name,value),redact=self._redact_value)
                self._check_cancel()
            state_type="state_machine_state"
            states[current]={"status":"running","type":state_type,"workflow":workflow_name,"label":state.get("label",current)}
            self._emit({"event":"activity-started","activityId":current,"type":state_type,"state":current},logs)
            try:
                self._sequence(state.get("activities",[]),variables,logs,states,workflow_name)
                next_state=None
                if not state.get("final",False):
                    fallback=None
                    for transition in outgoing[current]:
                        condition=transition.get("condition")
                        if condition is None:
                            fallback=transition
                            continue
                        outcome=evaluate(condition,variables)
                        if not isinstance(outcome,bool):
                            raise WorkflowError(f"Transition condition from state {current} must evaluate to true or false",current,"state-machine-condition-type")
                        if outcome:
                            next_state=transition["to"]
                            break
                    if next_state is None and fallback is not None:next_state=fallback["to"]
                    if next_state is None:
                        raise WorkflowError(f"No transition condition matched from state {current}",current,"state-machine-no-transition-match")
                states[current].update(status="succeeded",durationMs=0)
                self._emit({"event":"activity-completed","activityId":current,"type":state_type,"nextState":next_state},logs)
                if self.options.debugger is not None:self.options.debugger.after_activity(current,0)
                current=next_state
            except Exception as exc:
                states[current].update(status="failed",error=str(exc))
                if not getattr(exc,"activity_id",None):
                    try:setattr(exc,"activity_id",current)
                    except Exception:pass
                self._emit({"event":"activity-failed","activityId":current,"type":state_type,"error":str(exc)},logs)
                raise

    def _activity(self, a: dict[str, Any], v: dict[str, Any], logs: list[dict[str, Any]], states: dict[str, dict[str, Any]], workflow_name: str, depth: int = 0) -> None:
        kind = a["type"]
        if kind == "assign":
            v[a["target"]] = interpolate(a.get("value"), v)
        elif kind == "credential_get":
            service=str(a.get("service", "")).strip()
            username=str(a.get("username", "")).strip()
            if not service or not username or len(service)>200 or len(username)>200:
                raise WorkflowError("Credential service and username are required", a["id"], "credential-config")
            try:
                keyring=get_safe_keyring()
            except RuntimeError as exc:
                code="credential-runtime-unavailable" if "optional keyring package" in str(exc) else "credential-backend-unsafe"
                raise WorkflowError(str(exc),a["id"],code) from exc
            secret=keyring.get_password(service,username)
            if not isinstance(secret,str) or not secret:
                raise WorkflowError("Credential was not found in the OS credential vault",a["id"],"credential-not-found")
            self._secret_values.add(secret)
            self.options.audit("credential.read", {"activityId":a["id"],"service":service,"username":username})
            v[a.get("result","credential")]=secret
        elif kind == "log":
            message = str(interpolate(a.get("message", ""), v))
            self._emit({"event": "log", "level": a.get("level", "info"), "activityId": a["id"], "message": message}, logs)
        elif kind == "if":
            self._sequence(a.get("then", []) if evaluate(a["condition"], v) else a.get("else", []), v, logs, states, workflow_name,depth+1)
        elif kind == "switch":
            actual=evaluate(a["expression"],v)
            selected=a.get("default",[])
            for case in a.get("cases",[]):
                candidate=case.get("value")
                numeric_pair=isinstance(actual,(int,float)) and not isinstance(actual,bool) and isinstance(candidate,(int,float)) and not isinstance(candidate,bool)
                if (numeric_pair or type(actual) is type(candidate)) and actual==candidate:
                    selected=case.get("activities",[])
                    break
            self._sequence(selected,v,logs,states,workflow_name,depth+1)
        elif kind == "for_each":
            values = evaluate(a["items"], v)
            if not isinstance(values, (list, tuple, str)):
                raise WorkflowError("For Each expression must produce a list, tuple, or string", a["id"], "loop-input")
            if len(values) > self._max_loop_items:
                raise WorkflowError("For Each exceeded the configured item limit", a["id"], "loop-limit")
            item_name = a["itemName"]
            had_old, old = item_name in v, v.get(item_name)
            for value in values:
                self._check_cancel()
                self._loop_items_executed+=1
                if self._loop_items_executed>1_000_000:
                    raise WorkflowError("Workflow exceeded the 1,000,000 total loop item quota",a["id"],"loop-quota")
                v[item_name] = value
                self._sequence(a.get("body", []), v, logs, states, workflow_name,depth+1)
            if had_old:
                v[item_name] = old
            else:
                v.pop(item_name, None)
        elif kind == "while":
            condition=a.get("condition","")
            while True:
                self._check_cancel()
                outcome=evaluate(condition,v)
                if not isinstance(outcome,bool):
                    raise WorkflowError("While condition must evaluate to true or false",a["id"],"while-condition-type")
                if not outcome:
                    break
                self._loop_items_executed+=1
                if self._loop_items_executed>self._max_loop_items or self._loop_items_executed>1_000_000:
                    raise WorkflowError("While exceeded the configured loop item limit",a["id"],"loop-limit")
                self._sequence(a.get("body",[]),v,logs,states,workflow_name,depth+1)
        elif kind == "retry":
            max_attempts=int(a["maxAttempts"])
            retry_on=set(a.get("retryOn",[]))
            delay=float(a.get("delaySeconds",0))
            factor=float(a.get("backoffFactor",1))
            for attempt in range(1,max_attempts+1):
                self._check_cancel()
                variable_checkpoint=copy_module.deepcopy(v)
                try:
                    self._sequence(a["body"],v,logs,states,workflow_name,depth+1)
                    if attempt>1:
                        self._emit({"event":"retry-succeeded","activityId":a["id"],"attempt":attempt,"maxAttempts":max_attempts},logs)
                    break
                except RunCancelled:
                    raise
                except Exception as exc:
                    error_code=getattr(exc,"code","activity-failed")
                    can_retry=attempt<max_attempts and error_code in retry_on
                    self._emit({"event":"retry-attempt-failed","activityId":a["id"],"attempt":attempt,"maxAttempts":max_attempts,"errorCode":error_code,"willRetry":can_retry},logs)
                    if not can_retry:
                        raise
                    v.clear();v.update(variable_checkpoint)
                    remaining=min(delay*(factor**(attempt-1)),60)
                    deadline=time.monotonic()+remaining
                    while time.monotonic()<deadline:
                        self._check_cancel()
                        time.sleep(min(.1,deadline-time.monotonic()))
        elif kind == "try":
            failure: Exception | None = None
            try:
                self._sequence(a.get("body", []), v, logs, states, workflow_name,depth+1)
            except Exception as exc:
                if isinstance(exc, RunCancelled):
                    raise
                failure = exc
                if a.get("errorName"):
                    v[a["errorName"]] = {"message": str(exc), "type": type(exc).__name__}
                self._sequence(a.get("catch", []), v, logs, states, workflow_name,depth+1)
            finally:
                self._sequence(a.get("finally", []), v, logs, states, workflow_name,depth+1)
            if failure is not None and not a.get("catch"):
                raise failure
        elif kind == "invoke_workflow":
            target = a["workflow"]
            raw_inputs=a.get("inputs",{})
            if not isinstance(raw_inputs,dict):
                raise WorkflowError("Invoked workflow inputs must be an object",a["id"],"argument-inputs")
            raw_outputs=a.get("outputs",{})
            if not isinstance(raw_outputs,dict):
                raise WorkflowError("Invoked workflow outputs must be an object",a["id"],"argument-outputs")
            child_args = {k: interpolate(value, v) for k, value in raw_inputs.items()}
            child_wf = self.workflows[target]
            child_vars = {item["name"]: item.get("value") for item in child_wf.get("variables", [])}
            child_specs={arg["name"]:arg for arg in child_wf.get("arguments", [])}
            unknown=set(child_args)-set(child_specs)
            if unknown:
                raise WorkflowError(f"Unknown invoked workflow input(s): {', '.join(sorted(map(str,unknown)))}",a["id"],"argument-unknown")
            invalid_outputs=set(raw_outputs)-{name for name,arg in child_specs.items() if arg.get("direction","in") in {"out","inout"}}
            if invalid_outputs:
                raise WorkflowError(f"Unknown invoked workflow output(s): {', '.join(sorted(map(str,invalid_outputs)))}",a["id"],"argument-output")
            for arg in child_specs.values():
                direction=arg.get("direction","in")
                if arg["name"] in child_args:
                    if direction=="out":
                        raise WorkflowError(f"Output-only argument '{arg['name']}' cannot be supplied as input",a["id"],"argument-direction")
                    child_vars[arg["name"]] = child_args[arg["name"]]
                elif "default" in arg:
                    child_vars[arg["name"]] = arg["default"]
                elif direction in {"in","inout"} and arg.get("required", True):
                    raise WorkflowError(f"Missing invoked workflow argument '{arg['name']}'", a["id"], "argument-missing")
                if arg["name"] in child_vars and not _matches_type(child_vars[arg["name"]],arg.get("type","any")):
                    raise WorkflowError(f"Invoked workflow argument '{arg['name']}' does not match declared type {arg.get('type')}",a["id"],"argument-type")
            before = dict(v)
            if child_wf.get("executionModel","sequence")=="flowchart":
                self._flowchart(child_wf["flowchart"],child_vars,logs,states,target)
            elif child_wf.get("executionModel")=="state_machine":
                self._state_machine(child_wf["stateMachine"],child_vars,logs,states,target)
            else:
                self._sequence(child_wf["activities"], child_vars, logs, states, target,depth+1)
            for arg in child_specs.values():
                if arg.get("direction") in {"out", "inout"} and arg["name"] in child_vars:
                    destination=raw_outputs.get(arg["name"],arg.get("target",arg["name"]))
                    if not isinstance(destination,str) or not destination.isidentifier() or len(destination)>256:
                        raise WorkflowError(f"Output '{arg['name']}' needs a valid caller variable name",a["id"],"argument-output-target")
                    v[destination] = child_vars[arg["name"]]
            if a.get("resultTarget"):
                v[a["resultTarget"]] = {k: value for k, value in child_vars.items() if k not in before}
        elif kind == "file_read_text":
            path = self._path(a["path"], v)
            max_bytes = self._max_file_bytes
            if path.stat().st_size > max_bytes: raise WorkflowError("File exceeds configured read limit", a["id"], "file-size-limit")
            v[a.get("result", "text")] = path.read_text(encoding=a.get("encoding", "utf-8"))
        elif kind == "file_write_text":
            output=str(interpolate(a.get("text", ""), v))
            if len(output.encode("utf-8"))>self._max_file_bytes: raise WorkflowError("Output file exceeds configured write limit",a["id"],"file-size-limit")
            self._atomic_write(self._path(a["path"], v, True),output.encode(a.get("encoding", "utf-8")))
        elif kind == "file_copy":
            src, dst = self._path(a["source"], v), self._path(a["destination"], v, True)
            if src.stat().st_size>self._max_file_bytes: raise WorkflowError("Copy source exceeds configured file limit",a["id"],"file-size-limit")
            shutil.copy2(src, dst)
        elif kind == "file_move":
            src, dst = self._path(a["source"], v), self._path(a["destination"], v, True)
            shutil.move(str(src), str(dst))
        elif kind == "file_delete":
            target = self._path(a["path"], v)
            if target.is_dir():
                raise WorkflowError("File Delete does not remove directories", a["id"], "file-type")
            target.unlink(missing_ok=bool(a.get("missingOk", False)))
        elif kind == "file_list":
            directory = self._path(a["directory"], v)
            pattern = str(a.get("pattern", "*"))
            matches=[str(p.relative_to(self.root)) for p in sorted(directory.glob(pattern)) if p.is_file()]
            if len(matches)>100_000: raise WorkflowError("File listing exceeds 100,000 entries",a["id"],"file-size-limit")
            v[a.get("result", "files")] = matches
        elif kind in {"regex_replace", "regex_match"}:
            source = str(interpolate(a.get("text", ""), v))
            pattern = str(interpolate(a.get("pattern", ""), v))
            if len(pattern)>1000 or len(source)>200_000: raise WorkflowError("Regex pattern or input exceeds its size limit",a["id"],"regex-size-limit")
            try:
                import regex as bounded_regex
                flags=bounded_regex.IGNORECASE if a.get("ignoreCase") else 0
                if kind == "regex_replace":
                    v[a.get("result", "text")] = bounded_regex.sub(pattern, str(interpolate(a.get("replacement", ""), v)), source, flags=flags, timeout=0.25)
                else:
                    match = bounded_regex.search(pattern, source, flags=flags, timeout=0.25)
                    v[a.get("result", "match")] = match.groupdict() if match and match.groupdict() else (match.group(0) if match else None)
            except TimeoutError as exc:
                raise WorkflowError("Regex operation exceeded its 250 ms time quota",a["id"],"regex-timeout") from exc
        elif kind == "transform_field":
            rows = interpolate(a.get("rows", "rows"), v)
            if isinstance(rows, str): rows = evaluate(rows, v)
            field = str(a["field"]); operation = a["operation"]
            result = []
            for row in rows:
                copy = dict(row)
                if field in copy and copy[field] is not None:
                    value = str(copy[field])
                    if operation == "trim": value = value.strip()
                    elif operation == "upper": value = value.upper()
                    elif operation == "lower": value = value.lower()
                    elif operation == "regex_replace":
                        if len(value)>200_000 or len(str(a.get("pattern","")))>1000: raise WorkflowError("Regex pattern or input exceeds its size limit",a["id"],"regex-size-limit")
                        try:
                            import regex as bounded_regex
                            value=bounded_regex.sub(str(a.get("pattern","")),str(a.get("replacement","")),value,timeout=0.25)
                        except TimeoutError as exc: raise WorkflowError("Regex operation exceeded its 250 ms time quota",a["id"],"regex-timeout") from exc
                    else: raise WorkflowError(f"Unsupported field transform: {operation}", a["id"], "transform-operation")
                    copy[field] = value
                result.append(copy)
            v[a.get("result", "rows")] = result
        elif kind == "csv_read":
            path = self._path(a["path"], v)
            max_bytes = self._max_file_bytes
            if path.stat().st_size > max_bytes: raise WorkflowError("CSV exceeds configured read limit", a["id"], "file-size-limit")
            with path.open("r", newline="", encoding=a.get("encoding", "utf-8-sig")) as f:
                v[a.get("result", "rows")] = list(csv.DictReader(f, delimiter=a.get("delimiter", ",")))
        elif kind == "csv_write":
            rows = interpolate(a.get("rows", ""), v)
            if isinstance(rows, str):
                rows = evaluate(rows, v)
            if not isinstance(rows, list):
                raise WorkflowError("CSV Write rows must be a list of objects", a["id"], "csv-input")
            fields = a.get("fields") or list(dict.fromkeys(k for row in rows for k in row.keys()))
            if len(rows)>100_000 or len(fields)>2_000 or sum(sum(len(str(value)) for value in row.values()) for row in rows)>self._max_file_bytes:
                raise WorkflowError("CSV output exceeds its row, field, or size quota",a["id"],"file-size-limit")
            rendered=io.StringIO(newline="")
            writer = csv.DictWriter(rendered, fieldnames=fields, delimiter=a.get("delimiter", ","), extrasaction="ignore")
            writer.writeheader();writer.writerows(rows)
            encoded=rendered.getvalue().encode(a.get("encoding", "utf-8"))
            if len(encoded)>self._max_file_bytes: raise WorkflowError("CSV output exceeds configured file size limit",a["id"],"file-size-limit")
            self._atomic_write(self._path(a["path"], v, True),encoded)
        elif kind == "xlsx_read":
            path=self._path(a["path"],v)
            if path.suffix.lower()!='.xlsx': raise WorkflowError("Spreadsheet Read supports .xlsx files only",a["id"],"spreadsheet-format")
            if path.stat().st_size>self._max_file_bytes: raise WorkflowError("Spreadsheet exceeds configured read limit",a["id"],"file-size-limit")
            try:
                with zipfile.ZipFile(path) as archive:
                    infos=archive.infolist()
                    if len(infos)>2_000 or sum(info.file_size for info in infos)>min(self._max_file_bytes*10,200_000_000):
                        raise WorkflowError("Spreadsheet expands beyond its archive quota",a["id"],"file-size-limit")
                    for info in infos:
                        if not info.filename.lower().endswith((".xml",".rels")):continue
                        tail=b""
                        with archive.open(info) as stream:
                            while chunk:=stream.read(65_536):
                                self._check_cancel()
                                probe=(tail+chunk).upper()
                                if b"<!DOCTYPE" in probe or b"<!ENTITY" in probe:
                                    raise WorkflowError("Spreadsheet XML must not contain DTD or entity declarations",a["id"],"spreadsheet-xml-entity")
                                tail=probe[-16:]
                from openpyxl import load_workbook
                workbook=load_workbook(path,read_only=True,data_only=bool(a.get("dataOnly",True)))
            except WorkflowError: raise
            except Exception as exc: raise WorkflowError(f"Cannot open XLSX spreadsheet: {exc}",a["id"],"spreadsheet-read-error") from exc
            try:
                sheet_name=str(a.get("sheetName") or workbook.sheetnames[0])
                if sheet_name not in workbook.sheetnames: raise WorkflowError(f"Worksheet not found: {sheet_name}",a["id"],"spreadsheet-sheet")
                sheet=workbook[sheet_name];header_row=int(a.get("headerRow",1))
                if header_row>sheet.max_row:raise WorkflowError("Spreadsheet headerRow is beyond the worksheet data",a["id"],"spreadsheet-header")
                headers=[cell.value for cell in next(sheet.iter_rows(min_row=header_row,max_row=header_row))]
                while headers and headers[-1] is None:headers.pop()
                if not headers or len(headers)>2_000 or any(not isinstance(value,(str,int,float)) or not str(value).strip() for value in headers):
                    raise WorkflowError("Spreadsheet header row needs 1–2,000 non-empty text or numeric headers",a["id"],"spreadsheet-header")
                headers=[str(value).strip() for value in headers]
                if len(headers)!=len(set(headers)): raise WorkflowError("Spreadsheet header names must be unique",a["id"],"spreadsheet-header-duplicate")
                rows=[];text_bytes=0
                for values in sheet.iter_rows(min_row=header_row+1,max_col=len(headers),values_only=True):
                    self._check_cancel()
                    if all(value is None for value in values):continue
                    if len(rows)>=100_000:raise WorkflowError("Spreadsheet exceeds 100,000 data rows",a["id"],"spreadsheet-row-limit")
                    if (len(rows)+1)*len(headers)>2_000_000:raise WorkflowError("Spreadsheet exceeds two million cells",a["id"],"spreadsheet-cell-limit")
                    row={}
                    for name,value in zip(headers,values):
                        if isinstance(value,(datetime.date,datetime.datetime,datetime.time)):value=value.isoformat()
                        if isinstance(value,str):text_bytes+=len(value.encode("utf-8"))
                        if text_bytes>self._max_file_bytes:raise WorkflowError("Spreadsheet cell text exceeds configured data limit",a["id"],"file-size-limit")
                        row[name]=value
                    rows.append(row)
                v[a.get("result","rows")]=rows
            finally:workbook.close()
        elif kind == "pdf_read_text":
            path=self._path(a["path"],v)
            if path.suffix.lower()!=".pdf":raise WorkflowError("PDF Read Text supports .pdf files only",a["id"],"pdf-format")
            if path.stat().st_size>self._max_file_bytes:raise WorkflowError("PDF exceeds configured read limit",a["id"],"file-size-limit")
            self._check_cancel()
            try:
                from pypdf import PdfReader
                reader=PdfReader(path,strict=True)
                if reader.is_encrypted:raise WorkflowError("Encrypted PDFs are not supported; provide an authorised unencrypted copy",a["id"],"pdf-encrypted")
                page_count=len(reader.pages)
                max_pages=int(a.get("maxPages",500))
                if page_count>max_pages:raise WorkflowError(f"PDF has {page_count} pages, exceeding the configured {max_pages}-page limit",a["id"],"pdf-page-limit")
                pages=[];total_bytes=0
                for page in reader.pages:
                    self._check_cancel()
                    text=page.extract_text(extraction_mode="layout" if a.get("layoutMode",False) else "plain") or ""
                    total_bytes+=len(text.encode("utf-8"))
                    if total_bytes>self._max_file_bytes:raise WorkflowError("Extracted PDF text exceeds configured data limit",a["id"],"file-size-limit")
                    pages.append(text)
                v[a.get("result","text") ]="\n\f\n".join(pages)
                v[a.get("pageCountResult","pageCount")]=page_count
            except WorkflowError:raise
            except Exception as exc:raise WorkflowError(f"Cannot extract text from PDF: {type(exc).__name__}: {exc}",a["id"],"pdf-read-error") from exc
        elif kind == "sqlite_query":
            path=self._path(a["path"],v)
            if path.suffix.lower() not in {".db",".sqlite",".sqlite3"}:raise WorkflowError("SQLite Query supports .db, .sqlite, or .sqlite3 files only",a["id"],"sqlite-format")
            parameters=interpolate(a.get("parameters",[]),v)
            if not isinstance(parameters,(list,dict)):raise WorkflowError("SQLite Query parameters must resolve to a list or object",a["id"],"sqlite-parameters")
            self.options.audit("database.query.attempt",{"activityId":a["id"],"path":self._audit_path(path),"parameterCount":len(parameters)})
            if not path.is_file():raise WorkflowError("SQLite database file does not exist",a["id"],"sqlite-not-found")
            if path.stat().st_size>self._max_file_bytes:raise WorkflowError("SQLite database exceeds configured read limit",a["id"],"file-size-limit")
            query=interpolate(a["query"],v)
            if not isinstance(query,str) or not query.strip() or len(query)>100_000:raise WorkflowError("SQLite Query needs a SQL statement no longer than 100,000 characters",a["id"],"sqlite-query")
            bound_values=parameters.values() if isinstance(parameters,dict) else parameters
            if len(parameters)>1000 or any(value is not None and not isinstance(value,(str,int,float,bool,bytes)) for value in bound_values):
                raise WorkflowError("SQLite Query accepts at most 1,000 scalar parameters",a["id"],"sqlite-parameters")
            timeout=float(a.get("timeoutSeconds",30));deadline=time.monotonic()+timeout;max_rows=int(a.get("maxRows",10_000))
            connection=None
            try:
                connection=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=min(timeout,0.5),isolation_level=None)
                connection.enable_load_extension(False)
                connection.execute("PRAGMA query_only=ON")
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute(f"PRAGMA busy_timeout={min(int(timeout*1000),500)}")
                allowed={sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION}
                if hasattr(sqlite3,"SQLITE_RECURSIVE"):allowed.add(sqlite3.SQLITE_RECURSIVE)
                def authorize(action:int,arg1:str|None,arg2:str|None,_database:str|None,_trigger:str|None)->int:
                    if action==sqlite3.SQLITE_READ and _database!="main":return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY
                connection.set_authorizer(authorize)
                def progress()->int:
                    return int(self.options.cancel() or time.monotonic()>deadline)
                connection.set_progress_handler(progress,1000)
                cursor=connection.execute(query,parameters)
                columns=[str(item[0]) for item in (cursor.description or [])]
                names=[];seen_names={}
                for column in columns:
                    seen_names[column]=seen_names.get(column,0)+1
                    names.append(column if seen_names[column]==1 else f"{column}_{seen_names[column]}")
                rows=[];result_bytes=0
                while True:
                    self._check_cancel()
                    if time.monotonic()>deadline:raise WorkflowError("SQLite Query exceeded its time limit",a["id"],"sqlite-timeout")
                    batch=cursor.fetchmany(min(128,max_rows-len(rows)+1))
                    if not batch:break
                    for raw in batch:
                        if len(rows)>=max_rows:raise WorkflowError(f"SQLite Query exceeded its {max_rows}-row result limit",a["id"],"sqlite-row-limit")
                        row={name:( {"$binaryBase64":base64.b64encode(value).decode("ascii")} if isinstance(value,bytes) else value) for name,value in zip(names,raw)}
                        try:encoded=json.dumps(row,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode("utf-8")
                        except (TypeError,ValueError) as exc:raise WorkflowError("SQLite Query returned a value that cannot be represented as JSON",a["id"],"sqlite-value") from exc
                        result_bytes+=len(encoded)
                        if result_bytes>self._max_file_bytes:raise WorkflowError("SQLite Query result exceeds configured data limit",a["id"],"file-size-limit")
                        rows.append(row)
                v[a.get("result","rows")]=rows
                self.options.audit("database.query.completed",{"activityId":a["id"],"path":self._audit_path(path),"rowCount":len(rows),"parameterCount":len(parameters)})
            except WorkflowError:raise
            except sqlite3.Error as exc:
                if self.options.cancel():raise RunCancelled() from exc
                if time.monotonic()>deadline or "interrupted" in str(exc).lower():raise WorkflowError("SQLite Query exceeded its time limit",a["id"],"sqlite-timeout") from exc
                message="SQLite Query was blocked by the read-only policy" if "not authorized" in str(exc).lower() else f"SQLite Query failed: {exc}"
                code="sqlite-readonly-policy" if "not authorized" in str(exc).lower() else "sqlite-query-error"
                raise WorkflowError(message,a["id"],code) from exc
            finally:
                if connection is not None:connection.close()
        elif kind == "xlsx_write":
            if Path(str(interpolate(a["path"],v))).suffix.lower()!='.xlsx':raise WorkflowError("Spreadsheet Write supports .xlsx output only",a["id"],"spreadsheet-format")
            rows=interpolate(a.get("rows","rows"),v)
            if isinstance(rows,str):rows=evaluate(rows,v)
            if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise WorkflowError("Spreadsheet Write rows must be a list of objects",a["id"],"spreadsheet-input")
            if len(rows)>100_000:raise WorkflowError("Spreadsheet output exceeds 100,000 rows",a["id"],"spreadsheet-row-limit")
            fields=a.get("fields") or list(dict.fromkeys(key for row in rows for key in row))
            if not fields or len(fields)>2_000 or any(not isinstance(name,str) or not name.strip() for name in fields) or len(fields)!=len(set(fields)):
                raise WorkflowError("Spreadsheet Write needs 1–2,000 unique text column names",a["id"],"spreadsheet-fields")
            if any(not isinstance(key,str) for row in rows for key in row) or any(key not in fields for row in rows for key in row):raise WorkflowError("Spreadsheet row contains a column not listed in fields",a["id"],"spreadsheet-fields")
            if sum(len(str(value).encode("utf-8")) for row in rows for value in row.values())>self._max_file_bytes:raise WorkflowError("Spreadsheet cell data exceeds configured write limit",a["id"],"file-size-limit")
            if len(rows)*len(fields)>2_000_000:raise WorkflowError("Spreadsheet exceeds two million cells",a["id"],"spreadsheet-cell-limit")
            from openpyxl import Workbook
            workbook=Workbook();sheet=workbook.active;sheet.title=str(a.get("sheetName") or "Sheet1");sheet.append(fields)
            for row in rows:
                self._check_cancel()
                values=[]
                for name in fields:
                    value=row.get(name)
                    if isinstance(value,(dict,list,tuple,set)):raise WorkflowError("Spreadsheet cells must be scalar values",a["id"],"spreadsheet-cell-type")
                    values.append(value)
                sheet.append(values)
                for cell in sheet[sheet.max_row]:
                    if isinstance(cell.value,str) and cell.value.startswith("="):cell.data_type="s"
            output=io.BytesIO();workbook.save(output);workbook.close();encoded=output.getvalue()
            if len(encoded)>self._max_file_bytes:raise WorkflowError("Spreadsheet exceeds configured write limit",a["id"],"file-size-limit")
            self._atomic_write(self._path(a["path"],v,True),encoded)
        elif kind == "json_parse":
            value = interpolate(a.get("text", ""), v)
            if not isinstance(value, str):
                value = json.dumps(value)
            parsed = json.loads(value)
            selector = a.get("select")
            if selector:
                for part in selector.split("."):
                    parsed = parsed[int(part)] if isinstance(parsed, list) else parsed[part]
            v[a.get("result", "json")]=parsed
        elif kind == "json_write":
            value = interpolate(a.get("value", ""), v)
            if isinstance(value, str):
                value = evaluate(value, v)
            rendered = json.dumps(value, ensure_ascii=False, indent=2)
            if len(rendered.encode("utf-8"))>self._max_file_bytes: raise WorkflowError("JSON output exceeds configured file limit",a["id"],"file-size-limit")
            if a.get("path"):
                self._atomic_write(self._path(a["path"], v, True),(rendered+"\n").encode("utf-8"))
            if a.get("result"):
                v[a["result"]] = rendered
        elif kind == "wait":
            seconds = float(interpolate(a.get("seconds", 0), v))
            if seconds < 0 or seconds > 300:
                raise WorkflowError("Wait duration must be between 0 and 300 seconds", a["id"], "wait-range")
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                self._check_cancel()
                time.sleep(min(0.05, end - time.monotonic()))
        elif kind == "http_request":
            if not self.options.allow_network:
                raise WorkflowError("HTTP access requires explicit per-run network permission", a["id"], "network-permission-denied")
            url = str(interpolate(a["url"], v))
            body = a.get("body")
            if body is not None:
                body = str(interpolate(body, v)).encode("utf-8")
            parsed_target=urlsplit(url)
            self.options.audit("http.request", {"activityId":a["id"],"method":str(a.get("method","GET")).upper(),"host":parsed_target.hostname,"scheme":parsed_target.scheme})
            try:
                v[a.get("result", "response")] = restricted_http_request(
                    url, str(a.get("method", "GET")),
                    {str(k): str(interpolate(val, v)) for k, val in a.get("headers", {}).items()},
                    body, float(a.get("timeoutSeconds", 20)), int(a.get("maxResponseBytes", 5_000_000)))
            except EgressDenied as exc:
                raise WorkflowError(str(exc), a["id"], "http-egress-denied") from exc
            except (OSError, TimeoutError, ValueError) as exc:
                code="http-timeout" if isinstance(exc,TimeoutError) else "http-error"
                raise WorkflowError(f"HTTP request failed: {exc}", a["id"], code) from exc
        elif kind.startswith("browser_"):
            self._browser_activity(a, v, logs)
        elif kind.startswith("desktop_"):
            self._desktop_activity(a, v)
        else:
            raise WorkflowError(f"Unsupported activity: {kind}", a.get("id"), "activity-unsupported")

        if kind in {"file_read_text","csv_read","xlsx_read","pdf_read_text","sqlite_query","file_list"}:
            raw_path=a.get("path",a.get("directory",""))
            target=self._path(raw_path,v) if raw_path else self.root
            self.options.audit("file.read", {"activityId":a["id"],"path":self._audit_path(target)})
        elif kind in {"file_write_text","csv_write","xlsx_write","json_write"}:
            raw_path=a.get("path")
            if raw_path:
                target=self._path(raw_path,v)
                self.options.audit("file.write", {"activityId":a["id"],"path":self._audit_path(target)})
        elif kind in {"file_copy","file_move"}:
            for field,action in (("source","file.read"),("destination","file.write")):
                target=self._path(a[field],v)
                self.options.audit(action,{"activityId":a["id"],"path":self._audit_path(target)})
        elif kind=="file_delete":
            target=self._path(a["path"],v)
            self.options.audit("file.delete",{"activityId":a["id"],"path":self._audit_path(target)})

    def _browser_activity(self, a: dict[str, Any], v: dict[str, Any], logs: list[dict[str, Any]] | None = None) -> None:
        kind = a["type"]
        if kind == "browser_launch":
            if self._browser_page is not None:
                raise WorkflowError("Browser is already open", a["id"], "browser-state")
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise WorkflowError("Browser automation requires optional Playwright and its browser runtime. See docs/AUTOMATION_ADAPTERS.md", a["id"], "runtime-unavailable") from exc
            self._browser_runtime = sync_playwright().start()
            self._browser = self._browser_runtime.chromium.launch(headless=bool(a.get("headless", False)))
            self._browser_context = self._browser.new_context()
            self._browser_page = self._browser_context.new_page()
            self._browser_page.set_default_timeout(30_000)
            self._browser_page.set_default_navigation_timeout(60_000)
            def guard_browser_request(route: Any) -> None:
                try:
                    assert_public_url(route.request.url)
                    route.continue_()
                except Exception:
                    route.abort()
            self._browser_page.route("**/*", guard_browser_request)
            return
        if kind == "browser_close":
            self._close_browser()
            return
        if self._browser_page is None:
            raise WorkflowError("Launch Browser must run before browser interaction", a["id"], "browser-state")
        timeout = min(max(float(a.get("timeoutSeconds", 15)),1),120) * 1000
        if kind == "browser_wait":
            state=a.get("state","visible")
            self._locator(a,logs,allow_fallback=state not in {"hidden","detached"}).wait_for(state=state,timeout=timeout)
            return
        if kind == "browser_assert":
            assertion=a.get("assertion","visible")
            locator=self._locator(a,logs,allow_fallback=assertion!="hidden")
            if assertion in {"visible","hidden"}:
                actual=locator.is_visible(timeout=timeout) if assertion=="visible" else locator.is_hidden(timeout=timeout)
                passed=actual
            elif assertion in {"enabled","disabled"}:
                actual=locator.is_enabled(timeout=timeout);passed=actual if assertion=="enabled" else not actual
            elif assertion=="checked":
                actual=locator.is_checked(timeout=timeout);passed=actual
            elif assertion=="text":
                actual=locator.inner_text(timeout=timeout)
                expected=str(interpolate(a.get("expectedText",""),v))
                passed=actual==expected if a.get("textMatch","exact")=="exact" else expected in actual
            else: raise WorkflowError(f"Unsupported browser assertion: {assertion}",a["id"],"browser-assertion")
            if not passed:
                detail=f"expected {assertion}={a.get('expectedText','')!r}, observed {actual!r}" if assertion=="text" else f"expected {assertion}, observed {actual}"
                raise WorkflowError(f"Browser assertion failed for selector {a.get('selector')!r}: {detail}",a["id"],"browser-assertion-failed")
            return
        if kind == "browser_navigate":
            url = str(interpolate(a["url"], v))
            if not url.startswith(("https://", "http://")): raise WorkflowError("Browser URL must use http or https", a["id"], "browser-url")
            if not self.options.allow_network: raise WorkflowError("Browser access requires explicit per-run network permission", a["id"], "network-permission-denied")
            try: assert_public_url(url)
            except EgressDenied as exc: raise WorkflowError(str(exc),a["id"],"http-egress-denied") from exc
            self._browser_page.goto(url, wait_until=a.get("waitUntil", "domcontentloaded"), timeout=timeout)
        elif kind == "browser_click": self._locator(a,logs).click(timeout=timeout)
        elif kind == "browser_fill": self._locator(a,logs).fill(str(interpolate(a.get("value", ""), v)), timeout=timeout)
        elif kind == "browser_select": self._locator(a,logs).select_option(value=str(interpolate(a.get("value", ""),v)),timeout=timeout)
        elif kind == "browser_check": self._locator(a,logs).check(timeout=timeout)
        elif kind == "browser_uncheck": self._locator(a,logs).uncheck(timeout=timeout)
        elif kind == "browser_text": v[a.get("result", "text")] = self._locator(a,logs).inner_text(timeout=timeout)
        elif kind == "browser_screenshot":
            path = self._path(a["path"], v, True)
            self._browser_page.screenshot(path=str(path), full_page=bool(a.get("fullPage", False)), timeout=timeout)
        else: raise WorkflowError(f"Unsupported browser activity: {kind}", a["id"], "activity-unsupported")

    def _close_browser(self) -> None:
        if self._browser is not None:
            try: self._browser.close()
            except Exception: pass
        if self._browser_runtime is not None:
            try: self._browser_runtime.stop()
            except Exception: pass
        self._browser_runtime = self._browser = self._browser_context = self._browser_page = None

    def _locator(self, a: dict[str, Any], logs: list[dict[str, Any]] | None = None, allow_fallback: bool = True) -> Any:
        def make_locator(kind: str, value: str, exact: bool = True) -> Any:
            if kind == "role":
                role, _, name = value.partition(":")
                return self._browser_page.get_by_role(role, name=name or None, exact=exact)
            if kind == "label": return self._browser_page.get_by_label(value, exact=exact)
            if kind == "text": return self._browser_page.get_by_text(value, exact=exact)
            if kind == "placeholder": return self._browser_page.get_by_placeholder(value, exact=exact)
            if kind == "test_id": return self._browser_page.get_by_test_id(value)
            if kind == "css": return self._browser_page.locator(value)
            raise WorkflowError(f"Unknown selector kind: {kind}", a["id"], "selector-kind")

        kind, value = a.get("selectorKind", "role"), str(a.get("selector", ""))
        if not value: raise WorkflowError("Browser selector is required", a["id"], "selector-empty")
        exact = bool(a.get("exact", True))
        primary=make_locator(kind,value,exact)
        fallbacks=a.get("selectorFallbacks",[])
        if not allow_fallback or not fallbacks:
            return primary
        primary_count=primary.count()
        if primary_count==1:
            return primary
        matches=[]
        ambiguous=[]
        for index,fallback in enumerate(fallbacks):
            locator=make_locator(str(fallback["selectorKind"]),str(fallback["selector"]),bool(fallback.get("exact",True)))
            count=locator.count()
            if count==1: matches.append((index,locator))
            elif count>1: ambiguous.append(index)
        if len(matches)!=1 or ambiguous:
            reason="ambiguous" if ambiguous or len(matches)>1 or primary_count>1 else "not found"
            code="selector-fallback-ambiguous" if reason=="ambiguous" else "selector-fallback-not-found"
            raise WorkflowError(f"Browser selector {reason}: primary matched {primary_count}; {len(matches)} fallback(s) matched uniquely and {len(ambiguous)} fallback(s) were ambiguous. Make the explicit selector chain resolve to exactly one control.",a["id"],code)
        fallback_index,locator=matches[0]
        details={"activityId":a["id"],"fallbackIndex":fallback_index}
        self.options.audit("browser.selector_fallback",details)
        if logs is not None:
            self._emit({"event":"browser-selector-fallback","activityId":a["id"],"fallbackIndex":fallback_index},logs)
        return locator

    def _desktop_activity(self, a: dict[str, Any], v: dict[str, Any]) -> None:
        if not self.options.allow_desktop:
            raise WorkflowError("Desktop control requires explicit per-run permission", a["id"], "desktop-permission-denied")
        kind=a["type"]
        if kind.startswith("desktop_ui_"):
            try:
                from . import desktop_accessibility
                runtime=desktop_accessibility.status()
                if not runtime.get("available"):
                    raise WorkflowError(runtime.get("reason") or "Windows UI Automation is unavailable",a["id"],"runtime-unavailable")
                title=str(interpolate(a.get("windowTitle",""),v))
                name=a.get("name")
                automation_id=a.get("automationId")
                control_type=a.get("controlType")
                process_id=a.get("processId")
                timeout=min(max(float(a.get("timeoutSeconds",10)),1),120)
                def state() -> dict[str,bool] | None:
                    self._check_cancel()
                    return desktop_accessibility.control_state(title,name,automation_id,control_type,process_id)
                desired={"desktop_ui_wait":a.get("state","exists"),
                         "desktop_ui_click":"enabled","desktop_ui_fill":"enabled",
                         "desktop_ui_text":"exists"}[kind]
                deadline=time.monotonic()+timeout
                observed=None
                while True:
                    observed=state()
                    ready=(observed is not None if desired=="exists" else
                           observed is None or not observed["visible"] if desired=="not_visible" else
                           observed is not None and observed.get(desired,False))
                    if ready:break
                    remaining=deadline-time.monotonic()
                    if remaining<=0:
                        selector=f"window={title!r}, name={name!r}, automationId={automation_id!r}, controlType={control_type!r}"
                        raise WorkflowError(f"Timed out after {timeout:g}s waiting for UIA {desired}: {selector}",a["id"],"desktop-uia-timeout")
                    time.sleep(min(0.2,remaining))
                if kind=="desktop_ui_wait":return
                if kind=="desktop_ui_click":desktop_accessibility.click(title,name,automation_id,control_type,process_id)
                elif kind=="desktop_ui_fill":desktop_accessibility.fill(title,name,automation_id,control_type,str(interpolate(a.get("value",""),v)),process_id)
                elif kind=="desktop_ui_text":v[a.get("result","text")]=desktop_accessibility.read_text(title,name,automation_id,control_type,process_id)
                return
            except WorkflowError:
                raise
            except Exception as exc:
                raise WorkflowError(f"Desktop accessibility failed: {type(exc).__name__}: {exc}",a["id"],"desktop-uia-error") from exc
        try:
            import pyautogui
        except ImportError as exc:
            raise WorkflowError("Desktop automation requires the optional PyAutoGUI adapter. See docs/AUTOMATION_ADAPTERS.md", a["id"], "runtime-unavailable") from exc
        if kind=="desktop_screenshot":
            path=self._path(a["path"],v,True);pyautogui.screenshot().save(path)
        elif kind=="desktop_click": pyautogui.click(int(a["x"]),int(a["y"]),clicks=int(a.get("clicks",1)))
        elif kind=="desktop_type": pyautogui.write(str(interpolate(a.get("text",""),v)),interval=float(a.get("interval",0.02)))
        elif kind=="desktop_hotkey": pyautogui.hotkey(*[x.strip() for x in str(a["keys"]).split("+")])
        elif kind=="desktop_press": pyautogui.press(str(a["key"]))
        else: raise WorkflowError(f"Unsupported desktop activity: {kind}",a["id"],"activity-unsupported")


def run_project(project: dict[str, Any], root: Path, workflow: str | None = None, inputs: dict[str, Any] | None = None, options: RunOptions | None = None) -> RunResult:
    engine = WorkflowEngine(project, root, options)
    name = workflow or project.get("main") or next(iter(engine.workflows))
    return engine.run(name, inputs)


def _matches_type(value: Any, declared: str) -> bool:
    return {"any":lambda:True,"string":lambda:isinstance(value,str),"integer":lambda:isinstance(value,int) and not isinstance(value,bool),
        "number":lambda:isinstance(value,(int,float)) and not isinstance(value,bool),"boolean":lambda:isinstance(value,bool),
        "object":lambda:isinstance(value,dict),"array":lambda:isinstance(value,list)}.get(declared,lambda:False)()
