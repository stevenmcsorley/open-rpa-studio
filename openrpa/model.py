from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import math
from pathlib import PureWindowsPath
from decimal import Decimal

FORMAT = "openrpa.workflow"
VERSION = 1


class WorkflowError(ValueError):
    def __init__(self, message: str, activity_id: str | None = None, code: str = "workflow-invalid"):
        super().__init__(message)
        self.activity_id = activity_id
        self.code = code


def load_project(path: str | Path) -> tuple[dict[str, Any], Path]:
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        source = source / "project.json"
    if not source.is_file():
        raise WorkflowError(f"Project file does not exist: {source}", code="project-not-found")
    if source.stat().st_size > 1_000_000:
        raise WorkflowError("Project manifest exceeds 1 MB", code="project-size-limit")
    try:
        project = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"Cannot read project JSON: {exc}", code="project-read-error") from exc
    root = source.parent
    if not isinstance(project, dict) or project.get("format") != "openrpa.project":
        raise WorkflowError("Expected format 'openrpa.project'", code="project-format")
    if project.get("formatVersion") != VERSION:
        raise WorkflowError(f"Unsupported project format version: {project.get('formatVersion')}", code="project-version")
    workflows = project.get("workflows")
    if not isinstance(workflows, dict) or not workflows:
        raise WorkflowError("Project must declare at least one workflow", code="workflows-empty")
    for name, relative in workflows.items():
        if not isinstance(name, str) or not name or not isinstance(relative, str) or not relative:
            raise WorkflowError("Workflow mappings require a non-empty name and relative path", code="workflow-path")
        win_path=PureWindowsPath(relative)
        if "\x00" in relative or win_path.is_absolute() or win_path.drive or any(part==".." for part in relative.replace("\\","/").split("/")):
            raise WorkflowError(f"Workflow path is not a safe project-relative path: {relative}", code="workflow-path")
        target = (root / relative).resolve()
        try: target.relative_to(root)
        except ValueError as exc: raise WorkflowError(f"Workflow path escapes project root: {relative}", code="workflow-path") from exc
        if not target.is_file():
            raise WorkflowError(f"Workflow file does not exist: {relative}", code="workflow-not-found")
        if target.stat().st_size > 10_000_000:
            raise WorkflowError(f"Workflow file exceeds 10 MB: {relative}", code="workflow-size-limit")
        try:
            workflow=json.loads(target.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError) as exc:
            raise WorkflowError(f"Cannot read workflow {name}: {exc}",code="workflow-read-error") from exc
        problems=validate_workflow(workflow,set(workflows))
        if problems:
            first=problems[0]
            raise WorkflowError(f"{name}: {first['message']}",first.get("activityId"),first["code"])
    if project.get("main") not in workflows:
        raise WorkflowError("Project main workflow must refer to a declared workflow",code="workflow-main")
    return project, root


