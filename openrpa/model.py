from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import math
import re
from pathlib import PureWindowsPath
from decimal import Decimal
from .desktop_keys import SUPPORTED_DESKTOP_KEYS
from .expressions import ExpressionError, validate_expression

FORMAT = "openrpa.workflow"
VERSION = 1


def _valid_json_pointer(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    if value == "":
        return True
    if not value.startswith("/"):
        return False
    index = 0
    while index < len(value):
        if value[index] == "~":
            if index + 1 >= len(value) or value[index + 1] not in "01":
                return False
            index += 2
        else:
            index += 1
    return True


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
            if typ == "http_paginate":
                url=item.get("url")
                if not isinstance(url,str) or not url.strip() or len(url)>8192:
                    problems.append({"code":"api-url","message":"Paginated API Read needs a URL or expression of at most 8,192 characters","activityId":str(aid or "")})
                for field_name, default in (("pageParam","page"),("pageSizeParam","limit"),("itemsPath","data.items")):
                    value=item.get(field_name,default)
                    if not isinstance(value,str) or len(value)>512 or (field_name!="itemsPath" and value and not value.replace("_", "a").isalnum()):
                        problems.append({"code":"api-pagination-field","message":f"Paginated API Read {field_name} must be bounded text using letters, numbers, and underscores","activityId":str(aid or "")})
                if item.get("pageParam","page") and item.get("pageParam","page")==item.get("pageSizeParam","limit"):
                    problems.append({"code":"api-pagination-params","message":"Page number and page size parameters must be different","activityId":str(aid or "")})
                headers=item.get("headers",{})
                if not isinstance(headers,dict) or len(headers)>50 or any(not isinstance(k,str) or not k or len(k)>256 or "\r" in k or "\n" in k or not isinstance(v,str) or len(v)>8192 or "\r" in v or "\n" in v for k,v in headers.items()):
                    problems.append({"code":"api-headers","message":"Paginated API Read headers must be an object of at most 50 bounded text values","activityId":str(aid or "")})
                elif any(k.lower() in {"host","content-length","transfer-encoding","connection"} for k in headers):
                    problems.append({"code":"api-header-restricted","message":"Paginated API Read cannot override transport headers","activityId":str(aid or "")})
                for field_name, default, minimum, maximum in (("pageSize",100,1,1000),("maxPages",10,1,50),("maxItems",10_000,1,100_000),("maxTotalBytes",5_000_000,1024,20_000_000)):
                    value=item.get(field_name,default)
                    if not isinstance(value,int) or isinstance(value,bool) or not minimum<=value<=maximum:
                        problems.append({"code":"api-limit","message":f"Paginated API Read {field_name} must be an integer from {minimum} to {maximum}","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",20)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=60:
                    problems.append({"code":"api-timeout","message":"Paginated API Read timeoutSeconds must be between 1 and 60","activityId":str(aid or "")})
                for field_name, default, optional in (("result","items",False),("metadataResult","pagination",True)):
                    value=item.get(field_name,default)
                    if not isinstance(value,str) or (optional and value and not value.isidentifier()) or (not optional and not value.isidentifier()):
                        problems.append({"code":"api-result","message":f"Paginated API Read {field_name} must be a variable name" if not optional else "Paginated API Read metadataResult must be empty or a variable name","activityId":str(aid or "")})
                if item.get("metadataResult","pagination") and item.get("metadataResult","pagination")==item.get("result","items"):
                    problems.append({"code":"api-result-conflict","message":"Paginated API Read result and metadataResult must use different variables","activityId":str(aid or "")})
            if typ == "api_request":
                connection_id=item.get("connectionId")
                if not isinstance(connection_id,str) or not connection_id or len(connection_id)>64:
                    problems.append({"code":"api-connection-id","message":"API Request requires a saved connection id","activityId":str(aid or "")})
                method=item.get("method","GET")
                if not isinstance(method,str) or method.upper() not in {"GET","POST","PUT","PATCH","DELETE"}:
                    problems.append({"code":"api-method","message":"API Request method must be GET, POST, PUT, PATCH, or DELETE","activityId":str(aid or "")})
                path=item.get("path","/")
                if not isinstance(path,str) or len(path)>8192:
                    problems.append({"code":"api-path","message":"API Request path must be text no longer than 8,192 characters","activityId":str(aid or "")})
                query=item.get("query",{})
                if not isinstance(query,dict) or len(query)>100 or any(not isinstance(key,str) or not key or len(key)>256 for key in query):
                    problems.append({"code":"api-query","message":"API Request query must be an object with at most 100 named parameters","activityId":str(aid or "")})
                headers=item.get("headers",{})
                if not isinstance(headers,dict) or len(headers)>50 or any(not isinstance(key,str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}",key) or not isinstance(value,str) or len(value)>8192 or "\r" in value or "\n" in value for key,value in headers.items()):
                    problems.append({"code":"api-request-headers","message":"API Request headers must use valid HTTP token names and at most 50 bounded single-line text values","activityId":str(aid or "")})
                elif any(key.lower() in {"host","content-length","transfer-encoding","connection","authorization","cookie","set-cookie","proxy-authorization"} or any(term in key.lower() for term in ("token","secret","api-key","api_key","apikey","password","credential")) for key in headers):
                    problems.append({"code":"api-request-header-restricted","message":"API Request cannot contain authentication, credential, or transport headers; configure credentials on the saved connection","activityId":str(aid or "")})
                for field_name,source,maximum in (("omitEmptyQuery",query,100),("omitEmptyHeaders",headers,50)):
                    names=item.get(field_name,[])
                    if not isinstance(names,list) or len(names)>maximum or not isinstance(source,dict) or any(not isinstance(name,str) or not name or name not in source for name in names) or len(set(names))!=len(names):
                        problems.append({"code":"api-optional-parameter","message":f"API Request {field_name} must list unique names present in its configured parameters","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",20)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=60:
                    problems.append({"code":"api-request-timeout","message":"API Request timeoutSeconds must be between 1 and 60","activityId":str(aid or "")})
                max_bytes=item.get("maxResponseBytes",5_000_000)
                if not isinstance(max_bytes,int) or isinstance(max_bytes,bool) or not 1<=max_bytes<=20_000_000:
                    problems.append({"code":"api-request-size","message":"API Request maxResponseBytes must be from 1 to 20,000,000","activityId":str(aid or "")})
                result=item.get("result","response")
                if not isinstance(result,str) or not result.isidentifier():
                    problems.append({"code":"api-request-result","message":"API Request result must be a variable name","activityId":str(aid or "")})
                mapping=item.get("responseMapping")
                pagination=item.get("pagination")
                if pagination is not None:
                    if not isinstance(pagination,dict):
                        problems.append({"code":"api-pagination","message":"API Request pagination must be an object","activityId":str(aid or "")})
                    else:
                        strategy=pagination.get("strategy")
                        if strategy not in {"cursor","next_link"}:
                            problems.append({"code":"api-pagination-strategy","message":"API Request pagination strategy must be cursor or next_link","activityId":str(aid or "")})
                        if not isinstance(method,str) or method.upper()!="GET" or item.get("body") is not None:
                            problems.append({"code":"api-pagination-method","message":"API Request pagination supports GET requests without a body","activityId":str(aid or "")})
                        for field_name in ("itemsPointer", "cursorPointer", "nextLinkPointer"):
                            pointer=pagination.get(field_name)
                            required=field_name=="itemsPointer" or (strategy=="cursor" and field_name=="cursorPointer") or (strategy=="next_link" and field_name=="nextLinkPointer")
                            if required and not _valid_json_pointer(pointer):
                                problems.append({"code":"api-pagination-pointer","message":f"API pagination {field_name} must be an RFC 6901 JSON Pointer","activityId":str(aid or "")})
                        for field_name in ("cursorParam",):
                            value=pagination.get(field_name)
                            if strategy=="cursor" and (not isinstance(value,str) or not value or len(value)>256):
                                problems.append({"code":"api-pagination-param","message":"Cursor pagination cursorParam must be 1–256 characters","activityId":str(aid or "")})
                        for field_name, default, minimum, maximum in (("maxPages",10,1,50),("maxItems",10000,1,100000),("maxTotalBytes",5000000,1024,20000000)):
                            value=pagination.get(field_name,default)
                            if not isinstance(value,int) or isinstance(value,bool) or not minimum<=value<=maximum:
                                problems.append({"code":"api-pagination-limit","message":f"API pagination {field_name} must be an integer from {minimum} to {maximum}","activityId":str(aid or "")})
                        for field_name,default,optional in (("result","items",False),("metadataResult","pagination",True)):
                            value=pagination.get(field_name,default)
                            if not isinstance(value,str) or (optional and value and not value.isidentifier()) or (not optional and not value.isidentifier()):
                                problems.append({"code":"api-pagination-result","message":f"API pagination {field_name} must be a variable name" if not optional else "API pagination metadataResult must be empty or a variable name","activityId":str(aid or "")})
                        names=[result,pagination.get("result","items")]
                        if pagination.get("metadataResult","pagination"):names.append(pagination.get("metadataResult","pagination"))
                        if all(isinstance(value,str) for value in names) and len(set(names))!=len(names):
                            problems.append({"code":"api-pagination-result-conflict","message":"Raw response, paginated items, and pagination metadata need different variable names","activityId":str(aid or "")})
                retry_policy=item.get("retryPolicy")
                if retry_policy is not None:
                    if not isinstance(retry_policy,dict):
                        problems.append({"code":"api-retry-policy","message":"API Request retryPolicy must be an object","activityId":str(aid or "")})
                    else:
                        attempts=retry_policy.get("maxAttempts",1)
                        if not isinstance(attempts,int) or isinstance(attempts,bool) or not 1<=attempts<=5:
                            problems.append({"code":"api-retry-attempts","message":"API Request maxAttempts must be an integer from 1 to 5","activityId":str(aid or "")})
                        delay=retry_policy.get("delaySeconds",0.5)
                        if not isinstance(delay,(int,float)) or isinstance(delay,bool) or not math.isfinite(delay) or not 0<=delay<=10:
                            problems.append({"code":"api-retry-delay","message":"API Request delaySeconds must be between 0 and 10","activityId":str(aid or "")})
                        factor=retry_policy.get("backoffFactor",2)
                        if not isinstance(factor,(int,float)) or isinstance(factor,bool) or not math.isfinite(factor) or not 1<=factor<=3:
                            problems.append({"code":"api-retry-backoff","message":"API Request backoffFactor must be between 1 and 3","activityId":str(aid or "")})
                        if attempts!=1 and (not isinstance(method,str) or method.upper()!="GET" or item.get("body") is not None):
                            problems.append({"code":"api-retry-safety","message":"Automatic API retries are available only for GET requests without a body; DELETE and other methods are never retried","activityId":str(aid or "")})
                if mapping is not None:
                    if not isinstance(mapping,dict):
                        problems.append({"code":"api-response-mapping","message":"API Request responseMapping must be an object","activityId":str(aid or "")})
                    else:
                        response_code=mapping.get("responseCode","")
                        if not isinstance(response_code,str) or response_code and (len(response_code)!=3 or not response_code.isdigit() or response_code[0]!="2"):
                            problems.append({"code":"api-response-code","message":"API response mapping responseCode must be empty or a 2xx status code","activityId":str(aid or "")})
                        items_pointer=mapping.get("itemsPointer","")
                        if not _valid_json_pointer(items_pointer):
                            problems.append({"code":"api-response-pointer","message":"API response itemsPointer must be an RFC 6901 JSON Pointer (empty selects the root)","activityId":str(aid or "")})
                        if isinstance(pagination,dict) and items_pointer!=pagination.get("itemsPointer"):
                            problems.append({"code":"api-pagination-mapping-pointer","message":"When pagination and response mapping are combined, both itemsPointer values must select the same array","activityId":str(aid or "")})
                        output_name=mapping.get("result")
                        if not isinstance(output_name,str) or not output_name.isidentifier():
                            problems.append({"code":"api-response-result","message":"API response mapping result must be a variable name","activityId":str(aid or "")})
                        elif isinstance(result,str) and output_name==result:
                            problems.append({"code":"api-response-result-conflict","message":"API response mapping result must differ from the raw API response variable","activityId":str(aid or "")})
                        elif isinstance(pagination,dict) and output_name in (pagination.get("result","items"),pagination.get("metadataResult","pagination")):
                            problems.append({"code":"api-pagination-mapping-result-conflict","message":"Mapped API response result must differ from raw items and pagination metadata variables","activityId":str(aid or "")})
                        max_items=mapping.get("maxItems",10_000)
                        if not isinstance(max_items,int) or isinstance(max_items,bool) or not 1<=max_items<=10_000:
                            problems.append({"code":"api-response-limit","message":"API response mapping maxItems must be an integer from 1 to 10,000","activityId":str(aid or "")})
                        max_output_bytes=mapping.get("maxOutputBytes",5_000_000)
                        if not isinstance(max_output_bytes,int) or isinstance(max_output_bytes,bool) or not 1_024<=max_output_bytes<=20_000_000:
                            problems.append({"code":"api-response-output-limit","message":"API response mapping maxOutputBytes must be an integer from 1,024 to 20,000,000","activityId":str(aid or "")})
                        fields=mapping.get("fields")
                        if not isinstance(fields,list) or not 1<=len(fields)<=50:
                            problems.append({"code":"api-response-fields","message":"API response mapping needs 1 to 50 field mappings","activityId":str(aid or "")})
                        else:
                            field_names:set[str]=set()
                            for field in fields:
                                if not isinstance(field,dict):
                                    problems.append({"code":"api-response-field","message":"Each API response field must be an object","activityId":str(aid or "")});continue
                                name=field.get("name");pointer=field.get("path");expression=field.get("expression")
                                if not isinstance(name,str) or not name.isidentifier() or len(name)>100:
                                    problems.append({"code":"api-response-field-name","message":"API response field name must be a variable-style identifier up to 100 characters","activityId":str(aid or "")})
                                elif name.casefold() in field_names:
                                    problems.append({"code":"api-response-field-duplicate","message":"API response field names must be unique ignoring case","activityId":str(aid or "")})
                                else:field_names.add(name.casefold())
                                has_pointer=isinstance(pointer,str)
                                has_expression=isinstance(expression,str)
                                if has_pointer==has_expression:
                                    problems.append({"code":"api-response-field-source","message":"Each API response field must define exactly one JSON Pointer path or safe expression","activityId":str(aid or "")})
                                elif has_pointer and not _valid_json_pointer(pointer):
                                    problems.append({"code":"api-response-field-pointer","message":"API response field path must be an RFC 6901 JSON Pointer","activityId":str(aid or "")})
                                elif has_expression:
                                    try: validate_expression(expression, {"item"})
                                    except ExpressionError as exc: problems.append({"code":"api-response-field-expression","message":f"API response field expression is invalid: {exc}","activityId":str(aid or "")})
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
            elif typ == "filter_rows":
                if not isinstance(item.get("rows","rows"),(str,list)):
                    problems.append({"code":"filter-input","message":"Filter Rows rows must be a variable name, expression, or array","activityId":str(aid or "")})
                conditions=item.get("conditions")
                operators={"equals","not_equals","contains","not_contains","starts_with","ends_with","greater_than","greater_or_equal","less_than","less_or_equal","is_empty","is_not_empty"}
                if not isinstance(conditions,list) or not 1<=len(conditions)<=100:
                    problems.append({"code":"filter-conditions","message":"Filter Rows needs 1–100 conditions","activityId":str(aid or "")})
                else:
                    for condition_index,condition in enumerate(conditions):
                        if not isinstance(condition,dict) or not isinstance(condition.get("field"),str) or not condition["field"].strip() or len(condition["field"])>256 or not isinstance(condition.get("operator"),str) or condition.get("operator") not in operators:
                            problems.append({"code":"filter-condition","message":f"Filter Rows condition {condition_index+1} needs a field and supported operator","activityId":str(aid or "")})
                            continue
                        if condition["operator"] not in {"is_empty","is_not_empty"} and "value" not in condition:
                            problems.append({"code":"filter-value","message":f"Filter Rows condition {condition_index+1} needs a comparison value","activityId":str(aid or "")})
                        try: json.dumps(condition.get("value"),allow_nan=False)
                        except (TypeError,ValueError): problems.append({"code":"filter-value","message":f"Filter Rows condition {condition_index+1} value must be finite JSON data","activityId":str(aid or "")})
                        if "ignoreCase" in condition and not isinstance(condition["ignoreCase"],bool):problems.append({"code":"filter-ignore-case","message":f"Filter Rows condition {condition_index+1} ignoreCase must be boolean","activityId":str(aid or "")})
                if not isinstance(item.get("match","all"),str) or item.get("match","all") not in {"all","any"}:problems.append({"code":"filter-match","message":"Filter Rows match must be 'all' or 'any'","activityId":str(aid or "")})
                result=item.get("result","filteredRows")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"filter-result","message":"Filter Rows result must be a variable name","activityId":str(aid or "")})
            elif typ == "join_rows":
                for field_name,default in (("left","leftRows"),("right","rightRows")):
                    if not isinstance(item.get(field_name,default),(str,list)):problems.append({"code":"join-input","message":f"Join Rows {field_name} input must be a variable name, expression, or array","activityId":str(aid or "")})
                for field_name in ("leftKey","rightKey"):
                    if not isinstance(item.get(field_name),str) or not item[field_name].strip() or len(item[field_name])>256:problems.append({"code":"join-key","message":f"Join Rows {field_name} must be non-empty text of at most 256 characters","activityId":str(aid or "")})
                join_type=item.get("joinType","inner")
                if not isinstance(join_type,str) or join_type not in {"inner","left"}:problems.append({"code":"join-type","message":"Join Rows supports inner or left joins","activityId":str(aid or "")})
                prefix=item.get("rightPrefix","right_")
                if not isinstance(prefix,str) or len(prefix)>128:problems.append({"code":"join-prefix","message":"Join Rows rightPrefix must be text no longer than 128 characters","activityId":str(aid or "")})
                limit=item.get("maxRows",100_000)
                if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100_000:problems.append({"code":"join-limit","message":"Join Rows maxRows must be an integer from 1 to 100,000","activityId":str(aid or "")})
                result=item.get("result","joinedRows")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"join-result","message":"Join Rows result must be a variable name","activityId":str(aid or "")})
            elif typ == "group_rows":
                if not isinstance(item.get("rows","rows"),(str,list)):problems.append({"code":"group-input","message":"Group Rows rows must be a variable name, expression, or array","activityId":str(aid or "")})
                group_by=item.get("groupBy",[])
                if not isinstance(group_by,list) or len(group_by)>100 or any(not isinstance(field,str) or not field.strip() or len(field)>256 for field in group_by) or isinstance(group_by,list) and len(set(group_by))!=len(group_by):problems.append({"code":"group-fields","message":"Group Rows needs up to 100 unique, non-empty group fields","activityId":str(aid or "")})
                aggregations=item.get("aggregations",[])
                if not isinstance(aggregations,list) or len(aggregations)>100:problems.append({"code":"group-aggregations","message":"Group Rows supports up to 100 aggregations","activityId":str(aid or "")})
                else:
                    aliases=set(group_by) if isinstance(group_by,list) and all(isinstance(field,str) for field in group_by) else set()
                    operations={"count_rows","count_values","sum","average","min","max"}
                    for aggregation_index,aggregation in enumerate(aggregations):
                        operation=aggregation.get("operation") if isinstance(aggregation,dict) else None
                        output_name=aggregation.get("as") if isinstance(aggregation,dict) else None
                        if not isinstance(operation,str) or operation not in operations or not isinstance(output_name,str) or not output_name.strip() or len(output_name)>256:problems.append({"code":"group-aggregation","message":f"Group Rows aggregation {aggregation_index+1} needs a supported operation and output field","activityId":str(aid or "")});continue
                        if operation!="count_rows" and (not isinstance(aggregation.get("field"),str) or not aggregation["field"].strip() or len(aggregation["field"])>256):problems.append({"code":"group-aggregation-field","message":f"Group Rows aggregation {aggregation_index+1} needs an input field","activityId":str(aid or "")})
                        if output_name in aliases:problems.append({"code":"group-output-duplicate","message":f"Group Rows output field '{output_name}' is duplicated","activityId":str(aid or "")})
                        aliases.add(output_name)
                max_groups=item.get("maxGroups",100_000)
                if not isinstance(max_groups,int) or isinstance(max_groups,bool) or not 1<=max_groups<=100_000:problems.append({"code":"group-limit","message":"Group Rows maxGroups must be an integer from 1 to 100,000","activityId":str(aid or "")})
                result=item.get("result","groupedRows")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"group-result","message":"Group Rows result must be a variable name","activityId":str(aid or "")})
            elif typ == "sort_rows":
                if not isinstance(item.get("rows","rows"),(str,list)):problems.append({"code":"sort-input","message":"Sort Rows rows must be a variable name, expression, or array","activityId":str(aid or "")})
                keys=item.get("keys",[])
                if not isinstance(keys,list) or not 1<=len(keys)<=50:problems.append({"code":"sort-keys","message":"Sort Rows needs 1–50 sort keys","activityId":str(aid or "")})
                else:
                    fields=[]
                    for key_index,key in enumerate(keys):
                        if not isinstance(key,dict) or not isinstance(key.get("field"),str) or not key["field"].strip() or len(key["field"])>256 or not isinstance(key.get("direction","ascending"),str) or key.get("direction","ascending") not in ("ascending","descending") or not isinstance(key.get("nulls","last"),str) or key.get("nulls","last") not in ("first","last"):
                            problems.append({"code":"sort-key","message":f"Sort Rows key {key_index+1} needs a field, direction and null placement","activityId":str(aid or "")})
                        elif key["field"] in fields:problems.append({"code":"sort-key-duplicate","message":f"Sort Rows field '{key['field']}' is duplicated","activityId":str(aid or "")})
                        else:fields.append(key["field"])
                limit=item.get("maxRows",100_000)
                if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100_000:problems.append({"code":"sort-limit","message":"Sort Rows maxRows must be an integer from 1 to 100,000","activityId":str(aid or "")})
                result=item.get("result","sortedRows")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"sort-result","message":"Sort Rows result must be a variable name","activityId":str(aid or "")})
            elif typ == "map_rows":
                if not isinstance(item.get("rows","rows"),(str,list)):problems.append({"code":"map-input","message":"Map Rows rows must be a variable name, expression, or array","activityId":str(aid or "")})
                mappings=item.get("mappings",[])
                if not isinstance(mappings,list) or not 1<=len(mappings)<=100:problems.append({"code":"map-mappings","message":"Map Rows needs 1–100 field mappings","activityId":str(aid or "")})
                else:
                    fields=set()
                    for mapping_index,mapping in enumerate(mappings):
                        if not isinstance(mapping,dict) or not isinstance(mapping.get("field"),str) or not mapping["field"].strip() or len(mapping["field"])>256 or not isinstance(mapping.get("expression"),str) or not mapping["expression"].strip() or len(mapping["expression"])>4096:
                            problems.append({"code":"map-mapping","message":f"Map Rows mapping {mapping_index+1} needs an output field and expression of at most 4,096 characters","activityId":str(aid or "")})
                        elif mapping["field"] in fields:problems.append({"code":"map-field-duplicate","message":f"Map Rows output field '{mapping['field']}' is duplicated","activityId":str(aid or "")})
                        else:fields.add(mapping["field"])
                limit=item.get("maxRows",100_000)
                if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100_000:problems.append({"code":"map-limit","message":"Map Rows maxRows must be an integer from 1 to 100,000","activityId":str(aid or "")})
                result=item.get("result","mappedRows")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"map-result","message":"Map Rows result must be a variable name","activityId":str(aid or "")})
            elif typ == "distinct_rows":
                if not isinstance(item.get("rows","rows"),(str,list)):problems.append({"code":"distinct-input","message":"Distinct Rows rows must be a variable name, expression, or array","activityId":str(aid or "")})
                keys=item.get("keys",[])
                if not isinstance(keys,list) or not 1<=len(keys)<=100 or any(not isinstance(key,str) or not key.strip() or len(key)>256 for key in keys):problems.append({"code":"distinct-keys","message":"Distinct Rows needs 1–100 non-empty key fields","activityId":str(aid or "")})
                elif len(set(keys))!=len(keys):problems.append({"code":"distinct-key-duplicate","message":"Distinct Rows key fields must be unique","activityId":str(aid or "")})
                keep=item.get("keep","first")
                if not isinstance(keep,str) or keep not in {"first","last"}:problems.append({"code":"distinct-keep","message":"Distinct Rows keep must be 'first' or 'last'","activityId":str(aid or "")})
                limit=item.get("maxRows",100_000)
                if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100_000:problems.append({"code":"distinct-limit","message":"Distinct Rows maxRows must be an integer from 1 to 100,000","activityId":str(aid or "")})
                result=item.get("result","distinctRows")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"distinct-result","message":"Distinct Rows result must be a variable name","activityId":str(aid or "")})
            elif typ == "validate_rows":
                if not isinstance(item.get("rows","rows"),(str,list)):problems.append({"code":"validate-input","message":"Validate Rows rows must be a variable name, expression, or array","activityId":str(aid or "")})
                rules=item.get("rules",[]);types={"text","number","boolean","object","array"}
                if not isinstance(rules,list) or not 1<=len(rules)<=100:problems.append({"code":"validate-rules","message":"Validate Rows needs 1–100 field rules","activityId":str(aid or "")})
                else:
                    fields=set()
                    for rule_index,rule in enumerate(rules):
                        if not isinstance(rule,dict) or not isinstance(rule.get("field"),str) or not rule["field"].strip() or len(rule["field"])>256 or not isinstance(rule.get("type"),str) or rule["type"] not in types:
                            problems.append({"code":"validate-rule","message":f"Validate Rows rule {rule_index+1} needs a field and supported type","activityId":str(aid or "")});continue
                        if rule["field"] in fields:problems.append({"code":"validate-field-duplicate","message":f"Validate Rows field '{rule['field']}' is duplicated","activityId":str(aid or "")})
                        fields.add(rule["field"])
                        if "required" in rule and not isinstance(rule["required"],bool):problems.append({"code":"validate-required","message":f"Validate Rows rule {rule_index+1} required must be boolean","activityId":str(aid or "")})
                        if "nonEmpty" in rule and not isinstance(rule["nonEmpty"],bool):problems.append({"code":"validate-non-empty","message":f"Validate Rows rule {rule_index+1} nonEmpty must be boolean","activityId":str(aid or "")})
                for name,default in (("validResult","validRows"),("invalidResult","invalidRows")):
                    value=item.get(name,default)
                    if not isinstance(value,str) or not value.isidentifier():problems.append({"code":"validate-result","message":f"Validate Rows {name} must be a variable name","activityId":str(aid or "")})
                if item.get("validResult","validRows")==item.get("invalidResult","invalidRows"):problems.append({"code":"validate-result-duplicate","message":"Validate Rows result variables must be different","activityId":str(aid or "")})
                limit=item.get("maxRows",100_000)
                if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100_000:problems.append({"code":"validate-limit","message":"Validate Rows maxRows must be an integer from 1 to 100,000","activityId":str(aid or "")})
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
            elif typ == "image_ocr":
                if not isinstance(item.get("path"),str) or not item["path"].strip():problems.append({"code":"ocr-path","message":"OCR Image needs a non-empty image path","activityId":str(aid or "")})
                result=item.get("result","recognizedText")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"ocr-result","message":"OCR Image result must be a variable name","activityId":str(aid or "")})
                language=item.get("language","eng")
                if not isinstance(language,str) or not 1<=len(language)<=64 or any(not (character.isascii() and (character.isalnum() or character in "_+.-")) for character in language):problems.append({"code":"ocr-language","message":"OCR Image language must be a 1–64 character Tesseract language identifier","activityId":str(aid or "")})
                psm=item.get("pageSegmentationMode",3)
                if not isinstance(psm,int) or isinstance(psm,bool) or not 0<=psm<=13:problems.append({"code":"ocr-psm","message":"OCR Image pageSegmentationMode must be an integer from 0 to 13","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",60)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=300:problems.append({"code":"ocr-timeout","message":"OCR Image timeoutSeconds must be from 1 to 300","activityId":str(aid or "")})
            elif typ == "desktop_ocr_click":
                title=item.get("windowTitle")
                if not isinstance(title,str) or not title.strip() or len(title)>512:problems.append({"code":"desktop-ocr-window","message":"OCR Click needs an exact visible windowTitle of 1–512 characters","activityId":str(aid or "")})
                target=item.get("text")
                if not isinstance(target,str) or not target.strip() or len(target)>512:problems.append({"code":"desktop-ocr-text","message":"OCR Click text must contain 1–512 characters","activityId":str(aid or "")})
                process_id=item.get("processId")
                if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):problems.append({"code":"desktop-ocr-process-id","message":"OCR Click processId must be a positive integer","activityId":str(aid or "")})
                confidence=item.get("confidenceThreshold",80)
                if not isinstance(confidence,int) or isinstance(confidence,bool) or not 0<=confidence<=100:problems.append({"code":"desktop-ocr-confidence","message":"OCR Click confidenceThreshold must be an integer from 0 to 100","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",15)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=60:problems.append({"code":"desktop-ocr-timeout","message":"OCR Click timeoutSeconds must be from 1 to 60","activityId":str(aid or "")})
                result=item.get("result","ocrMatch")
                if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"desktop-ocr-result","message":"OCR Click result must be a variable name","activityId":str(aid or "")})
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
            if typ in {"browser_click","browser_hover","browser_press","browser_upload","browser_download","browser_fill","browser_select","browser_select_many","browser_check","browser_uncheck","browser_text","browser_extract_records","browser_table_read","browser_wait","browser_assert"}:
                selector_kind=item.get("selectorKind","role")
                if not isinstance(selector_kind,str) or selector_kind not in {"role","label","text","placeholder","test_id","css"}:
                    problems.append({"code":"browser-selector-kind","message":"Browser selectorKind must be role, label, text, placeholder, test_id, or css","activityId":str(aid or "")})
                selector=item.get("selector")
                if not isinstance(selector,str) or not selector.strip() or len(selector)>2048:
                    problems.append({"code":"browser-selector","message":"Browser selector must contain 1–2,048 characters","activityId":str(aid or "")})
                frame_selector=item.get("frameSelector")
                if frame_selector is not None and (not isinstance(frame_selector,str) or len(frame_selector)>2048 or "\x00" in frame_selector or (frame_selector and not frame_selector.strip())):
                    problems.append({"code":"browser-frame-selector","message":"frameSelector must be empty or a CSS selector of at most 2,048 characters","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",15)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:
                    problems.append({"code":"browser-timeout","message":"Browser timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
                if "exact" in item and not isinstance(item["exact"],bool):
                    problems.append({"code":"browser-exact","message":"Browser exact must be a boolean","activityId":str(aid or "")})
                healing=item.get("selectorHealing","off")
                if not isinstance(healing,str) or healing not in {"off","accessible_role"}:
                    problems.append({"code":"browser-selector-healing","message":"selectorHealing must be off or accessible_role","activityId":str(aid or "")})
                elif healing=="accessible_role" and (selector_kind!="role" or item.get("exact",True) is not True):
                    problems.append({"code":"browser-selector-healing-scope","message":"Accessible selector recovery requires an exact role selector such as button:Save","activityId":str(aid or "")})
                fallbacks=item.get("selectorFallbacks",[])
                if not isinstance(fallbacks,list) or len(fallbacks)>10:
                    problems.append({"code":"browser-selector-fallbacks","message":"selectorFallbacks must be a list of at most 10 explicit selectors","activityId":str(aid or "")})
                else:
                    selector_seen={(selector_kind if isinstance(selector_kind,str) else "",selector.strip() if isinstance(selector,str) else "",bool(item.get("exact",True)))}
                    for fallback in fallbacks:
                        if not isinstance(fallback,dict) or set(fallback)-{"selectorKind","selector","exact"}:
                            problems.append({"code":"browser-selector-fallback","message":"Each fallback must contain only selectorKind, selector, and optional exact","activityId":str(aid or "")});continue
                        fk=fallback.get("selectorKind");fs=fallback.get("selector");fe=fallback.get("exact",True)
                        if not isinstance(fk,str) or fk not in {"role","label","text","placeholder","test_id","css"} or not isinstance(fs,str) or not fs.strip() or len(fs)>2048 or not isinstance(fe,bool):
                            problems.append({"code":"browser-selector-fallback","message":"Fallback selector kind, selector, or exact flag is invalid","activityId":str(aid or "")});continue
                        candidate=(fk,fs.strip(),fe)
                        if candidate in selector_seen:
                            problems.append({"code":"browser-selector-fallback-duplicate","message":"Fallback selectors must be distinct from the primary selector and each other","activityId":str(aid or "")})
                        selector_seen.add(candidate)
                if typ in {"browser_fill","browser_select"} and not isinstance(item.get("value",""),str):
                    problems.append({"code":"browser-value","message":"Browser Fill/Select value must be a string or expression","activityId":str(aid or "")})
                elif typ=="browser_select" and not item.get("value","").strip():
                    problems.append({"code":"browser-option-value","message":"Browser Select needs an option value or expression","activityId":str(aid or "")})
                if typ=="browser_select_many":
                    values=item.get("values")
                    if not isinstance(values,list) or not 1<=len(values)<=100 or any(not isinstance(value,str) or not value or len(value)>1000 for value in values):
                        problems.append({"code":"browser-option-values","message":"Browser Select Multiple needs 1 to 100 non-empty option values, each no longer than 1,000 characters","activityId":str(aid or "")})
                    elif len(set(values))!=len(values):
                        problems.append({"code":"browser-option-values-duplicate","message":"Browser Select Multiple values must be unique","activityId":str(aid or "")})
                    result=item.get("result","selectedValues")
                    if not isinstance(result,str) or not result.isidentifier():problems.append({"code":"browser-select-many-result","message":"Browser Select Multiple result must be a variable name","activityId":str(aid or "")})
                if typ=="browser_press":
                    key=item.get("key","Enter")
                    valid_keys={"Enter","Tab","Escape","Space","ArrowUp","ArrowDown","ArrowLeft","ArrowRight","Home","End","PageUp","PageDown","Backspace","Delete"}
                    if not isinstance(key,str) or key not in valid_keys:
                        problems.append({"code":"browser-key","message":"Browser Press key must be one of Enter, Tab, Escape, Space, ArrowUp/Down/Left/Right, Home, End, PageUp/Down, Backspace, or Delete","activityId":str(aid or "")})
                if typ=="browser_upload":
                    paths=item.get("paths")
                    if not isinstance(paths,list) or not 1<=len(paths)<=20 or any(not isinstance(path,str) or not path.strip() or len(path)>4096 or "\x00" in path for path in paths):
                        problems.append({"code":"browser-upload-paths","message":"Browser Upload needs 1 to 20 non-empty project-relative file paths","activityId":str(aid or "")})
                if typ=="browser_download":
                    path=item.get("path")
                    if not isinstance(path,str) or not path.strip() or len(path)>4096 or "\x00" in path:
                        problems.append({"code":"browser-download-path","message":"Browser Download needs a non-empty destination path of at most 4,096 characters","activityId":str(aid or "")})
                    if not isinstance(item.get("overwrite",False),bool):
                        problems.append({"code":"browser-download-overwrite","message":"Browser Download overwrite must be a boolean","activityId":str(aid or "")})
                    if not isinstance(item.get("result","download"),str) or not item.get("result","download").isidentifier():
                        problems.append({"code":"browser-download-result","message":"Browser Download result must be a variable name","activityId":str(aid or "")})
                if typ=="browser_text" and (not isinstance(item.get("result","text"),str) or not item.get("result","text")):
                    problems.append({"code":"browser-result","message":"Browser Text result must be a non-empty variable name","activityId":str(aid or "")})
                if typ=="browser_table_read":
                    if selector_kind!="css":problems.append({"code":"browser-table-selector","message":"Read Web Table requires a CSS selector for a table element","activityId":str(aid or "")})
                    if not isinstance(item.get("result","rows"),str) or not item.get("result","rows").isidentifier():problems.append({"code":"browser-table-result","message":"Read Web Table result must be a variable name","activityId":str(aid or "")})
                    if not isinstance(item.get("firstRowHeaders",True),bool):problems.append({"code":"browser-table-headers","message":"firstRowHeaders must be a boolean","activityId":str(aid or "")})
                    limits=(("maxRows",1000,5000),("maxColumns",50,100),("maxOutputChars",1_000_000,10_000_000))
                    for field,default,maximum in limits:
                        value=item.get(field,default)
                        if not isinstance(value,int) or isinstance(value,bool) or not 1<=value<=maximum:problems.append({"code":"browser-table-limit","message":f"{field} must be an integer from 1 to {maximum}","activityId":str(aid or "")})
                if typ=="browser_extract_records":
                    if selector_kind!="css":problems.append({"code":"browser-extract-selector","message":"Extract Repeated Web Items requires a CSS selector for the repeated item container","activityId":str(aid or "")})
                    fields=item.get("fields")
                    if not isinstance(fields,list) or not 1<=len(fields)<=50:
                        problems.append({"code":"browser-extract-fields","message":"Extract Repeated Web Items needs 1 to 50 field mappings","activityId":str(aid or "")})
                    else:
                        field_names:set[str]=set()
                        for field in fields:
                            if not isinstance(field,dict) or set(field)-{"name","selector","source","attribute","required","tokenIndex"}:
                                problems.append({"code":"browser-extract-field","message":"Each browser field mapping may contain only name, selector, source, attribute, required, and tokenIndex","activityId":str(aid or "")});continue
                            name=field.get("name");relative=field.get("selector");source=field.get("source","text")
                            if not isinstance(name,str) or not name.isidentifier() or len(name)>100:
                                problems.append({"code":"browser-extract-field-name","message":"Browser field name must be a variable-style identifier up to 100 characters","activityId":str(aid or "")})
                            elif name.casefold() in field_names:
                                problems.append({"code":"browser-extract-field-duplicate","message":"Browser field names must be unique ignoring case","activityId":str(aid or "")})
                            else:field_names.add(name.casefold())
                            if not isinstance(relative,str) or not relative.strip() or len(relative)>2048:
                                problems.append({"code":"browser-extract-field-selector","message":"Each field needs a relative CSS selector of 1–2,048 characters","activityId":str(aid or "")})
                            if not isinstance(source,str) or source not in {"text","attribute"}:
                                problems.append({"code":"browser-extract-source","message":"Browser field source must be text or attribute","activityId":str(aid or "")})
                            attribute=field.get("attribute","")
                            if source=="attribute" and (not isinstance(attribute,str) or not attribute or len(attribute)>128 or not re.fullmatch(r"[A-Za-z_:][A-Za-z0-9:._-]*",attribute)):
                                problems.append({"code":"browser-extract-attribute","message":"Attribute fields need a valid HTML attribute name","activityId":str(aid or "")})
                            if "required" in field and not isinstance(field["required"],bool):
                                problems.append({"code":"browser-extract-required","message":"Field required must be a boolean","activityId":str(aid or "")})
                            token_index=field.get("tokenIndex")
                            if token_index is not None and (source!="attribute" or not isinstance(token_index,int) or isinstance(token_index,bool) or not 0<=token_index<=20):
                                problems.append({"code":"browser-extract-token-index","message":"tokenIndex must be an integer from 0 to 20 and can only be used with an attribute source","activityId":str(aid or "")})
                    if not isinstance(item.get("result","records"),str) or not item.get("result","records").isidentifier():
                        problems.append({"code":"browser-extract-result","message":"Extract Repeated Web Items result must be a variable name","activityId":str(aid or "")})
                    for field,default,maximum in (("maxRecords",500,5000),("maxOutputChars",1000000,10000000)):
                        value=item.get(field,default)
                        if not isinstance(value,int) or isinstance(value,bool) or not 1<=value<=maximum:problems.append({"code":"browser-extract-limit","message":f"{field} must be an integer from 1 to {maximum}","activityId":str(aid or "")})
                    if not isinstance(item.get("append",False),bool):
                        problems.append({"code":"browser-extract-append","message":"Extract Repeated Web Items append must be a boolean","activityId":str(aid or "")})
                    deduplicate_by=item.get("deduplicateBy",[])
                    if not isinstance(deduplicate_by,list) or len(deduplicate_by)>10 or any(not isinstance(name,str) or not name or len(name)>100 for name in deduplicate_by):
                        problems.append({"code":"browser-extract-deduplicate","message":"deduplicateBy must be a list of up to 10 mapped field names","activityId":str(aid or "")})
                    elif len(set(deduplicate_by))!=len(deduplicate_by):
                        problems.append({"code":"browser-extract-deduplicate","message":"deduplicateBy field names must be unique","activityId":str(aid or "")})
                    elif deduplicate_by and not item.get("append",False):
                        problems.append({"code":"browser-extract-deduplicate","message":"Deduplication requires append mode so records can be compared across extracts","activityId":str(aid or "")})
                    elif isinstance(fields,list) and any(name not in {field.get("name") for field in fields if isinstance(field,dict) and isinstance(field.get("name"),str)} for name in deduplicate_by):
                        problems.append({"code":"browser-extract-deduplicate","message":"Every deduplicateBy value must exactly match a mapped field name","activityId":str(aid or "")})
                    for field,default,maximum in (("maxTotalRecords",10000,50000),("maxTotalOutputChars",5000000,10000000)):
                        value=item.get(field,default)
                        if not isinstance(value,int) or isinstance(value,bool) or not 1<=value<=maximum:problems.append({"code":"browser-extract-total-limit","message":f"{field} must be an integer from 1 to {maximum}","activityId":str(aid or "")})
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
            elif typ=="browser_wait_response":
                url_contains=item.get("urlContains")
                if not isinstance(url_contains,str) or not url_contains.strip() or len(url_contains)>2048 or "\x00" in url_contains or "?" in url_contains or "#" in url_contains:
                    problems.append({"code":"browser-response-url","message":"Browser response urlContains must be a non-empty URL/path substring without query strings or fragments (max 2,048 characters)","activityId":str(aid or "")})
                method=item.get("method","any")
                if not isinstance(method,str) or method.lower() not in {"any","get","post","put","patch","delete","head","options"}:
                    problems.append({"code":"browser-response-method","message":"Browser response method must be any, GET, POST, PUT, PATCH, DELETE, HEAD, or OPTIONS","activityId":str(aid or "")})
                status=item.get("status")
                if status is not None and (not isinstance(status,int) or isinstance(status,bool) or not 100<=status<=599):
                    problems.append({"code":"browser-response-status","message":"Browser response status must be null or an integer from 100 to 599","activityId":str(aid or "")})
                for field,default,minimum,maximum in (("maxAgeSeconds",30,1,300),("timeoutSeconds",15,1,120)):
                    value=item.get(field,default)
                    if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or not minimum<=value<=maximum:
                        problems.append({"code":"browser-response-timeout","message":f"{field} must be between {minimum} and {maximum} seconds","activityId":str(aid or "")})
                result=item.get("result","response")
                if not isinstance(result,str) or not result.isidentifier() or len(result)>256:
                    problems.append({"code":"browser-response-result","message":"Browser response result must be a variable name","activityId":str(aid or "")})
                max_response_bytes=item.get("maxResponseBytes",500_000)
                if not isinstance(max_response_bytes,int) or isinstance(max_response_bytes,bool) or not 1<=max_response_bytes<=2_000_000:
                    problems.append({"code":"browser-response-size","message":"Browser response maxResponseBytes must be an integer from 1 to 2,000,000","activityId":str(aid or "")})
                mapping=item.get("jsonMapping")
                discover_schema=item.get("discoverJsonSchema",False)
                if not isinstance(discover_schema,bool):
                    problems.append({"code":"browser-response-schema-discovery","message":"Browser response schema discovery must be a boolean","activityId":str(aid or "")})
                schema_result=item.get("schemaResult","responseSchema")
                if discover_schema:
                    if not isinstance(schema_result,str) or not schema_result.isidentifier() or len(schema_result)>256:
                        problems.append({"code":"browser-response-schema-result","message":"Browser response schema result must be a variable name","activityId":str(aid or "")})
                    elif schema_result==result or (isinstance(mapping,dict) and schema_result==mapping.get("result")):
                        problems.append({"code":"browser-response-schema-result-conflict","message":"Browser response schema result must differ from metadata and mapped-row variables","activityId":str(aid or "")})
                    if mapping is not None:
                        problems.append({"code":"browser-response-schema-mode","message":"Choose either JSON schema discovery or explicit JSON mapping for one response","activityId":str(aid or "")})
                if mapping is not None:
                    if not isinstance(mapping,dict) or set(mapping)-{"itemsPointer","result","maxItems","fields"}:
                        problems.append({"code":"browser-response-mapping","message":"Browser JSON mapping must contain only itemsPointer, result, maxItems, and fields","activityId":str(aid or "")})
                    else:
                        if not _valid_json_pointer(mapping.get("itemsPointer","")):
                            problems.append({"code":"browser-response-pointer","message":"Browser JSON itemsPointer must be an RFC 6901 JSON Pointer","activityId":str(aid or "")})
                        mapped_result=mapping.get("result")
                        if not isinstance(mapped_result,str) or not mapped_result.isidentifier() or len(mapped_result)>256:
                            problems.append({"code":"browser-response-mapping-result","message":"Browser JSON mapping result must be a variable name","activityId":str(aid or "")})
                        elif mapped_result==result:
                            problems.append({"code":"browser-response-mapping-result-conflict","message":"Browser JSON mapped result must differ from the response metadata variable","activityId":str(aid or "")})
                        max_items=mapping.get("maxItems",500)
                        if not isinstance(max_items,int) or isinstance(max_items,bool) or not 1<=max_items<=10_000:
                            problems.append({"code":"browser-response-mapping-limit","message":"Browser JSON mapping maxItems must be an integer from 1 to 10,000","activityId":str(aid or "")})
                        fields=mapping.get("fields")
                        if not isinstance(fields,list) or not 1<=len(fields)<=50:
                            problems.append({"code":"browser-response-mapping-fields","message":"Browser JSON mapping needs 1 to 50 field mappings","activityId":str(aid or "")})
                        else:
                            field_names:set[str]=set()
                            for field in fields:
                                if not isinstance(field,dict) or set(field)-{"name","path"}:
                                    problems.append({"code":"browser-response-mapping-field","message":"Each browser JSON response field must contain only name and path","activityId":str(aid or "")});continue
                                name=field.get("name");pointer=field.get("path")
                                if not isinstance(name,str) or not name.isidentifier() or len(name)>100:
                                    problems.append({"code":"browser-response-mapping-field-name","message":"Browser JSON response field names must be variable-style identifiers up to 100 characters","activityId":str(aid or "")})
                                elif name.casefold() in field_names:
                                    problems.append({"code":"browser-response-mapping-field-duplicate","message":"Browser JSON response field names must be unique ignoring case","activityId":str(aid or "")})
                                else:field_names.add(name.casefold())
                                if not _valid_json_pointer(pointer):
                                    problems.append({"code":"browser-response-mapping-field-pointer","message":"Browser JSON response field path must be an RFC 6901 JSON Pointer","activityId":str(aid or "")})
            elif typ=="browser_launch" and "headless" in item and not isinstance(item["headless"],bool):
                problems.append({"code":"browser-headless","message":"Browser Launch headless must be a boolean","activityId":str(aid or "")})
            elif typ=="browser_launch":
                browser_type=item.get("browserType","chromium")
                channel=item.get("channel","chromium")
                executable=item.get("executablePath","")
                profile_name=item.get("profileName","")
                if not isinstance(profile_name,str) or (profile_name and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}",profile_name)):
                    problems.append({"code":"browser-profile-name","message":"Persistent profile name must be empty or start with a letter and contain only letters, digits, underscores or hyphens (max 40 characters)","activityId":str(aid or "")})
                if not isinstance(browser_type,str) or browser_type not in {"chromium","firefox","webkit"}:
                    problems.append({"code":"browser-engine","message":"Browser Launch browserType must be chromium, firefox, or webkit","activityId":str(aid or "")})
                if not isinstance(channel,str) or channel not in {"chromium","chrome","msedge","custom"}:
                    problems.append({"code":"browser-channel","message":"Chromium channel must be chromium, chrome, msedge, or custom","activityId":str(aid or "")})
                if browser_type!="chromium" and channel!="chromium":
                    problems.append({"code":"browser-channel-engine","message":"Chrome/Edge channels and custom executable paths are supported only with the Chromium engine","activityId":str(aid or "")})
                if channel=="custom" and (not isinstance(executable,str) or not executable.strip() or len(executable)>4096 or "\x00" in executable or not Path(executable).is_absolute()):
                    problems.append({"code":"browser-executable","message":"Custom Chromium needs an absolute executable path of at most 4,096 characters","activityId":str(aid or "")})
                elif channel!="custom" and (not isinstance(executable,str) or executable!=""):
                    problems.append({"code":"browser-executable-channel","message":"Set Chromium channel to custom when configuring executablePath","activityId":str(aid or "")})
            elif typ in {"browser_new_tab","browser_capture_popup","browser_switch_tab","browser_close_tab"}:
                name=item.get("name")
                if not isinstance(name,str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,49}",name):
                    problems.append({"code":"browser-tab-name","message":"Browser tab name must start with a letter and contain only letters, digits, underscores or hyphens (max 50 characters)","activityId":str(aid or "")})
                if typ=="browser_new_tab":
                    url=item.get("url","")
                    if not isinstance(url,str) or len(url)>2048 or "\x00" in url:
                        problems.append({"code":"browser-tab-url","message":"New Browser Tab URL must be a string of at most 2,048 characters","activityId":str(aid or "")})
                if typ=="browser_capture_popup":
                    timeout=item.get("timeoutSeconds",15)
                    if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:
                        problems.append({"code":"browser-popup-timeout","message":"Capture Browser Popup timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
            elif typ=="browser_accessibility_snapshot":
                limit=item.get("maxOutputChars",50000)
                if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=200000:
                    problems.append({"code":"browser-accessibility-limit","message":"Accessibility Snapshot maxOutputChars must be an integer from 1 to 200,000","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",15)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:
                    problems.append({"code":"browser-accessibility-timeout","message":"Accessibility Snapshot timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
                result=item.get("result","accessibilitySnapshot")
                if not isinstance(result,str) or not result.isidentifier():
                    problems.append({"code":"browser-accessibility-result","message":"Accessibility Snapshot result must be a variable name","activityId":str(aid or "")})
            elif typ=="browser_scroll":
                if not isinstance(item.get("direction","down"),str) or item.get("direction","down") not in {"down","up"}:
                    problems.append({"code":"browser-scroll-direction","message":"Scroll direction must be down or up","activityId":str(aid or "")})
                for field,default,minimum,maximum in (("distancePx",600,50,2000),("delayMilliseconds",700,0,5000),("maxSteps",100,1,500)):
                    value=item.get(field,default)
                    if not isinstance(value,int) or isinstance(value,bool) or not minimum<=value<=maximum:
                        problems.append({"code":"browser-scroll-limit","message":f"{field} must be an integer from {minimum} to {maximum}","activityId":str(aid or "")})
                if not isinstance(item.get("toBottom",False),bool):
                    problems.append({"code":"browser-scroll-bottom","message":"toBottom must be a boolean","activityId":str(aid or "")})
                container_selector=item.get("containerSelector","")
                if not isinstance(container_selector,str) or len(container_selector)>2048 or "\x00" in container_selector:
                    problems.append({"code":"browser-scroll-container","message":"Scroll container CSS selector must be text no longer than 2,048 characters","activityId":str(aid or "")})
                elif container_selector.strip()!=container_selector:
                    problems.append({"code":"browser-scroll-container","message":"Scroll container CSS selector must not have leading or trailing whitespace","activityId":str(aid or "")})
                if not isinstance(item.get("result","scrollResult"),str) or not item.get("result","scrollResult").isidentifier():
                    problems.append({"code":"browser-scroll-result","message":"Scroll Page result must be a variable name","activityId":str(aid or "")})
            if typ == "desktop_ui_grid_read":
                window_title=item.get("windowTitle")
                if not isinstance(window_title,str) or not window_title.strip() or len(window_title)>512:problems.append({"code":"desktop-uia-window","message":"UIA grid read needs an exact windowTitle of 1–512 characters","activityId":str(aid or "")})
                name=item.get("name","");automation_id=item.get("automationId","");control_type=item.get("controlType","DataGrid")
                if not isinstance(name,str) or len(name)>512:problems.append({"code":"desktop-uia-name","message":"UIA grid accessible name must be text no longer than 512 characters","activityId":str(aid or "")})
                if not isinstance(automation_id,str) or len(automation_id)>512:problems.append({"code":"desktop-uia-automation-id","message":"UIA grid Automation ID must be text no longer than 512 characters","activityId":str(aid or "")})
                if isinstance(name,str) and isinstance(automation_id,str) and not name.strip() and not automation_id.strip():problems.append({"code":"desktop-uia-selector","message":"Specify an accessible name or Automation ID for the UIA grid","activityId":str(aid or "")})
                if not isinstance(control_type,str) or len(control_type)>128:problems.append({"code":"desktop-uia-control-type","message":"UIA grid controlType must be text no longer than 128 characters","activityId":str(aid or "")})
                for field,default,minimum,maximum in (("maxRows",100,1,500),("maxColumns",30,1,100),("maxOutputChars",50000,1000,500000)):
                    value=item.get(field,default)
                    if not isinstance(value,int) or isinstance(value,bool) or not minimum<=value<=maximum:problems.append({"code":"desktop-uia-grid-limit","message":f"{field} must be an integer from {minimum} to {maximum}","activityId":str(aid or "")})
                if not isinstance(item.get("result","rows"),str) or not item.get("result","rows").isidentifier():problems.append({"code":"desktop-uia-grid-result","message":"UIA grid result must be a variable name","activityId":str(aid or "")})
                metadata_result=item.get("metadataResult","gridMetadata")
                if not isinstance(metadata_result,str) or (metadata_result and not metadata_result.isidentifier()):problems.append({"code":"desktop-uia-grid-metadata-result","message":"UIA grid metadataResult must be an empty value or a variable name","activityId":str(aid or "")})
                if isinstance(metadata_result,str) and metadata_result and metadata_result==item.get("result","rows"):problems.append({"code":"desktop-uia-grid-result-collision","message":"UIA grid result and metadataResult must use different variable names","activityId":str(aid or "")})
                process_id=item.get("processId")
                if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):problems.append({"code":"desktop-uia-process-id","message":"UIA processId must be a positive integer","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",10)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:problems.append({"code":"desktop-uia-timeout","message":"UIA timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
            if typ == "desktop_ui_set_range_value":
                window_title=item.get("windowTitle")
                if not isinstance(window_title,str) or not window_title.strip() or len(window_title)>512:problems.append({"code":"desktop-uia-window","message":"Set UI Range Value needs an exact windowTitle of 1–512 characters","activityId":str(aid or "")})
                name=item.get("name","");automation_id=item.get("automationId","");control_type=item.get("controlType","")
                if not isinstance(name,str) or len(name)>512:problems.append({"code":"desktop-uia-name","message":"UIA accessible name must be text no longer than 512 characters","activityId":str(aid or "")})
                if not isinstance(automation_id,str) or len(automation_id)>512:problems.append({"code":"desktop-uia-automation-id","message":"UIA Automation ID must be text no longer than 512 characters","activityId":str(aid or "")})
                if isinstance(name,str) and isinstance(automation_id,str) and not name.strip() and not automation_id.strip():problems.append({"code":"desktop-uia-selector","message":"Specify an accessible name or Automation ID for the UIA control","activityId":str(aid or "")})
                if not isinstance(control_type,str) or control_type not in {"Slider","Spinner","Spin Button","SpinButton"}:problems.append({"code":"desktop-uia-range-type","message":"Set UI Range Value requires a Slider, Spinner, or AT-SPI Spin Button control","activityId":str(aid or "")})
                value=item.get("value")
                if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value):problems.append({"code":"desktop-uia-range-value","message":"Range value must be a finite number","activityId":str(aid or "")})
                process_id=item.get("processId")
                if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):problems.append({"code":"desktop-uia-process-id","message":"UIA processId must be a positive integer","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",10)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:problems.append({"code":"desktop-uia-timeout","message":"UIA timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
            if typ == "desktop_ui_drag":
                window_title=item.get("windowTitle")
                if not isinstance(window_title,str) or not window_title.strip() or len(window_title)>512:
                    problems.append({"code":"desktop-uia-window","message":"UIA drag needs an exact windowTitle of 1–512 characters","activityId":str(aid or "")})
                for side in ("source","target"):
                    name=item.get(side+"Name","");automation_id=item.get(side+"AutomationId","");control_type=item.get(side+"ControlType","")
                    if not isinstance(name,str) or len(name)>512:problems.append({"code":"desktop-uia-drag-name","message":f"Drag {side} name must be text no longer than 512 characters","activityId":str(aid or "")})
                    if not isinstance(automation_id,str) or len(automation_id)>512:problems.append({"code":"desktop-uia-drag-id","message":f"Drag {side} Automation ID must be text no longer than 512 characters","activityId":str(aid or "")})
                    if isinstance(name,str) and isinstance(automation_id,str) and not name.strip() and not automation_id.strip():problems.append({"code":"desktop-uia-drag-selector","message":f"Specify a name or Automation ID for the drag {side}","activityId":str(aid or "")})
                    if not isinstance(control_type,str) or len(control_type)>128:problems.append({"code":"desktop-uia-drag-control-type","message":f"Drag {side} controlType must be text no longer than 128 characters","activityId":str(aid or "")})
                duration=item.get("durationMilliseconds",500)
                if not isinstance(duration,int) or isinstance(duration,bool) or not 100<=duration<=5000:problems.append({"code":"desktop-uia-drag-duration","message":"Drag durationMilliseconds must be an integer from 100 to 5,000","activityId":str(aid or "")})
                process_id=item.get("processId")
                if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):problems.append({"code":"desktop-uia-process-id","message":"UIA processId must be a positive integer","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",10)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:problems.append({"code":"desktop-uia-timeout","message":"UIA timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
            if typ in {"desktop_ui_click","desktop_ui_scroll_into_view","desktop_ui_invoke","desktop_ui_press","desktop_ui_fill","desktop_ui_text","desktop_ui_wait","desktop_ui_select","desktop_ui_select_many","desktop_ui_check","desktop_ui_uncheck","desktop_ui_expand","desktop_ui_collapse"}:
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
                if typ=="desktop_ui_invoke" and control_type and control_type not in {"Button","Push Button","Toggle Button","Hyperlink","MenuItem","Menu Item","SplitButton","Split Button","Link"}:
                    problems.append({"code":"desktop-uia-invoke-type","message":"Invoke UI Control requires an accessible Button, Hyperlink, MenuItem, SplitButton, or Link control","activityId":str(aid or "")})
                if typ=="desktop_ui_press" and item.get("key") not in SUPPORTED_DESKTOP_KEYS:
                    problems.append({"code":"desktop-uia-key","message":"Press UI Key needs one key or chord from the supported allowlist","activityId":str(aid or "")})
                process_id=item.get("processId")
                if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):
                    problems.append({"code":"desktop-uia-process-id","message":"UIA processId must be a positive integer","activityId":str(aid or "")})
                timeout=item.get("timeoutSeconds",10)
                if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:
                    problems.append({"code":"desktop-uia-timeout","message":"UIA timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
                if typ=="desktop_ui_fill" and (not isinstance(item.get("value"),str) or (control_type and control_type not in {"Edit","Entry"})):
                    problems.append({"code":"desktop-uia-fill","message":"UIA Set Text needs a string value and an Edit control","activityId":str(aid or "")})
                if typ=="desktop_ui_select" and (not isinstance(item.get("value"),str) or not item.get("value").strip() or (control_type and control_type not in {"ComboBox","Combo Box","List","ListBox","List Box","ListItem","List Item","TreeItem","Tree Item"})):
                    problems.append({"code":"desktop-uia-select","message":"UIA Select Option needs a non-empty exact option name and a ComboBox, List, ListBox, ListItem, or TreeItem control","activityId":str(aid or "")})
                if typ=="desktop_ui_select_many":
                    values=item.get("values",[])
                    mode=item.get("mode","replace")
                    if control_type and control_type not in {"List","List Box"}:
                        problems.append({"code":"desktop-uia-select-many-type","message":"Set List Selection requires a List control","activityId":str(aid or "")})
                    if not isinstance(values,list) or len(values)>100 or any(not isinstance(value,str) or len(value)>512 for value in values):
                        problems.append({"code":"desktop-uia-select-many-values","message":"List selection values must be an array of at most 100 names, each no longer than 512 characters","activityId":str(aid or "")})
                    elif len(values)!=len(set(values)):
                        problems.append({"code":"desktop-uia-select-many-duplicates","message":"List selection values must not contain duplicate names","activityId":str(aid or "")})
                    if not isinstance(mode,str) or mode not in {"replace","add","remove"} or (mode!="replace" and isinstance(values,list) and not values):
                        problems.append({"code":"desktop-uia-select-many-mode","message":"List selection mode must be replace, add, or remove; add and remove need at least one name","activityId":str(aid or "")})
                    result=item.get("result","selectedItems")
                    if not isinstance(result,str) or not result.isidentifier():
                        problems.append({"code":"desktop-uia-select-many-result","message":"Set List Selection result must be a variable name","activityId":str(aid or "")})
                if typ=="desktop_ui_check" and (control_type and control_type not in {"CheckBox","Check Box","RadioButton","Radio Button"}):
                    problems.append({"code":"desktop-uia-check","message":"UIA Set Checked requires a CheckBox or RadioButton control","activityId":str(aid or "")})
                if typ=="desktop_ui_uncheck" and (control_type and control_type not in {"CheckBox","Check Box"}):
                    problems.append({"code":"desktop-uia-uncheck","message":"UIA Uncheck requires a CheckBox control","activityId":str(aid or "")})
                if typ in {"desktop_ui_expand","desktop_ui_collapse"} and control_type and control_type not in {"TreeItem","Tree Item"}:
                    problems.append({"code":"desktop-uia-tree-type","message":"Expand or Collapse requires a TreeItem control","activityId":str(aid or "")})
                if typ=="desktop_ui_text" and (not isinstance(item.get("result","text"),str) or not item.get("result","text").strip()):
                    problems.append({"code":"desktop-uia-result","message":"UIA Read Text needs a non-empty result variable name","activityId":str(aid or "")})
                if typ=="desktop_ui_wait" and (not isinstance(item.get("state","exists"),str) or item.get("state","exists") not in {"exists","visible","enabled","not_visible","checked","unchecked","selected","unselected","expanded","collapsed"}):
                    problems.append({"code":"desktop-uia-state","message":"UIA Wait state must be exists, visible, enabled, not_visible, checked, unchecked, selected, unselected, expanded, or collapsed","activityId":str(aid or "")})
                if typ=="desktop_ui_wait" and item.get("state") in {"selected","unselected"} and control_type not in {"ListItem","List Item","TreeItem","Tree Item"}:
                    problems.append({"code":"desktop-uia-selected-state-type","message":"Selected and unselected wait states require a ListItem or TreeItem control","activityId":str(aid or "")})
                if typ=="desktop_ui_wait" and item.get("state") in {"expanded","collapsed"} and control_type not in {"TreeItem","Tree Item"}:
                    problems.append({"code":"desktop-uia-tree-state-type","message":"Expanded and collapsed wait states require a TreeItem control","activityId":str(aid or "")})
            if typ=="desktop_launch_app":
                executable=item.get("executable")
                if not isinstance(executable,str) or not executable.strip() or len(executable)>4096 or "\x00" in executable or not Path(executable).is_absolute():
                    problems.append({"code":"desktop-app-executable","message":"Launch Desktop Application needs an absolute executable path of at most 4,096 characters","activityId":str(aid or "")})
                arguments=item.get("arguments",[])
                if not isinstance(arguments,list) or len(arguments)>100 or any(not isinstance(value,str) or len(value)>4096 or "\x00" in value for value in arguments):
                    problems.append({"code":"desktop-app-arguments","message":"Application arguments must be an array of at most 100 strings, each no longer than 4,096 characters","activityId":str(aid or "")})
                result=item.get("result","processId")
                if not isinstance(result,str) or not result.isidentifier() or len(result)>256:
                    problems.append({"code":"desktop-app-result","message":"Launch Desktop Application result must be a variable name","activityId":str(aid or "")})
            if typ in {"desktop_window_wait","desktop_window_activate","desktop_window_minimize","desktop_window_restore","desktop_window_close"}:
                title=item.get("windowTitle","");process_id=item.get("processId")
                if not isinstance(title,str) or len(title)>512:
                    problems.append({"code":"desktop-window-title","message":"Window title must be text no longer than 512 characters","activityId":str(aid or "")})
                if process_id is not None and (not isinstance(process_id,int) or isinstance(process_id,bool) or process_id<1):
                    problems.append({"code":"desktop-window-process-id","message":"Window processId must be a positive integer","activityId":str(aid or "")})
                if not title.strip() and process_id is None:
                    problems.append({"code":"desktop-window-selector","message":"Specify an exact windowTitle or processId","activityId":str(aid or "")})
                if typ=="desktop_window_wait":
                    state=item.get("state","exists");timeout=item.get("timeoutSeconds",30)
                    if state not in {"exists","not_exists"}:
                        problems.append({"code":"desktop-window-state","message":"Wait for Window state must be exists or not_exists","activityId":str(aid or "")})
                    if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:
                        problems.append({"code":"desktop-window-timeout","message":"Wait for Window timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
                if typ=="desktop_window_close":
                    timeout=item.get("timeoutSeconds",15)
                    if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 1<=timeout<=120:
                        problems.append({"code":"desktop-window-close-timeout","message":"Close Window timeoutSeconds must be between 1 and 120","activityId":str(aid or "")})
                if typ=="desktop_window_close" and item.get("confirmClose") is not True:
                    problems.append({"code":"desktop-window-close-confirmation","message":"Close Window requires confirmClose=true to acknowledge it may close unsaved work","activityId":str(aid or "")})
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
            if node.get("breakpointCondition") is not None:
                condition=node.get("breakpointCondition")
                if node.get("breakpoint") is not True:
                    problems.append({"code":"breakpoint-condition-disabled","message":f"Conditional breakpoint on flowchart node {node_id} requires the breakpoint to be enabled"})
                elif not isinstance(condition,str) or len(condition)>2048:
                    problems.append({"code":"breakpoint-condition","message":f"Breakpoint condition on flowchart node {node_id} must be text no longer than 2,048 characters"})
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
            if state.get("breakpointCondition") is not None:
                condition=state.get("breakpointCondition")
                if state.get("breakpoint") is not True:
                    problems.append({"code":"breakpoint-condition-disabled","message":f"Conditional breakpoint on state {state_id} requires the breakpoint to be enabled"})
                elif not isinstance(condition,str) or len(condition)>2048:
                    problems.append({"code":"breakpoint-condition","message":f"Breakpoint condition on state {state_id} must be text no longer than 2,048 characters"})
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
            if isinstance(arg,dict) and "default" in arg and not _argument_value_matches(arg["default"],arg.get("type","any")):
                problems.append({"code":"argument-default-type","message":f"Argument '{arg.get('name')}' default does not match declared type {arg.get('type','any')}"})
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
    "regex_replace", "regex_match", "csv_read", "csv_write", "xlsx_read", "xlsx_write", "pdf_read_text", "image_ocr", "json_parse", "json_write",
    "wait", "http_request", "http_paginate", "api_request", "sqlite_query", "invoke_workflow", "try", "while", "retry", "switch", "file_move", "file_delete", "transform_field", "filter_rows", "join_rows", "group_rows", "sort_rows", "map_rows", "distinct_rows", "validate_rows",
    "browser_launch", "browser_close", "browser_navigate", "browser_new_tab", "browser_capture_popup", "browser_switch_tab", "browser_close_tab", "browser_click", "browser_hover", "browser_press", "browser_upload", "browser_download", "browser_wait_response", "browser_fill", "browser_select", "browser_select_many", "browser_check", "browser_uncheck", "browser_text", "browser_accessibility_snapshot", "browser_extract_records", "browser_table_read", "browser_wait", "browser_assert", "browser_scroll", "browser_screenshot",
    "desktop_click", "desktop_type", "desktop_hotkey", "desktop_press", "desktop_screenshot",
    "desktop_ui_click", "desktop_ui_scroll_into_view", "desktop_ocr_click", "desktop_ui_drag", "desktop_ui_grid_read", "desktop_ui_set_range_value", "desktop_ui_invoke", "desktop_ui_press", "desktop_ui_fill", "desktop_ui_text", "desktop_ui_wait", "desktop_ui_select", "desktop_ui_select_many", "desktop_ui_check", "desktop_ui_uncheck", "desktop_ui_expand", "desktop_ui_collapse", "desktop_launch_app",
    "desktop_window_wait", "desktop_window_activate", "desktop_window_minimize", "desktop_window_restore", "desktop_window_close",
}