def validate_workflow(workflow: dict[str, Any], known_workflows: set[str] | None = None) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if not isinstance(workflow, dict) or workflow.get("format") != FORMAT:
        return [{"code": "workflow-format", "message": f"Expected format '{FORMAT}'"}]
    if workflow.get("formatVersion") != VERSION:
        problems.append({"code": "workflow-version", "message": f"Unsupported workflow version: {workflow.get('formatVersion')}"})
    if not isinstance(workflow.get("name"), str) or not workflow["name"].strip():
        problems.append({"code": "workflow-name", "message": "Workflow needs a name"})
    activities = workflow.get("activities")
    if not isinstance(activities, list):
        return problems + [{"code": "activities-type", "message": "activities must be an array"}]
    seen: set[str] = set()
    activity_count = 0
    def check(items: list[Any], scope: str = "activities", depth: int = 0) -> None:
        nonlocal activity_count
        if depth > 40:
            problems.append({"code":"workflow-depth","message":"Workflow nesting exceeds 40 levels"})
            return
        for i, item in enumerate(items):
            activity_count += 1
            if activity_count > 10_000:
                problems.append({"code":"activity-limit","message":"Workflow exceeds 10,000 activities"})
                return
            if not isinstance(item, dict):
                problems.append({"code": "activity-type", "message": f"{scope}[{i}] must be an object"})
                continue
            aid = item.get("id")
            typ = item.get("type")
            if not isinstance(aid, str) or not aid:
                problems.append({"code": "activity-id", "message": f"{scope}[{i}] needs a non-empty id"})
            elif aid in seen:
                problems.append({"code": "activity-id-duplicate", "message": f"Duplicate activity id: {aid}", "activityId": aid})
            else:
                seen.add(aid)
            if not isinstance(typ, str) or not typ:
                problems.append({"code": "activity-type-missing", "message": f"{scope}[{i}] needs a type", "activityId": str(aid or "")})
            if item.get("breakpointCondition") is not None:
                condition = item.get("breakpointCondition")
                if item.get("breakpoint") is not True:
                    problems.append({"code": "breakpoint-condition-disabled", "message": "A conditional breakpoint requires the activity breakpoint to be enabled", "activityId": str(aid or "")})
                elif not isinstance(condition, str) or len(condition) > 2048:
                    problems.append({"code": "breakpoint-condition", "message": "Breakpoint condition must be text no longer than 2,048 characters", "activityId": str(aid or "")})
            if typ == "if":
                if not isinstance(item.get("condition"), str):
                    problems.append({"code": "if-condition", "message": "If activity needs a condition expression", "activityId": str(aid or "")})
                for branch in ("then", "else"):
                    if not isinstance(item.get(branch, []), list):
                        problems.append({"code": "if-branch", "message": f"If {branch} branch must be an array", "activityId": str(aid or "")})
                    else:
                        check(item.get(branch, []), f"{scope}[{i}].{branch}", depth+1)
            elif typ == "for_each":
                if not isinstance(item.get("items"), str) or not isinstance(item.get("itemName"), str):
                    problems.append({"code": "loop-config", "message": "For Each needs items expression and itemName", "activityId": str(aid or "")})
                if not isinstance(item.get("body", []), list):
                    problems.append({"code": "loop-body", "message": "For Each body must be an array", "activityId": str(aid or "")})
                else:
                    check(item.get("body", []), f"{scope}[{i}].body", depth+1)
            elif typ == "while":
                if not isinstance(item.get("condition"),str):
                    problems.append({"code":"while-condition","message":"While needs a condition expression","activityId":str(aid or "")})
                if not isinstance(item.get("body",[]),list):
                    problems.append({"code":"while-body","message":"While body must be an array","activityId":str(aid or "")})
                else:
                    check(item.get("body",[]),f"{scope}[{i}].body",depth+1)
            elif typ == "retry":
                attempts=item.get("maxAttempts")
                if not isinstance(attempts,int) or isinstance(attempts,bool) or not 1<=attempts<=10:
                    problems.append({"code":"retry-attempts","message":"Retry maxAttempts must be an integer from 1 to 10","activityId":str(aid or "")})
                elif attempts>1 and item.get("repeatSafe") is not True:
                    problems.append({"code":"retry-safety","message":"Mark the retry body as safe to repeat before allowing multiple attempts","activityId":str(aid or "")})
                delay=item.get("delaySeconds")
                if not isinstance(delay,(int,float)) or isinstance(delay,bool) or not math.isfinite(delay) or not 0<=delay<=60:
                    problems.append({"code":"retry-delay","message":"Retry delaySeconds must be between 0 and 60","activityId":str(aid or "")})
                factor=item.get("backoffFactor")
                if not isinstance(factor,(int,float)) or isinstance(factor,bool) or not math.isfinite(factor) or not 1<=factor<=5:
                    problems.append({"code":"retry-backoff","message":"Retry backoffFactor must be between 1 and 5","activityId":str(aid or "")})
                retry_on=item.get("retryOn")
                if not isinstance(retry_on,list) or len(retry_on)>50 or any(not isinstance(code,str) or not code or len(code)>100 for code in retry_on):
                    problems.append({"code":"retry-codes","message":"Retry retryOn must be an array of up to 50 non-empty error codes","activityId":str(aid or "")})
                elif isinstance(attempts,int) and not isinstance(attempts,bool) and attempts>1 and not retry_on:
                    problems.append({"code":"retry-codes-empty","message":"List at least one retryable error code before enabling multiple attempts","activityId":str(aid or "")})
                if not isinstance(item.get("body"),list):
                    problems.append({"code":"retry-body","message":"Retry body must be an array","activityId":str(aid or "")})
                else:
                    check(item["body"],f"{scope}[{i}].body",depth+1)
            elif typ == "switch":
                if not isinstance(item.get("expression"),str):
                    problems.append({"code":"switch-expression","message":"Switch needs an expression","activityId":str(aid or "")})
                cases=item.get("cases")
                if not isinstance(cases,list):
                    problems.append({"code":"switch-cases","message":"Switch cases must be an array","activityId":str(aid or "")})
                    cases=[]
                elif len(cases)>100:
                    problems.append({"code":"switch-case-limit","message":"Switch supports at most 100 cases","activityId":str(aid or "")})
                seen_case_values:set[str]=set()
                for case_index,case in enumerate(cases[:100]):
                    if not isinstance(case,dict) or "value" not in case:
                        problems.append({"code":"switch-case","message":f"Switch case {case_index+1} needs a value and activities array","activityId":str(aid or "")})
                        continue
                    value=case["value"]
                    if value is not None and not isinstance(value,(str,bool,int,float)):
                        problems.append({"code":"switch-case-value","message":f"Switch case {case_index+1} value must be a JSON scalar","activityId":str(aid or "")})
                    try:
                        if isinstance(value,(int,float)) and not isinstance(value,bool):
                            number=Decimal(str(value)).normalize()
                            if not number.is_finite(): raise ValueError("Switch case numbers must be finite")
                            canonical=f"number:{Decimal(0) if number==0 else number}"
                        else:
                            canonical=json.dumps(value,sort_keys=True,allow_nan=False,separators=(",",":"))
                    except (TypeError,ValueError):
                        canonical=f"invalid:{case_index}"
                        problems.append({"code":"switch-case-value","message":f"Switch case {case_index+1} value is not finite JSON","activityId":str(aid or "")})
                    if canonical in seen_case_values:
                        problems.append({"code":"switch-case-duplicate","message":f"Duplicate Switch case value: {value!r}","activityId":str(aid or "")})
                    seen_case_values.add(canonical)
                    branch=case.get("activities")
                    if not isinstance(branch,list):
                        problems.append({"code":"switch-case-activities","message":f"Switch case {case_index+1} activities must be an array","activityId":str(aid or "")})
                    else:
                        check(branch,f"{scope}[{i}].cases[{case_index}].activities",depth+1)
                default=item.get("default")
                if not isinstance(default,list):
                    problems.append({"code":"switch-default","message":"Switch default branch must be an array","activityId":str(aid or "")})
                else:
                    check(default,f"{scope}[{i}].default",depth+1)
            elif typ == "try":
                for branch in ("body", "catch", "finally"):
                    if not isinstance(item.get(branch, []), list):
                        problems.append({"code":"try-branch","message":f"Try {branch} branch must be an array","activityId":str(aid or "")})
                    else:
                        check(item.get(branch, []), f"{scope}[{i}].{branch}", depth+1)
            elif typ == "invoke_workflow":
                target = item.get("workflow")
                if not isinstance(target,str) or not target:
                    problems.append({"code":"workflow-ref","message":"Invoke Workflow needs a workflow name","activityId":str(aid or "")})
                if isinstance(target,str) and known_workflows is not None and target not in known_workflows:
                    problems.append({"code": "workflow-ref", "message": f"Unknown workflow reference: {target}", "activityId": str(aid or "")})
                if "inputs" in item and not isinstance(item["inputs"],dict):
                    problems.append({"code":"argument-inputs","message":"Invoke Workflow inputs must be an object","activityId":str(aid or "")})
                if "outputs" in item and not isinstance(item["outputs"],dict):
                    problems.append({"code":"argument-outputs","message":"Invoke Workflow outputs must be an object","activityId":str(aid or "")})
            elif typ == "xlsx_read":
                if not isinstance(item.get("path"),str) or not item["path"].strip():problems.append({"code":"spreadsheet-path","message":"Spreadsheet Read needs a non-empty path","activityId":str(aid or "")})
                result=item.get("result","rows")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"spreadsheet-result","message":"Spreadsheet Read result must be a variable name","activityId":str(aid or "")})
                header=item.get("headerRow",1)
                if not isinstance(header,int) or isinstance(header,bool) or not 1<=header<=1000:problems.append({"code":"spreadsheet-header-row","message":"Spreadsheet headerRow must be between 1 and 1,000","activityId":str(aid or "")})
                if "dataOnly" in item and not isinstance(item["dataOnly"],bool):problems.append({"code":"spreadsheet-data-only","message":"Spreadsheet dataOnly must be a boolean","activityId":str(aid or "")})
                sheet=item.get("sheetName")
                if sheet is not None and (not isinstance(sheet,str) or not sheet.strip() or len(sheet)>31 or any(char in sheet for char in "[]:?*/" + chr(92))):problems.append({"code":"spreadsheet-sheet-name","message":"Spreadsheet sheetName must be a valid Excel worksheet name of up to 31 characters","activityId":str(aid or "")})
            elif typ == "xlsx_write":
                if not isinstance(item.get("path"),str) or not item["path"].strip():problems.append({"code":"spreadsheet-path","message":"Spreadsheet Write needs a non-empty path","activityId":str(aid or "")})
                if not isinstance(item.get("rows"),(str,list)):problems.append({"code":"spreadsheet-input","message":"Spreadsheet Write rows must be a variable name, expression, or array","activityId":str(aid or "")})
                fields=item.get("fields")
                if fields is not None and (not isinstance(fields,list) or not 1<=len(fields)<=2000 or any(not isinstance(name,str) or not name.strip() for name in fields) or len(set(fields))!=len(fields)):problems.append({"code":"spreadsheet-fields","message":"Spreadsheet fields must be 1–2,000 unique non-empty text names","activityId":str(aid or "")})
                sheet=item.get("sheetName")
                if sheet is not None and (not isinstance(sheet,str) or not sheet.strip() or len(sheet)>31 or any(char in sheet for char in "[]:?*/" + chr(92))):problems.append({"code":"spreadsheet-sheet-name","message":"Spreadsheet sheetName must be a valid Excel worksheet name of up to 31 characters","activityId":str(aid or "")})
            elif typ == "pdf_read_text":
                if not isinstance(item.get("path"),str) or not item["path"].strip():problems.append({"code":"pdf-path","message":"PDF Read Text needs a non-empty path","activityId":str(aid or "")})
                result=item.get("result","text")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"pdf-result","message":"PDF Read Text result must be a variable name","activityId":str(aid or "")})
                count_result=item.get("pageCountResult","pageCount")
                if not isinstance(count_result,str) or not count_result.isidentifier() or count_result==result:problems.append({"code":"pdf-page-count-result","message":"PDF page count result must be a different valid variable name","activityId":str(aid or "")})
                max_pages=item.get("maxPages",500)
                if not isinstance(max_pages,int) or isinstance(max_pages,bool) or not 1<=max_pages<=5000:problems.append({"code":"pdf-page-limit","message":"PDF maximum pages must be between 1 and 5,000","activityId":str(aid or "")})
                if "layoutMode" in item and not isinstance(item["layoutMode"],bool):problems.append({"code":"pdf-layout-mode","message":"PDF layoutMode must be a boolean","activityId":str(aid or "")})
            elif typ == "sqlite_query":
                if not isinstance(item.get("path"),str) or not item["path"].strip():problems.append({"code":"sqlite-path","message":"SQLite Query needs a non-empty database path","activityId":str(aid or "")})
                query=item.get("query")
                if not isinstance(query,str) or not query.strip() or len(query)>100_000:problems.append({"code":"sqlite-query","message":"SQLite Query needs a SQL statement no longer than 100,000 characters","activityId":str(aid or "")})
                result=item.get("result","rows")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"sqlite-result","message":"SQLite Query result must be a variable name","activityId":str(aid or "")})
                parameters=item.get("parameters",[])
                if not isinstance(parameters,(list,dict,str)):problems.append({"code":"sqlite-parameters","message":"SQLite Query parameters must be a list, object, or expression","activityId":str(aid or "")})
                max_rows=item.get("maxRows",10000)
                if not isinstance(max_rows,int) or isinstance(max_rows,bool) or not 1<=max_rows<=100_000:problems.append({"code":"sqlite-row-limit","message":"SQLite Query maxRows must be from 1 to 100,000","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",30)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:problems.append({"code":"sqlite-timeout","message":"SQLite Query timeoutSeconds must be from 1 to 120","activityId":str(aid or "")})
            elif typ not in ACTIVITY_TYPES:
                problems.append({"code": "activity-unsupported", "message": f"Unsupported activity type: {typ}", "activityId": str(aid or "")})
            if typ in {"browser_click","browser_fill","browser_select","browser_check","browser_uncheck","browser_text","browser_wait","browser_assert"}:
                selector_kind=item.get("selectorKind","role")
                if not isinstance(selector_kind,str) or selector_kind not in {"role","label","text","placeholder","test_id","css"}:
                    problems.append({"code":"browser-selector-kind","message":"Browser selectorKind must be role, label, text, placeholder, test_id, or css","activityId":str(aid or "")})
                selector=item.get("selector")
                if not isinstance(selector,str) or not selector.strip() or len(selector)>2048:
                    problems.append({"code":"browser-selector","message":"Browser selector must contain 1–2,048 characters","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",15)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:
                    problems.append({"code":"browser-timeout","message":"Browser timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
                if "exact" in item and not isinstance(item["exact"],bool):
                    problems.append({"code":"browser-exact","message":"Browser exact must be a boolean","activityId":str(aid or "")})
                if typ in {"browser_fill","browser_select"} and not isinstance(item.get("value",""),str):
                    problems.append({"code":"browser-value","message":"Browser Fill/Select value must be a string or expression","activityId":str(aid or "")})
                elif typ=="browser_select" and not item.get("value","").strip():
                    problems.append({"code":"browser-option-value","message":"Browser Select needs an option value or expression","activityId":str(aid or "")})
                if typ=="browser_text" and (not isinstance(item.get("result","text"),str) or not item.get("result","text")):
                    problems.append({"code":"browser-result","message":"Browser Text result must be a non-empty variable name","activityId":str(aid or "")})
                if typ=="browser_wait" and (not isinstance(item.get("state","visible"),str) or item.get("state","visible") not in {"attached","detached","visible","hidden"}):
                    problems.append({"code":"browser-wait-state","message":"Browser Wait state must be attached, detached, visible, or hidden","activityId":str(aid or "")})
                if typ=="browser_assert":
                    assertion=item.get("assertion","visible")
                    if not isinstance(assertion,str) or assertion not in {"visible","hidden","enabled","disabled","checked","text"}:
                        problems.append({"code":"browser-assertion","message":"Browser Assert must check visible, hidden, enabled, disabled, checked, or text","activityId":str(aid or "")})
                    if assertion=="text" and (not isinstance(item.get("expectedText"),str) or not item.get("expectedText")):
                        problems.append({"code":"browser-assert-text","message":"Browser Assert text requires expectedText","activityId":str(aid or "")})
                    if not isinstance(item.get("textMatch","exact"),str) or item.get("textMatch","exact") not in {"exact","contains"}:
                        problems.append({"code":"browser-assert-match","message":"Browser Assert textMatch must be exact or contains","activityId":str(aid or "")})
            elif typ=="browser_navigate":
                if not isinstance(item.get("url"),str) or not item["url"].strip():
                    problems.append({"code":"browser-url","message":"Browser Navigate needs a URL or expression","activityId":str(aid or "")})
                wait_until=item.get("waitUntil","domcontentloaded")
                if not isinstance(wait_until,str) or wait_until not in {"commit","domcontentloaded","load","networkidle"}:
                    problems.append({"code":"browser-wait-until","message":"Browser waitUntil must be commit, domcontentloaded, load, or networkidle","activityId":str(aid or "")})
            elif typ=="browser_launch" and "headless" in item and not isinstance(item["headless"],bool):
                problems.append({"code":"browser-headless","message":"Browser Launch headless must be a boolean","activityId":str(aid or "")})
            if typ in {"desktop_ui_click","desktop_ui_fill","desktop_ui_text","desktop_ui_wait"}:
                window_title=item.get("windowTitle")
                if not isinstance(window_title,str) or not window_title.strip() or len(window_title)>512:
                    problems.append({"code":"desktop-uia-window","message":"UIA activity needs an exact windowTitle of 1–512 characters","activityId":str(aid or "")})
                name=item.get("name","");automation_id=item.get("automationId","")
                if not isinstance(name,str) or len(name)>512:
                    problems.append({"code":"desktop-uia-name","message":"UIA accessible name must be text no longer than 512 characters","activityId":str(aid or "")})
                if not isinstance(automation_id,str) or len(automation_id)>512:
                    problems.append({"code":"desktop-uia-automation-id","message":"UIA Automation ID must be text no longer than 512 characters","activityId":str(aid or "")})
                if isinstance(name,str) and isinstance(automation_id,str) and not name.strip() and not automation_id.strip():
                    problems.append({"code":"desktop-uia-selector","message":"Specify an accessible name or Automation ID for the UIA control","activityId":str(aid or "")})
                control_type=item.get("controlType","")
                if not isinstance(control_type,str) or len(control_type)>128:
                    problems.append({"code":"desktop-uia-control-type","message":"UIA controlType must be text no longer than 128 characters","activityId":str(aid or "")})
                process_id=item.get("processId")
                if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):
                    problems.append({"code":"desktop-uia-process-id","message":"UIA processId must be a positive integer","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",10)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:
                    problems.append({"code":"desktop-uia-timeout","message":"UIA timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
                if typ=="desktop_ui_fill" and (not isinstance(item.get("value"),str) or (control_type and control_type not in {"Edit","Entry"})):
                    problems.append({"code":"desktop-uia-fill","message":"UIA Set Text needs a string value and an Edit control","activityId":str(aid or "")})
                if typ=="desktop_ui_text" and (not isinstance(item.get("result","text"),str) or not item.get("result","text").strip()):
                    problems.append({"code":"desktop-uia-result","message":"UIA Read Text needs a non-empty result variable name","activityId":str(aid or "")})
                if typ=="desktop_ui_wait" and item.get("state","exists") not in {"exists","visible","enabled","not_visible"}:
                    problems.append({"code":"desktop-uia-state","message":"UIA Wait state must be exists, visible, enabled, or not_visible","activityId":str(aid or "")})
    model=workflow.get("executionModel","sequence")
    if model not in {"sequence","flowchart","state_machine"}:
        problems.append({"code":"execution-model","message":"executionModel must be 'sequence', 'flowchart', or 'state_machine'"})
    if model=="sequence":
        check(activities)
    elif model=="flowchart":
        if activities:
            problems.append({"code":"flowchart-sequence-mixed","message":"Flowchart workflows must keep the sequence activities array empty"})
        graph=workflow.get("flowchart")
        if not isinstance(graph,dict):
            problems.append({"code":"flowchart-type","message":"Flowchart workflows need a flowchart object"})
            graph={}
        nodes=graph.get("nodes")
        transitions=graph.get("transitions")
        if not isinstance(nodes,list) or not nodes or len(nodes)>10_000:
            problems.append({"code":"flowchart-nodes","message":"Flowchart needs between 1 and 10,000 nodes"})
            nodes=[]
        if not isinstance(transitions,list) or len(transitions)>20_000:
            problems.append({"code":"flowchart-transitions","message":"Flowchart transitions must be an array of at most 20,000 entries"})
            transitions=[]
        node_map:dict[str,dict[str,Any]]={}
        starts=[]
        for index,node in enumerate(nodes):
            if not isinstance(node,dict) or not isinstance(node.get("id"),str) or not node["id"]:
                problems.append({"code":"flowchart-node-id","message":f"Flowchart node {index+1} needs a non-empty id"})
                continue
            node_id=node["id"]
            if node_id in node_map or node_id in seen:
                problems.append({"code":"flowchart-node-duplicate","message":f"Duplicate flowchart node id: {node_id}"})
            node_map[node_id]=node
            kind=node.get("kind")
            if kind not in {"start","action","decision","end"}:
                problems.append({"code":"flowchart-node-kind","message":f"Flowchart node {node_id} has an unsupported kind"})
            if "breakpoint" in node and not isinstance(node["breakpoint"],bool):
                problems.append({"code":"flowchart-breakpoint","message":f"Flowchart node {node_id} breakpoint must be a boolean"})
            for coordinate in ("x","y"):
                if coordinate in node and (not isinstance(node[coordinate],(int,float)) or isinstance(node[coordinate],bool) or not math.isfinite(node[coordinate]) or not 0<=node[coordinate]<=10_000):
                    problems.append({"code":"flowchart-position","message":f"Flowchart node {node_id} {coordinate} must be between 0 and 10,000"})
            if kind=="start": starts.append(node_id)
            elif kind=="action":
                action=node.get("activity")
                if not isinstance(action,dict):
                    problems.append({"code":"flowchart-action","message":f"Action node {node_id} needs an activity"})
                else: check([action],f"flowchart.nodes.{node_id}.activity")
            elif kind=="decision" and (not isinstance(node.get("condition"),str) or not node["condition"].strip()):
                problems.append({"code":"flowchart-condition","message":f"Decision node {node_id} needs a condition expression"})
        for node_id in node_map:
            if node_id in seen: problems.append({"code":"flowchart-node-activity-duplicate","message":f"Flowchart node id conflicts with an activity id: {node_id}"})
        if len(starts)!=1 or graph.get("start") not in starts:
            problems.append({"code":"flowchart-start","message":"Flowchart must declare its single Start node in flowchart.start"})
        elif isinstance(transitions,list):
            incoming={node_id:0 for node_id in node_map};outgoing={node_id:[] for node_id in node_map};seen_edges:set[tuple[str,str]]=set()
            for index,edge in enumerate(transitions):
                if not isinstance(edge,dict) or edge.get("from") not in node_map or edge.get("to") not in node_map:
                    problems.append({"code":"flowchart-transition-target","message":f"Transition {index+1} references an unknown node"})
                    continue
                source=node_map[edge["from"]];when=edge.get("when","always")
                valid_when={"true","false"} if source.get("kind")=="decision" else {"always"}
                if when not in valid_when:
                    problems.append({"code":"flowchart-transition-condition","message":f"Transition from {edge['from']} has an invalid condition"})
                key=(edge["from"],str(when))
                if key in seen_edges: problems.append({"code":"flowchart-transition-duplicate","message":f"Duplicate {when} transition from {edge['from']}"})
                seen_edges.add(key);outgoing[edge["from"]].append(edge);incoming[edge["to"]]+=1
            for node_id,node in node_map.items():
                edges=outgoing[node_id];kind=node.get("kind")
                if kind=="start" and (len(edges)!=1 or edges[0].get("when","always")!="always"):
                    problems.append({"code":"flowchart-start-edge","message":f"Start node {node_id} needs exactly one outgoing transition"})
                elif kind=="action" and len(edges)!=1:
                    problems.append({"code":"flowchart-action-edges","message":f"Action node {node_id} needs exactly one outgoing transition"})
                elif kind=="decision" and {edge.get("when") for edge in edges}!={"true","false"}:
                    problems.append({"code":"flowchart-decision-edges","message":f"Decision node {node_id} needs one true and one false transition"})
                elif kind=="end" and edges:
                    problems.append({"code":"flowchart-end-edges","message":f"End node {node_id} cannot have outgoing transitions"})
                if kind=="start" and incoming.get(node_id):
                    problems.append({"code":"flowchart-start-incoming","message":f"Start node {node_id} cannot have incoming transitions"})
            if not any(node.get("kind")=="end" for node in node_map.values()):
                problems.append({"code":"flowchart-end-missing","message":"Flowchart needs at least one End node"})
            if graph.get("start") in node_map:
                reachable:set[str]=set();pending=[graph["start"]]
                while pending:
                    current=pending.pop()
                    if current in reachable:continue
                    reachable.add(current);pending.extend(edge["to"] for edge in outgoing.get(current,[]))
                for node_id in node_map.keys()-reachable:
                    problems.append({"code":"flowchart-unreachable","message":f"Flowchart node {node_id} is unreachable from Start"})
    elif model=="state_machine":
        if activities:
            problems.append({"code":"state-machine-sequence-mixed","message":"State-machine workflows must keep the sequence activities array empty"})
        machine=workflow.get("stateMachine")
        if not isinstance(machine,dict):
            problems.append({"code":"state-machine-type","message":"State-machine workflows need a stateMachine object"})
            machine={}
        states=machine.get("states")
        transitions=machine.get("transitions")
        if not isinstance(states,list) or not states or len(states)>1000:
            problems.append({"code":"state-machine-states","message":"State machine needs between 1 and 1,000 states"});states=[]
        if not isinstance(transitions,list) or len(transitions)>5000:
            problems.append({"code":"state-machine-transitions","message":"State machine transitions must be an array of at most 5,000 entries"});transitions=[]
        state_map:dict[str,dict[str,Any]]={}
        for index,state in enumerate(states):
            if not isinstance(state,dict) or not isinstance(state.get("id"),str) or not state["id"].strip():
                problems.append({"code":"state-machine-state-id","message":f"State {index+1} needs a non-empty id"});continue
            state_id=state["id"]
            if state_id in state_map or state_id in seen:problems.append({"code":"state-machine-state-duplicate","message":f"Duplicate state id: {state_id}"})
            seen.add(state_id)
            state_map[state_id]=state
            if "breakpoint" in state and not isinstance(state["breakpoint"],bool):problems.append({"code":"state-machine-breakpoint","message":f"State {state_id} breakpoint must be a boolean"})
            if "final" in state and not isinstance(state["final"],bool):problems.append({"code":"state-machine-final","message":f"State {state_id} final must be a boolean"})
            if not isinstance(state.get("label",state_id),str):problems.append({"code":"state-machine-label","message":f"State {state_id} label must be text"})
            state_activities=state.get("activities",[])
            if not isinstance(state_activities,list):problems.append({"code":"state-machine-activities","message":f"State {state_id} activities must be an array"})
            else:check(state_activities,f"stateMachine.states.{state_id}.activities")
        initial=machine.get("initial")
        if initial not in state_map:problems.append({"code":"state-machine-initial","message":"State machine initial must refer to a declared state"})
        outgoing:dict[str,list[dict[str,Any]]]={state_id:[] for state_id in state_map}
        for index,transition in enumerate(transitions):
            if not isinstance(transition,dict) or transition.get("from") not in state_map or transition.get("to") not in state_map:
                problems.append({"code":"state-machine-transition-target","message":f"Transition {index+1} refers to an unknown state"});continue
            source=transition["from"];condition=transition.get("condition")
            if condition is not None and (not isinstance(condition,str) or not condition.strip()):problems.append({"code":"state-machine-condition","message":f"Transition from {source} condition must be non-empty text"})
            outgoing[source].append(transition)
        for state_id,state in state_map.items():
            edges=outgoing[state_id]
            if state.get("final",False) and edges:problems.append({"code":"state-machine-final-edges","message":f"Final state {state_id} cannot have outgoing transitions"})
            if not state.get("final",False) and not edges:problems.append({"code":"state-machine-no-transition","message":f"Non-final state {state_id} needs at least one outgoing transition"})
            unconditional=[i for i,edge in enumerate(edges) if edge.get("condition") is None]
            if len(unconditional)>1 or (unconditional and unconditional[0]!=len(edges)-1):problems.append({"code":"state-machine-fallback-order","message":f"State {state_id} may have one unconditional fallback, and it must be last"})
        if initial in state_map:
            reachable:set[str]=set();pending=[initial]
            while pending:
                current=pending.pop()
                if current in reachable:continue
                reachable.add(current);pending.extend(edge["to"] for edge in outgoing.get(current,[]))
            for state_id in state_map.keys()-reachable:problems.append({"code":"state-machine-unreachable","message":f"State {state_id} is unreachable from the initial state"})
        if not any(state.get("final",False) for state in state_map.values()):problems.append({"code":"state-machine-final-missing","message":"State machine needs at least one final state"})
    variables = workflow.get("variables", [])
    if not isinstance(variables, list):
        problems.append({"code": "variables-type", "message": "variables must be an array"})
    else:
        names: set[str] = set()
        for var in variables:
            if not isinstance(var, dict) or not isinstance(var.get("name"), str) or not var["name"]:
                problems.append({"code": "variable-invalid", "message": "Each variable needs a name and optional type/value"})
            elif var["name"] in names:
                problems.append({"code": "variable-duplicate", "message": f"Duplicate variable: {var['name']}"})
            else:
                names.add(var["name"])
                if var.get("type","any") not in {"any","string","integer","number","boolean","object","array"}:
                    problems.append({"code":"variable-type","message":f"Variable '{var['name']}' has unsupported type {var.get('type')}"})
    arguments = workflow.get("arguments", [])
    if not isinstance(arguments,list):
        problems.append({"code":"arguments-type","message":"arguments must be an array"})
    else:
        names=set()
        for arg in arguments:
            if not isinstance(arg,dict) or not isinstance(arg.get("name"),str) or not arg.get("name"):
                problems.append({"code":"argument-invalid","message":"Each argument needs a name"})
            elif arg["name"] in names: problems.append({"code":"argument-duplicate","message":f"Duplicate argument: {arg['name']}"})
            else: names.add(arg["name"])
            if isinstance(arg,dict) and arg.get("direction","in") not in {"in","out","inout"}:
                problems.append({"code":"argument-direction","message":f"Invalid argument direction: {arg.get('direction')}"})
            if isinstance(arg,dict) and arg.get("type","any") not in {"any","string","integer","number","boolean","object","array"}:
                problems.append({"code":"argument-type","message":f"Argument '{arg.get('name')}' has unsupported type {arg.get('type')}"})
            if isinstance(arg,dict) and arg.get("required",True) is not True and arg.get("required",True) is not False:
                problems.append({"code":"argument-required","message":f"Argument '{arg.get('name')}' required must be a boolean"})
    return problems


def validate_workflow_bindings(workflows: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Validate reusable-workflow argument bindings across a whole project."""
    problems: list[dict[str, str]] = []

    def visit(items: Any, owner: str) -> None:
        if not isinstance(items, list):
            return
        for activity in items:
            if not isinstance(activity, dict):
                continue
            if activity.get("type") == "invoke_workflow":
                target = activity.get("workflow")
                child = workflows.get(target) if isinstance(target, str) else None
                if child is not None:
                    declared=child.get("arguments", [])
                    if not isinstance(declared,list): declared=[]
                    arguments = {arg.get("name"): arg for arg in declared if isinstance(arg, dict) and isinstance(arg.get("name"), str)}
                    inputs = activity.get("inputs", {})
                    outputs = activity.get("outputs", {})
                    if isinstance(inputs, dict):
                        for name in inputs:
                            spec = arguments.get(name)
                            if spec is None:
                                problems.append({"workflow": owner, "activityId": str(activity.get("id", "")), "code": "argument-unknown", "message": f"{owner}: Invoke Workflow '{target}' has no argument named '{name}'"})
                            elif spec.get("direction", "in") == "out":
                                problems.append({"workflow": owner, "activityId": str(activity.get("id", "")), "code": "argument-direction", "message": f"{owner}: Output-only argument '{name}' cannot be supplied to '{target}'"})
                            elif not (isinstance(inputs[name],str) and inputs[name].startswith("{{") and inputs[name].endswith("}}")) and not _argument_value_matches(inputs[name],spec.get("type","any")):
                                problems.append({"workflow": owner, "activityId": str(activity.get("id", "")), "code": "argument-type", "message": f"{owner}: Literal input '{name}' does not match the declared type {spec.get('type','any')}"})
                    for name, spec in arguments.items():
                        if spec.get("direction", "in") in {"in", "inout"} and spec.get("required", True) and "default" not in spec and isinstance(inputs, dict) and name not in inputs:
                            problems.append({"workflow": owner, "activityId": str(activity.get("id", "")), "code": "argument-missing", "message": f"{owner}: Required input '{name}' is not mapped for '{target}'"})
                    if isinstance(outputs, dict):
                        for name, destination in outputs.items():
                            spec = arguments.get(name)
                            if spec is None or spec.get("direction", "in") not in {"out", "inout"}:
                                problems.append({"workflow": owner, "activityId": str(activity.get("id", "")), "code": "argument-output", "message": f"{owner}: '{name}' is not an output argument of '{target}'"})
                            elif not isinstance(destination, str) or not destination.isidentifier() or len(destination) > 256:
                                problems.append({"workflow": owner, "activityId": str(activity.get("id", "")), "code": "argument-output-target", "message": f"{owner}: Output '{name}' needs a valid caller variable name"})
            for branch in ("then", "else", "body", "catch", "finally", "default"):
                visit(activity.get(branch), owner)
            for case in activity.get("cases", []) if isinstance(activity.get("cases", []), list) else []:
                if isinstance(case, dict):
                    visit(case.get("activities"), owner)

    for owner, workflow in workflows.items():
        visit(workflow.get("activities"), owner)
        graph = workflow.get("flowchart", {})
        for node in graph.get("nodes", []) if isinstance(graph, dict) else []:
            if isinstance(node, dict) and isinstance(node.get("activity"), dict):
                visit([node["activity"]], owner)
        machine = workflow.get("stateMachine", {})
        for state in machine.get("states", []) if isinstance(machine, dict) else []:
            if isinstance(state, dict):
                visit(state.get("activities"), owner)
    return problems


def _argument_value_matches(value: Any, declared: str) -> bool:
    return {"any":lambda:True,"string":lambda:isinstance(value,str),"integer":lambda:isinstance(value,int) and not isinstance(value,bool),
        "number":lambda:isinstance(value,(int,float)) and not isinstance(value,bool),"boolean":lambda:isinstance(value,bool),
        "object":lambda:isinstance(value,dict),"array":lambda:isinstance(value,list)}.get(declared,lambda:False)()


ACTIVITY_TYPES = {
    "assign", "log", "credential_get", "file_read_text", "file_write_text", "file_copy", "file_list",
    "regex_replace", "regex_match", "csv_read", "csv_write", "xlsx_read", "xlsx_write", "pdf_read_text", "json_parse", "json_write",
    "wait", "http_request", "sqlite_query", "invoke_workflow", "try", "while", "retry", "switch", "file_move", "file_delete", "transform_field",
    "browser_launch", "browser_close", "browser_navigate", "browser_click", "browser_fill", "browser_select", "browser_check", "browser_uncheck", "browser_text", "browser_wait", "browser_assert", "browser_screenshot",
    "desktop_click", "desktop_type", "desktop_hotkey", "desktop_press", "desktop_screenshot",
    "desktop_ui_click", "desktop_ui_fill", "desktop_ui_text", "desktop_ui_wait",
}
