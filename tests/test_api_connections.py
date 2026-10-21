from __future__ import annotations

import json
import datetime
from pathlib import Path

import pytest

from openrpa import api_connections
from openrpa.engine import RunOptions, run_project
from openrpa.model import validate_workflow


class FakeKeyring:
    def __init__(self): self.values={}
    def set_password(self,service,username,password): self.values[(service,username)]=password
    def get_password(self,service,username): return self.values.get((service,username))
    def delete_password(self,service,username): self.values.pop((service,username),None)


def test_api_connection_profiles_keep_secrets_out_of_local_json(tmp_path,monkeypatch):
    vault=FakeKeyring();monkeypatch.setattr("openrpa.credentials.get_safe_keyring",lambda:vault)
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    path=tmp_path/"api-connections.json"
    profile=api_connections.save_profile(path,{"name":"Ledger API","baseUrl":"https://ledger.example/v1","authType":"bearer","headers":{"Accept":"application/json"},"minIntervalSeconds":.25})
    api_connections.store_secret(profile["id"],"top-secret-token")
    assert api_connections.read_secret(profile["id"])=="top-secret-token"
    assert api_connections.has_secret(profile["id"])
    stored=path.read_text(encoding="utf-8")
    assert "top-secret-token" not in stored
    assert api_connections.list_profiles(path)==[profile]
    api_connections.delete_profile(path,profile["id"])
    assert api_connections.list_profiles(path)==[]
    assert not api_connections.has_secret(profile["id"])


def test_legacy_api_connection_store_is_readable_after_oauth_schema_upgrade(tmp_path,monkeypatch):
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile_id="a2b4d8d0-828a-4ee0-b43f-f9674ad7c2f1"
    path=tmp_path/"legacy.json"
    path.write_text(json.dumps({"format":"openrpa.api-connections","formatVersion":1,"profiles":[{"id":profile_id,"name":"Old API","baseUrl":"https://api.example/v1","authType":"bearer","apiKeyHeader":"X-API-Key","headers":{},"minIntervalSeconds":0}]}),encoding="utf-8")
    rows=api_connections.list_profiles(path)
    assert rows[0]["id"]==profile_id and rows[0]["authType"]=="bearer" and rows[0]["tokenUrl"]==""
    assert json.loads(path.read_text(encoding="utf-8"))["formatVersion"]==1


def test_metadata_only_profile_read_does_not_require_live_dns(tmp_path,monkeypatch):
    path=tmp_path/"connections.json"
    monkeypatch.setattr(api_connections,"assert_public_url",lambda _url:None)
    profile=api_connections.save_profile(path,{"name":"Offline API","baseUrl":"https://offline.example/v1"})
    def dns_unavailable(_url):raise RuntimeError("DNS unavailable")
    monkeypatch.setattr(api_connections,"assert_public_url",dns_unavailable)
    assert api_connections.list_profiles(path,check_public_destinations=False)==[profile]
    with pytest.raises(ValueError,match="not a permitted public HTTPS destination"):
        api_connections.list_profiles(path)


@pytest.mark.parametrize("values",[
    {"name":"Bad","baseUrl":"http://api.example"},
    {"name":"Bad","baseUrl":"https://user:pass@api.example"},
    {"name":"Bad","baseUrl":"https://api.example","headers":{"Authorization":"secret"}},
    {"name":"Bad","baseUrl":"https://api.example","headers":{"X-Token":"secret"}},
    {"name":"Bad","baseUrl":"https://api.example","authType":"api_key_header","apiKeyHeader":"X-API-Key","headers":{"x-api-key":"not-a-secret"}},
    {"name":"Bad OAuth","baseUrl":"https://api.example","authType":"oauth_client_credentials","tokenUrl":"http://auth.example/token","clientId":"client"},
    {"name":"Bad OAuth","baseUrl":"https://api.example","authType":"oauth_client_credentials","tokenUrl":"https://auth.example/token","clientId":""},
    {"name":"Bad","baseUrl":"https://api.example","headers":{"X-Okay":"line\nbreak"}},
    {"name":"Bad","baseUrl":"https://api.example","minIntervalSeconds":61},
])
def test_api_connection_profiles_reject_unsafe_configuration(tmp_path,monkeypatch,values):
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    with pytest.raises(ValueError):api_connections.save_profile(tmp_path/"connections.json",values)


@pytest.mark.parametrize("header,expected_code",[
    ("Bad Header","api-request-headers"),
    ("X-Token","api-request-header-restricted"),
    ("X-Secret","api-request-header-restricted"),
    ("X-API-Key","api-request-header-restricted"),
    ("X-Request-Id",None),
])
def test_api_request_validates_http_header_names_and_keeps_credentials_in_connection(header,expected_code):
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Headers","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":"profile","path":"/items","headers":{header:"value"}}]}
    codes={problem["code"] for problem in validate_workflow(workflow)}
    if expected_code is None:
        assert not codes
    else:
        assert expected_code in codes


def _project(tmp_path,workflow):
    root=tmp_path/"project";(root/"workflows").mkdir(parents=True,exist_ok=True)
    (root/"workflows/main.workflow.json").write_text(json.dumps(workflow),encoding="utf-8")
    project={"format":"openrpa.project","formatVersion":1,"name":"API Request test","main":"Main","workflows":{"Main":"workflows/main.workflow.json"}}
    return root,project


def test_api_request_uses_vault_auth_relative_path_and_bounded_response(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Example","baseUrl":"https://api.example.test/v1","authType":"bearer"})
    monkeypatch.setattr(api_connections,"read_secret",lambda profile_id:"private-token")
    requests=[]
    def fake_request(url,method,headers,body,timeout,max_bytes):
        requests.append((url,method,headers,body,timeout,max_bytes))
        return {"status":200,"headers":{"Content-Type":"application/json"},"body":"{\"ok\":true}"}
    monkeypatch.setattr(engine,"restricted_http_request",fake_request)
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[{"name":"page","type":"integer","value":2}],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/orders","query":{"page":"{{page}}"},"headers":{"Accept":"application/json"},"result":"response"}]}
    root,project=_project(tmp_path,workflow)
    audits=[];result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json",audit=lambda action,details:audits.append((action,details))))
    assert result.status=="succeeded"
    assert requests[0][0]=="https://api.example.test/v1/orders?page=2"
    assert requests[0][1]=="GET" and requests[0][2]["Authorization"]=="Bearer private-token"
    assert requests[0][4:]==(20,5_000_000)
    assert audits==[("api.request",{"activityId":"fetch","connectionId":profile["id"],"method":"GET","host":"api.example.test"})]
    assert "private-token" not in json.dumps(result.__dict__)


def test_api_delete_requires_explicit_permission_and_is_not_retried(tmp_path,monkeypatch):
    from openrpa import engine
    from openrpa.model import validate_workflow
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Example","baseUrl":"https://api.example.test/v1"})
    requests=[]
    monkeypatch.setattr(engine,"restricted_http_request",lambda *args:(requests.append(args),{"status":204,"headers":{},"body":""})[1])
    activity={"id":"remove","type":"api_request","connectionId":profile["id"],"method":"DELETE","path":"/records/42","result":"response"}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]}
    assert validate_workflow(workflow)==[]
    root,project=_project(tmp_path,workflow)
    denied=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert denied.status=="failed" and denied.error["code"]=="destructive-permission-denied"
    assert requests==[]
    allowed=run_project(project,root,"Main",options=RunOptions(allow_network=True,allow_destructive=True,api_connections_path=tmp_path/"connections.json"))
    assert allowed.status=="succeeded" and len(requests)==1 and requests[0][1]=="DELETE"
    activity["retryPolicy"]={"maxAttempts":2,"delaySeconds":0,"backoffFactor":2}
    assert any(problem["code"]=="api-retry-safety" for problem in validate_workflow(workflow))


def test_api_response_mapping_uses_json_pointers_and_enforces_limits(tmp_path,monkeypatch):
    from openrpa import engine
    from openrpa.model import validate_workflow
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Example","baseUrl":"https://api.example.test/v1"})
    response={"status":200,"headers":{"Content-Type":"application/json"},"body":json.dumps({"data":{"items":[{"id":7,"display/name":"Order A","status":" OPEN "}]}})}
    monkeypatch.setattr(engine,"restricted_http_request",lambda *args:response)
    mapping={"responseCode":"200","itemsPointer":"/data/items","fields":[{"name":"id","path":"/id"},{"name":"displayName","path":"/display~1name"},{"name":"normalizedStatus","expression":"lower(item[\"status\"])"}],"result":"orders","maxItems":1}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"path":"/orders","result":"response","responseMapping":mapping}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]}
    assert validate_workflow(workflow)==[]
    root,project=_project(tmp_path,workflow)
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded"
    assert result.variables["orders"]==[{"id":7,"displayName":"Order A","normalizedStatus":" open "}]
    assert result.variables["response"]["status"]==200
    assert result.variables["response"]["body"]==response["body"]

    failures=[
        ({**response,"body":"{"},mapping,"api-response-json"),
        (response,{**mapping,"itemsPointer":"/data/missing"},"api-response-pointer"),
        (response,{**mapping,"fields":[{"name":"broken","expression":"1 / 0"}]},"api-response-field-expression"),
        ({**response,"body":json.dumps({"data":{"items":[{"id":1,"display/name":"A"},{"id":2,"display/name":"B"}]}})},{**mapping,"maxItems":1},"api-response-limit"),
        ({**response,"status":503},mapping,"api-response-status"),
    ]
    for next_response,next_mapping,code in failures:
        monkeypatch.setattr(engine,"restricted_http_request",lambda *args,reply=next_response:reply)
        activity["responseMapping"]=next_mapping
        root,project=_project(tmp_path,workflow)
        failed=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
        assert failed.status=="failed" and failed.error["activityId"]=="fetch" and failed.error["code"]==code


def test_api_response_mapping_preserves_nested_json_and_enforces_projected_byte_quota(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Nested","baseUrl":"https://api.example.test/v1"})
    payload={"data":{"items":[{"id":7,"customer":{"name":"Ada","addresses":[{"city":"London"}],"notes":"x"*1_500},"flags":["priority",{"code":"A"}]}]}}
    response={"status":200,"headers":{"Content-Type":"application/json"},"body":json.dumps(payload)}
    monkeypatch.setattr(engine,"restricted_http_request",lambda *args:response)
    mapping={"responseCode":"200","itemsPointer":"/data/items","fields":[{"name":"customer","path":"/customer"},{"name":"flags","path":"/flags"}],"result":"orders","maxItems":10,"maxOutputBytes":2_048}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"path":"/orders","result":"response","responseMapping":mapping}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]}
    assert validate_workflow(workflow)==[]
    root,project=_project(tmp_path,workflow)
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded",result.error
    assert result.variables["orders"]==[{"customer":{"name":"Ada","addresses":[{"city":"London"}],"notes":"x"*1_500},"flags":["priority",{"code":"A"}]}]

    activity["responseMapping"]={**mapping,"maxOutputBytes":1_024}
    root,project=_project(tmp_path,workflow)
    failed=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert failed.status=="failed" and failed.error["activityId"]=="fetch" and failed.error["code"]=="api-response-output-limit"


def test_reusable_openapi_operation_workflow_invokes_with_typed_inputs_and_outputs(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Orders","baseUrl":"https://api.example.test/v1"})
    requests=[]
    payload={"items":[{"id":"o-17","customer":{"name":"Ada"}}]}
    def fake_request(url,*args):
        requests.append((url,args[1]))
        return {"status":200,"headers":{"Content-Type":"application/json"},"body":json.dumps(payload)}
    monkeypatch.setattr(engine,"restricted_http_request",fake_request)
    operation={"format":"openrpa.workflow","formatVersion":1,"name":"Orders API - List Orders","executionModel":"sequence",
        "variables":[],"arguments":[
            {"name":"pathOrgId","type":"string","direction":"in","required":True},
            {"name":"queryState","type":"string","direction":"in","required":True},
            {"name":"queryPageSize","type":"string","direction":"in","required":False,"default":""},
            {"name":"headerXRegion","type":"string","direction":"in","required":False,"default":""},
            {"name":"apiResponse","type":"object","direction":"out","required":False,"target":"apiResponse"},
            {"name":"apiItems","type":"array","direction":"out","required":False,"target":"apiItems"}],
        "activities":[{"id":"api-request","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/orgs/{{ pathOrgId }}/orders","result":"apiResponse",
            "query":{"state":"{{ queryState }}","pageSize":"{{ queryPageSize }}"},"headers":{"X-Region":"{{ headerXRegion }}"},"omitEmptyQuery":["pageSize"],"omitEmptyHeaders":["X-Region"],
            "responseMapping":{"responseCode":"200","itemsPointer":"/items","fields":[{"name":"orderId","path":"/id"},{"name":"customer","path":"/customer"}],"result":"apiItems","maxItems":10,"maxOutputBytes":5_000_000}}]}
    main={"format":"openrpa.workflow","formatVersion":1,"name":"Main","executionModel":"sequence","arguments":[],"variables":[{"name":"org","type":"string","value":"north"},{"name":"state","type":"string","value":"open"}],
        "activities":[{"id":"invoke-orders","type":"invoke_workflow","workflow":operation["name"],"inputs":{"pathOrgId":"{{ org }}","queryState":"{{ state }}"},"outputs":{"apiResponse":"rawResponse","apiItems":"orders"}}]}
    workflows={"Main":main,operation["name"]:operation}
    assert validate_workflow(main,set(workflows))==[]
    assert validate_workflow(operation,set(workflows))==[]
    from openrpa.model import validate_workflow_bindings
    assert validate_workflow_bindings(workflows)==[]
    root=tmp_path/"project";(root/"workflows").mkdir(parents=True,exist_ok=True)
    (root/"workflows/main.workflow.json").write_text(json.dumps(main),encoding="utf-8")
    (root/"workflows/orders-api.workflow.json").write_text(json.dumps(operation),encoding="utf-8")
    project={"format":"openrpa.project","formatVersion":1,"name":"Reusable API test","main":"Main","workflows":{"Main":"workflows/main.workflow.json",operation["name"]:"workflows/orders-api.workflow.json"}}
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded",result.error
    assert requests[0][0]=="https://api.example.test/v1/orgs/north/orders?state=open"
    assert "X-Region" not in requests[0][1]
    assert result.variables["orders"]==[{"orderId":"o-17","customer":{"name":"Ada"}}]
    assert result.variables["rawResponse"]["status"]==200
    main["variables"].extend([{"name":"pageSize","type":"string","value":"25"},{"name":"region","type":"string","value":"EU"}])
    main["activities"][0]["inputs"].update({"queryPageSize":"{{ pageSize }}","headerXRegion":"{{ region }}"})
    (root/"workflows/main.workflow.json").write_text(json.dumps(main),encoding="utf-8")
    configured=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert configured.status=="succeeded",configured.error
    assert requests[1][0]=="https://api.example.test/v1/orgs/north/orders?state=open&pageSize=25"
    assert requests[1][1]["X-Region"]=="EU"


def test_api_response_mapping_validation_rejects_unsafe_or_conflicting_configuration():
    from openrpa.model import validate_workflow
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":"profile","path":"/items","result":"response","responseMapping":{"responseCode":"200","itemsPointer":"/items","fields":[{"name":"id","path":"/id"}],"result":"items","maxItems":10}}]}
    assert validate_workflow(base)==[]
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["itemsPointer"]="items"
    assert "api-response-pointer" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["result"]="response"
    assert "api-response-result-conflict" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["fields"]=[{"name":"status","expression":"lower(item[\"status\"])","path":"/status"}]
    assert "api-response-field-source" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["fields"]=[{"name":"status","expression":"__import__(\"os\")"}]
    assert "api-response-field-expression" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["fields"]=[{"name":"status","expression":"secretValue"}]
    assert "api-response-field-expression" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["responseCode"]="500"
    assert "api-response-code" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["maxOutputBytes"]=20_000_001
    assert "api-response-output-limit" in {problem["code"] for problem in validate_workflow(bad)}


def test_api_optional_query_and_header_omission_lists_are_validated():
    from openrpa.model import validate_workflow
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":"profile","query":{"limit":"{{ limit }}"},"headers":{"X-Region":"{{ region }}"},"omitEmptyQuery":["limit"],"omitEmptyHeaders":["X-Region"]}]}
    assert validate_workflow(base)==[]
    bad=json.loads(json.dumps(base));bad["activities"][0]["omitEmptyQuery"]=["missing"]
    assert "api-optional-parameter" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["omitEmptyHeaders"]=["X-Region","X-Region"]
    assert "api-optional-parameter" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["query"]=7
    assert "api-optional-parameter" in {problem["code"] for problem in validate_workflow(bad)}


def test_api_request_cursor_pagination_reuses_connection_and_publishes_complete_result(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Paged","baseUrl":"https://api.example.test/v1","authType":"bearer"})
    monkeypatch.setattr(api_connections,"read_secret",lambda _id:"page-token")
    seen=[]
    def fake_request(url,method,headers,body,timeout,max_bytes):
        seen.append((url,headers.get("Authorization")))
        cursor=dict(__import__("urllib.parse",fromlist=["parse_qsl"]).parse_qsl(__import__("urllib.parse",fromlist=["urlsplit"]).urlsplit(url).query)).get("cursor")
        payload={"items":[{"id":1},{"id":2}],"next":"two"} if cursor is None else {"items":[{"id":3}],"next":None}
        return {"status":200,"headers":{"Content-Type":"application/json"},"body":json.dumps(payload)}
    monkeypatch.setattr(engine,"restricted_http_request",fake_request)
    pagination={"strategy":"cursor","itemsPointer":"/items","cursorPointer":"/next","cursorParam":"cursor","maxPages":3,"maxItems":10,"maxTotalBytes":10000,"result":"orders","metadataResult":"pageInfo"}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/orders","result":"response","pagination":pagination}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]}
    from openrpa.model import validate_workflow
    assert validate_workflow(workflow)==[]
    root,project=_project(tmp_path,workflow)
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded",result.error
    assert result.variables["orders"]==[{"id":1},{"id":2},{"id":3}]
    assert result.variables["pageInfo"]["pages"]==2 and result.variables["pageInfo"]["itemCount"]==3
    assert result.variables["response"]["body"]==json.dumps({"items":[{"id":3}],"next":None})
    assert seen==[("https://api.example.test/v1/orders","Bearer page-token"),("https://api.example.test/v1/orders?cursor=two","Bearer page-token")]


def test_api_request_cursor_pagination_maps_fields_across_pages_and_keeps_raw_records(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Paged","baseUrl":"https://api.example.test/v1"})
    seen=[]
    def fake_request(url,*_args):
        seen.append(url)
        cursor=dict(__import__("urllib.parse",fromlist=["parse_qsl"]).parse_qsl(__import__("urllib.parse",fromlist=["urlsplit"]).urlsplit(url).query)).get("cursor")
        payload={"items":[{"id":1,"customer":{"name":"Ada"}},{"id":2,"customer":{"name":"Grace"}}],"next":"two"} if cursor is None else {"items":[{"id":3,"customer":{"name":"Lin"}}],"next":None}
        return {"status":200,"headers":{"Content-Type":"application/json"},"body":json.dumps(payload)}
    monkeypatch.setattr(engine,"restricted_http_request",fake_request)
    pagination={"strategy":"cursor","itemsPointer":"/items","cursorPointer":"/next","cursorParam":"cursor","maxPages":3,"maxItems":10,"maxTotalBytes":10000,"result":"rawOrders","metadataResult":"pageInfo"}
    mapping={"responseCode":"200","itemsPointer":"/items","fields":[{"name":"orderId","path":"/id"},{"name":"customer","path":"/customer"}],"result":"orders","maxItems":10}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/orders","result":"response","pagination":pagination,"responseMapping":mapping}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]}
    assert validate_workflow(workflow)==[]
    root,project=_project(tmp_path,workflow)
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded",result.error
    assert result.variables["rawOrders"]==[{"id":1,"customer":{"name":"Ada"}},{"id":2,"customer":{"name":"Grace"}},{"id":3,"customer":{"name":"Lin"}}]
    assert result.variables["orders"]==[{"orderId":1,"customer":{"name":"Ada"}},{"orderId":2,"customer":{"name":"Grace"}},{"orderId":3,"customer":{"name":"Lin"}}]
    assert result.variables["pageInfo"]["strategy"]=="cursor"
    assert result.variables["pageInfo"]["pages"]==2 and result.variables["pageInfo"]["itemCount"]==3
    assert result.variables["pageInfo"]["mappedItemCount"]==3 and result.variables["pageInfo"]["responseBytes"]>0
    assert result.variables["pageInfo"]["mappedOutputBytes"]>0
    assert seen==["https://api.example.test/v1/orders","https://api.example.test/v1/orders?cursor=two"]


def test_api_request_paginated_mapping_fails_atomically_on_total_mapped_limit(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Paged","baseUrl":"https://api.example.test/v1"})
    def fake_request(url,*_args):
        cursor=dict(__import__("urllib.parse",fromlist=["parse_qsl"]).parse_qsl(__import__("urllib.parse",fromlist=["urlsplit"]).urlsplit(url).query)).get("cursor")
        payload={"items":[{"id":1},{"id":2}],"next":"two"} if cursor is None else {"items":[{"id":3}],"next":None}
        return {"status":200,"headers":{},"body":json.dumps(payload)}
    monkeypatch.setattr(engine,"restricted_http_request",fake_request)
    pagination={"strategy":"cursor","itemsPointer":"/items","cursorPointer":"/next","cursorParam":"cursor","maxPages":3,"maxItems":10,"maxTotalBytes":10000,"result":"rawOrders","metadataResult":"pageInfo"}
    mapping={"responseCode":"","itemsPointer":"/items","fields":[{"name":"orderId","path":"/id"}],"result":"orders","maxItems":2}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/orders","result":"response","pagination":pagination,"responseMapping":mapping}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="failed" and result.error["code"]=="api-response-limit"
    assert "orders" not in result.variables and "rawOrders" not in result.variables


def test_api_request_paginated_nested_projection_enforces_combined_output_byte_quota(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Paged","baseUrl":"https://api.example.test/v1"})
    def fake_request(url,*_args):
        cursor=dict(__import__("urllib.parse",fromlist=["parse_qsl"]).parse_qsl(__import__("urllib.parse",fromlist=["urlsplit"]).urlsplit(url).query)).get("cursor")
        payload={"items":[{"data":{"text":"x"*600}}],"next":"two"} if cursor is None else {"items":[{"data":{"text":"y"*600}}],"next":None}
        return {"status":200,"headers":{},"body":json.dumps(payload)}
    monkeypatch.setattr(engine,"restricted_http_request",fake_request)
    pagination={"strategy":"cursor","itemsPointer":"/items","cursorPointer":"/next","cursorParam":"cursor","maxPages":3,"maxItems":10,"maxTotalBytes":5000,"result":"rawOrders","metadataResult":"pageInfo"}
    mapping={"responseCode":"","itemsPointer":"/items","fields":[{"name":"data","path":"/data"}],"result":"orders","maxItems":10,"maxOutputBytes":1024}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/orders","result":"response","pagination":pagination,"responseMapping":mapping}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="failed" and result.error["code"]=="api-response-output-limit"
    assert "orders" not in result.variables and "rawOrders" not in result.variables


def test_api_request_pagination_mapping_requires_shared_pointer_and_separate_results():
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":"profile","path":"/items","result":"response","pagination":{"strategy":"cursor","itemsPointer":"/data/items","cursorPointer":"/next","cursorParam":"cursor","result":"items","metadataResult":"pageInfo"},"responseMapping":{"responseCode":"","itemsPointer":"/items","fields":[{"name":"id","path":"/id"}],"result":"mapped","maxItems":10}}]}
    codes={problem["code"] for problem in validate_workflow(base)}
    assert "api-pagination-mapping-pointer" in codes
    base["activities"][0]["responseMapping"]["itemsPointer"]="/data/items"
    base["activities"][0]["responseMapping"]["result"]="pageInfo"
    codes={problem["code"] for problem in validate_workflow(base)}
    assert "api-pagination-mapping-result-conflict" in codes


def test_api_request_next_link_pagination_is_confined_to_saved_connection_path(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Paged","baseUrl":"https://api.example.test/v1"})
    seen=[]
    def fake_request(url,*_args):
        seen.append(url)
        page={"items":[1],"next":"/v1/orders?page=2"} if len(seen)==1 else {"items":[2],"next":None}
        return {"status":200,"headers":{},"body":json.dumps(page)}
    monkeypatch.setattr(engine,"restricted_http_request",fake_request)
    config={"strategy":"next_link","itemsPointer":"/items","nextLinkPointer":"/next","maxPages":3,"maxItems":10,"maxTotalBytes":10000,"result":"orders","metadataResult":"pageInfo"}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"path":"/orders","result":"response","pagination":config}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded",result.error
    assert seen==["https://api.example.test/v1/orders","https://api.example.test/v1/orders?page=2"]
    assert result.variables["orders"]==[1,2]


@pytest.mark.parametrize("link,code",[("https://other.example/v1/orders","api-pagination-next-link-origin"),("https://api.example.test/admin","api-pagination-next-link-path"),("/v1/orders?page=1","api-pagination-next-link-loop")])
def test_api_request_next_link_rejects_origin_path_and_loop(tmp_path,monkeypatch,link,code):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Paged","baseUrl":"https://api.example.test/v1"})
    seen=[]
    def request(*_args):
        seen.append(_args[0]);return {"status":200,"headers":{},"body":json.dumps({"items":[],"next":link})}
    monkeypatch.setattr(engine,"restricted_http_request",request)
    config={"strategy":"next_link","itemsPointer":"/items","nextLinkPointer":"/next","maxPages":3,"maxItems":10,"maxTotalBytes":10000,"result":"orders","metadataResult":"pageInfo"}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"path":"/orders","query":{"page":1},"result":"response","pagination":config}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="failed" and result.error["code"]==code
    if code=="api-pagination-next-link-loop":assert len(seen)==1


def test_api_request_cursor_pagination_rejects_repeated_initial_cursor_before_duplicate_fetch(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Paged","baseUrl":"https://api.example.test/v1"})
    seen=[]
    def request(url,*_args):
        seen.append(url);return {"status":200,"headers":{},"body":json.dumps({"items":[1],"next":"start"})}
    monkeypatch.setattr(engine,"restricted_http_request",request)
    config={"strategy":"cursor","itemsPointer":"/items","cursorPointer":"/next","cursorParam":"cursor","maxPages":3,"maxItems":10,"maxTotalBytes":10000,"result":"orders","metadataResult":"pageInfo"}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"path":"/orders","query":{"cursor":"start"},"result":"response","pagination":config}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="failed" and result.error["code"]=="api-pagination-cursor-loop"
    assert seen==["https://api.example.test/v1/orders?cursor=start"]


def test_api_pagination_validation_rejects_conflicts_and_unbounded_configuration():
    from openrpa.model import validate_workflow
    pagination={"strategy":"cursor","itemsPointer":"/items","cursorPointer":"/next","cursorParam":"cursor","maxPages":2,"maxItems":10,"maxTotalBytes":5000,"result":"items","metadataResult":"pageInfo"}
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":"profile","method":"GET","path":"/items","result":"response","pagination":pagination}]}
    assert validate_workflow(base)==[]
    for change,code in [({"maxPages":51},"api-pagination-limit"),({"itemsPointer":"items"},"api-pagination-pointer"),({"metadataResult":"response"},"api-pagination-result-conflict")]:
        bad=json.loads(json.dumps(base));bad["activities"][0]["pagination"].update(change)
        assert code in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["method"]="POST"
    assert "api-pagination-method" in {problem["code"] for problem in validate_workflow(bad)}


@pytest.mark.parametrize("failure",[TimeoutError("temporary timeout"),ConnectionError("connection reset")])
def test_api_request_retries_only_transient_transport_errors(tmp_path,monkeypatch,failure):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Retry API","baseUrl":"https://api.example.test/v1"})
    responses=[]
    def request(*_args):
        responses.append(True)
        if len(responses)==1:raise failure
        return {"status":200,"headers":{},"body":"ok"}
    monkeypatch.setattr(engine,"restricted_http_request",request)
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/items","result":"response","retryPolicy":{"maxAttempts":3,"delaySeconds":0,"backoffFactor":2}}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    audits=[];result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json",audit=lambda action,details:audits.append((action,details))))
    assert result.status=="succeeded" and result.variables["response"]["status"]==200
    assert len(responses)==2
    assert [action for action,_ in audits]==["api.request","api.retry","api.request"]


@pytest.mark.parametrize("status,expected_calls",[(503,2),(429,2),(400,1),(404,1)])
def test_api_request_retries_transient_statuses_but_not_client_errors(tmp_path,monkeypatch,status,expected_calls):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Retry API","baseUrl":"https://api.example.test/v1"})
    responses=[]
    def request(*_args):
        responses.append(True)
        code=status if len(responses)==1 else 200
        return {"status":code,"headers":{},"body":"response"}
    monkeypatch.setattr(engine,"restricted_http_request",request)
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/items","result":"response","retryPolicy":{"maxAttempts":2,"delaySeconds":0,"backoffFactor":2}}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded" and len(responses)==expected_calls
    assert result.variables["response"]["status"]==(200 if expected_calls==2 else status)


@pytest.mark.parametrize("headers,expected,source",[
    ({"Retry-After":"0"},0.0,"retry-after"),
    ({"rEtRy-AfTeR":"0"},0.0,"retry-after"),
    ({"Retry-After":"not-a-date"},0.0,"exponential-backoff"),
    ({},0.0,"exponential-backoff"),
])
def test_api_request_uses_bounded_retry_after_for_transient_http_responses(tmp_path,monkeypatch,headers,expected,source):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Retry API","baseUrl":"https://api.example.test/v1"})
    responses=[]
    def request(*_args):
        responses.append(True)
        return {"status":429 if len(responses)==1 else 200,"headers":headers if len(responses)==1 else {},"body":"response"}
    monkeypatch.setattr(engine,"restricted_http_request",request)
    waits=[]
    monkeypatch.setattr(engine.time,"sleep",lambda seconds:waits.append(seconds))
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/items","retryPolicy":{"maxAttempts":2,"delaySeconds":0,"backoffFactor":2}}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    audits=[]
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json",audit=lambda action,details:audits.append((action,details))))
    assert result.status=="succeeded" and len(responses)==2
    retry=next(details for action,details in audits if action=="api.retry")
    assert retry["delaySeconds"]==expected and retry["delaySource"]==source
    assert "Retry-After" not in json.dumps(retry)


def test_retry_after_http_date_is_parsed_and_capped():
    from openrpa.engine import _retry_after_seconds
    now=datetime.datetime(2026,1,1,tzinfo=datetime.timezone.utc)
    assert _retry_after_seconds({"Retry-After":"Thu, 01 Jan 2026 00:00:12 GMT"},now=now)==12.0
    assert _retry_after_seconds({"Retry-After":"Wed, 31 Dec 2025 23:59:59 GMT"},now=now)==0.0
    assert _retry_after_seconds({"Retry-After":"Thu, 01 Jan 2026 00:01:00 GMT"},now=now)==30.0
    assert _retry_after_seconds({"Retry-After":"120"},now=now)==30.0
    assert _retry_after_seconds({"Retry-After":"9"*129},now=now) is None


def test_api_retry_validation_requires_safe_get_and_bounded_policy():
    from openrpa.model import validate_workflow
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":"profile","method":"GET","path":"/items","retryPolicy":{"maxAttempts":3,"delaySeconds":.5,"backoffFactor":2}}]}
    assert validate_workflow(base)==[]
    for mutate,code in [(lambda item:item.update(method="POST"),"api-retry-safety"),(lambda item:item.update(body="{}"),"api-retry-safety"),(lambda item:item["retryPolicy"].update(maxAttempts=6),"api-retry-attempts"),(lambda item:item["retryPolicy"].update(delaySeconds=11),"api-retry-delay")]:
        bad=json.loads(json.dumps(base));mutate(bad["activities"][0])
        assert code in {problem["code"] for problem in validate_workflow(bad)}


def test_api_execution_rechecks_retry_safety_if_workflow_validation_is_bypassed(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Retry API","baseUrl":"https://api.example.test/v1"})
    calls=[];monkeypatch.setattr(engine,"restricted_http_request",lambda *_args:(calls.append(True) or {"status":200,"headers":{},"body":"ok"}))
    monkeypatch.setattr(engine,"validate_workflow",lambda *_args:[])
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/items","body":"","retryPolicy":{"maxAttempts":2,"delaySeconds":0,"backoffFactor":2}}
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="failed" and result.error["code"]=="api-retry-safety"
    assert calls==[]


def test_api_retry_exhaustion_is_audited_for_http_status_and_transport_failure(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Retry API","baseUrl":"https://api.example.test/v1"})
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/items","retryPolicy":{"maxAttempts":2,"delaySeconds":0,"backoffFactor":2}}
    audits=[];monkeypatch.setattr(engine,"restricted_http_request",lambda *_args:{"status":503,"headers":{},"body":"unavailable"})
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]})
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json",audit=lambda action,details:audits.append((action,details))))
    assert result.status=="succeeded" and result.variables["response"]["status"]==503
    assert ("api.retry.exhausted",{"activityId":"fetch","attempts":2,"reason":"transient-http-status","status":503}) in audits
    audits.clear();monkeypatch.setattr(engine,"restricted_http_request",lambda *_args:(_ for _ in ()).throw(TimeoutError("timeout")))
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json",audit=lambda action,details:audits.append((action,details))))
    assert result.status=="failed" and result.error["code"]=="http-timeout"
    assert ("api.retry.exhausted",{"activityId":"fetch","attempts":2,"reason":"transport-error","errorType":"TimeoutError"}) in audits


def test_api_request_requires_network_and_rejects_host_or_path_escape(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Example","baseUrl":"https://api.example.test/v1"})
    for path in ("//evil.example/x","https://evil.example/x","/%2e%2e/admin"):
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":profile["id"],"path":path}]}
        root,project=_project(tmp_path,workflow)
        result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
        assert result.status=="failed" and result.error["activityId"]=="fetch"
    workflow["activities"][0]["path"]="/orders"
    root,project=_project(tmp_path,workflow)
    result=run_project(project,root,"Main",options=RunOptions(allow_network=False,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="failed" and result.error["code"]=="network-permission-denied"


def test_oauth_client_credentials_is_exchanged_once_and_token_stays_ephemeral(tmp_path,monkeypatch):
    from openrpa import engine
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"OAuth API","baseUrl":"https://api.example.test/v1","authType":"oauth_client_credentials","tokenUrl":"https://auth.example.test/oauth/token","clientId":"client","scope":"orders.read","audience":"orders","clientAuthMethod":"client_secret_basic"})
    monkeypatch.setattr(api_connections,"read_secret",lambda profile_id:"client-secret")
    requests=[]
    def fake_request(url,method,headers,body,timeout,max_bytes):
        requests.append((url,method,headers,body,timeout,max_bytes))
        if url==profile["tokenUrl"]:
            return {"status":200,"headers":{"Content-Type":"application/json"},"body":json.dumps({"access_token":"ephemeral-access-token","token_type":"Bearer","expires_in":3600})}
        return {"status":200,"headers":{"Content-Type":"application/json"},"body":"{\"ok\":true}"}
    monkeypatch.setattr(engine,"restricted_http_request",fake_request)
    activities=[{"id":f"fetch-{index}","type":"api_request","connectionId":profile["id"],"method":"GET","path":f"/orders/{index}","result":f"response{index}"} for index in (1,2)]
    root,project=_project(tmp_path,{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":activities})
    audits=[];result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json",audit=lambda action,details:audits.append((action,details))))
    assert result.status=="succeeded"
    assert [item[0] for item in requests]==[profile["tokenUrl"],"https://api.example.test/v1/orders/1","https://api.example.test/v1/orders/2"]
    assert requests[0][2]["Authorization"].startswith("Basic ")
    assert b"grant_type=client_credentials" in requests[0][3] and b"scope=orders.read" in requests[0][3]
    assert requests[1][2]["Authorization"]=="Bearer ephemeral-access-token" and requests[2][2]["Authorization"]=="Bearer ephemeral-access-token"
    assert "ephemeral-access-token" not in json.dumps(result.__dict__)
    assert audits.count(("api.oauth.token",{"connectionId":profile["id"],"host":"auth.example.test"}))==1


def test_oauth_form_auth_does_not_log_credentials_and_rejects_bad_responses(monkeypatch):
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections._profile({"name":"OAuth","baseUrl":"https://api.example","authType":"oauth_client_credentials","tokenUrl":"https://auth.example/token","clientId":"client id","scope":"read","clientAuthMethod":"client_secret_post"})
    seen=[]
    token,expires=api_connections.request_oauth_token(profile,"private-secret",lambda *args:(seen.append(args) or {"status":200,"body":"{\"access_token\":\"token-value\",\"expires_in\":120}"}))
    assert token=="token-value" and expires==120
    assert b"client_id=client+id" in seen[0][3] and b"client_secret=private-secret" in seen[0][3]
    assert "private-secret" not in str(seen[0][2])
    with pytest.raises(ValueError,match="HTTP 401"):
        api_connections.request_oauth_token(profile,"private-secret",lambda *args:{"status":401,"body":"sensitive error body"})


def test_oauth_authorization_code_uses_pkce_loopback_and_refreshes_in_os_vault(tmp_path,monkeypatch):
    import http.client
    from urllib.parse import parse_qs,urlsplit
    vault=FakeKeyring();monkeypatch.setattr("openrpa.credentials.get_safe_keyring",lambda:vault)
    monkeypatch.setattr(api_connections,"assert_public_url",lambda _url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Calendar","baseUrl":"https://api.example.test/v1","authType":"oauth_authorization_code","authorizationUrl":"https://login.example.test/authorize","tokenUrl":"https://login.example.test/token","clientId":"desktop-client","scope":"events.read","audience":"calendar-api","clientAuthMethod":"none"})
    requests=[]
    def token_request(url,method,headers,body,timeout,max_bytes):
        requests.append((url,method,headers,body,timeout,max_bytes))
        if b"grant_type=authorization_code" in body:
            return {"status":200,"body":json.dumps({"access_token":"access-one","refresh_token":"refresh-one","expires_in":3600})}
        return {"status":200,"body":json.dumps({"access_token":"access-two","refresh_token":"refresh-two","expires_in":1800})}
    def fake_browser(url,**_kwargs):
        auth=parse_qs(urlsplit(url).query)
        assert auth["client_id"]==["desktop-client"] and auth["scope"]==["events.read"] and auth["audience"]==["calendar-api"]
        assert auth["code_challenge_method"]==["S256"] and len(auth["code_challenge"][0])==43
        redirect=urlsplit(auth["redirect_uri"][0]);connection=http.client.HTTPConnection(redirect.hostname,redirect.port,timeout=2)
        try:
            connection.request("GET",redirect.path+"?state=wrong&code=attacker");assert connection.getresponse().status==400
            connection.request("GET",redirect.path+"?"+urlencode({"state":auth["state"][0],"code":"auth-code"}));assert connection.getresponse().status==200
        finally:connection.close()
        return True
    from urllib.parse import urlencode
    tokens=api_connections.authorize_with_system_browser(profile,token_request,timeout=15,opener=fake_browser)
    assert len(requests)==1 and requests[0][0]==profile["tokenUrl"]
    fields=parse_qs(requests[0][3].decode())
    assert fields["grant_type"]==["authorization_code"] and fields["code"]==["auth-code"]
    assert fields["audience"]==["calendar-api"] and len(fields["code_verifier"][0])>=43
    api_connections.store_oauth_tokens(profile["id"],tokens)
    assert api_connections.read_oauth_tokens(profile["id"])["accessToken"]=="access-one"
    assert "access-one" not in (tmp_path/"connections.json").read_text(encoding="utf-8")
    vault.set_password(api_connections.OAUTH_TOKEN_SERVICE,profile["id"],json.dumps({"accessToken":"expired","expiresAt":0,"refreshToken":"refresh-one"}))
    assert api_connections.authorization_code_access_token(profile,token_request)=="access-two"
    assert parse_qs(requests[-1][3].decode())["grant_type"]==["refresh_token"]
    assert api_connections.read_oauth_tokens(profile["id"])["refreshToken"]=="refresh-two"
    api_connections.delete_profile(tmp_path/"connections.json",profile["id"])
    assert not vault.values


def test_oauth_authorization_code_can_be_cancelled_and_requires_explicit_pkce_client(tmp_path,monkeypatch):
    import threading
    monkeypatch.setattr(api_connections,"assert_public_url",lambda _url:None)
    profile=api_connections._profile({"name":"Calendar","baseUrl":"https://api.example.test/v1","authType":"oauth_authorization_code","authorizationUrl":"https://login.example.test/authorize","tokenUrl":"https://login.example.test/token","clientId":"desktop-client","clientAuthMethod":"none"})
    cancel=threading.Event();cancel.set()
    with pytest.raises(RuntimeError,match="cancelled"):
        api_connections.authorize_with_system_browser(profile,lambda *_args:pytest.fail("token exchange must not start"),cancel=cancel,opener=lambda *_args:True)


def test_api_request_uses_vaulted_authorization_code_token(tmp_path,monkeypatch):
    from openrpa import engine,credentials
    vault=FakeKeyring();monkeypatch.setattr(credentials,"get_safe_keyring",lambda:vault)
    monkeypatch.setattr(api_connections,"assert_public_url",lambda _url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Calendar","baseUrl":"https://api.example.test/v1","authType":"oauth_authorization_code","authorizationUrl":"https://login.example.test/authorize","tokenUrl":"https://login.example.test/token","clientId":"desktop-client","clientAuthMethod":"none"})
    api_connections.store_oauth_tokens(profile["id"],{"accessToken":"private-access-token","expiresAt":api_connections.time.time()+3600,"refreshToken":"private-refresh-token"})
    calls=[]
    monkeypatch.setattr(engine,"restricted_http_request",lambda url,method,headers,*args:(calls.append((url,method,headers)) or {"status":200,"headers":{"Content-Type":"application/json"},"body":"{\"ok\":true}"}))
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":profile["id"],"method":"GET","path":"/events","result":"response"}]}
    root,project=_project(tmp_path,workflow)
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded"
    assert calls[0][0]=="https://api.example.test/v1/events" and calls[0][2]["Authorization"]=="Bearer private-access-token"
    assert "private-access-token" not in json.dumps(result.__dict__) and "private-refresh-token" not in json.dumps(result.__dict__)


def test_local_bridge_manages_connections_tests_only_status_and_never_saves_secret(tmp_path,monkeypatch):
    from openrpa import bridge,network,credentials
    monkeypatch.setenv("OPENRPA_API_CONNECTIONS_FILE",str(tmp_path/"connections.json"))
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    vault=FakeKeyring();monkeypatch.setattr(credentials,"get_safe_keyring",lambda:vault)
    monkeypatch.setattr(network,"request",lambda *args:{"status":204,"headers":{"Content-Type":"application/json"},"body":"credential response must not be returned"})
    class History:
        def audit(self,*args):pass
    replies=[];monkeypatch.setattr(bridge,"send",replies.append);monkeypatch.setattr(bridge,"history",History())
    bridge.handle({"id":1,"method":"api.connections.save","params":{"profile":{"name":"Orders","baseUrl":"https://orders.example/v1","authType":"api_key_header","apiKeyHeader":"X-API-Key"},"secret":"never-write-me"}})
    saved=replies[-1]["result"];profile=saved["profile"]
    assert saved["credentialStored"] and profile["authType"]=="api_key_header"
    assert "never-write-me" not in (tmp_path/"connections.json").read_text(encoding="utf-8")
    bridge.handle({"id":2,"method":"api.connections.test","params":{"profileId":profile["id"],"path":"/health","allowNetwork":True}})
    assert replies[-1]["result"]=={"status":204,"ok":True,"contentType":"application/json"}
    assert "credential response" not in json.dumps(replies[-1])
    bridge.handle({"id":4,"method":"api.connections.save","params":{"profile":{**profile,"authType":"bearer"}}})
    assert replies[-1]["result"]["credentialStored"] is False
    assert not vault.values
    bridge.handle({"id":3,"method":"api.connections.delete","params":{"profileId":profile["id"]}})
    assert replies[-1]["result"]["deleted"] and not vault.values


def test_oauth_connection_test_discards_token_and_response_body(tmp_path,monkeypatch):
    from openrpa import bridge,network,credentials
    monkeypatch.setenv("OPENRPA_API_CONNECTIONS_FILE",str(tmp_path/"connections.json"))
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    vault=FakeKeyring();monkeypatch.setattr(credentials,"get_safe_keyring",lambda:vault)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"OAuth Orders","baseUrl":"https://orders.example/v1","authType":"oauth_client_credentials","tokenUrl":"https://login.example/token","clientId":"client"})
    api_connections.store_secret(profile["id"],"private-client-secret")
    calls=[]
    def response(url,*args):
        calls.append(url)
        return {"status":200,"headers":{"Content-Type":"application/json"},"body":"{\"access_token\":\"private-access-token\",\"expires_in\":60}"} if url==profile["tokenUrl"] else {"status":204,"headers":{"Content-Type":"application/json"},"body":"never surface this response"}
    monkeypatch.setattr(network,"request",response)
    class History:
        def audit(self,*args):pass
    replies=[];monkeypatch.setattr(bridge,"send",replies.append);monkeypatch.setattr(bridge,"history",History())
    bridge.handle({"id":9,"method":"api.connections.test","params":{"profileId":profile["id"],"path":"/health","allowNetwork":True}})
    assert calls==[profile["tokenUrl"],"https://orders.example/v1/health"]
    assert replies[-1]["result"]=={"status":204,"ok":True,"contentType":"application/json"}
    assert "private-client-secret" not in json.dumps(replies[-1]) and "private-access-token" not in json.dumps(replies[-1])
    assert "never surface this response" not in json.dumps(replies[-1])


def test_openapi_url_fetch_is_permission_gated_bounded_and_audited(monkeypatch):
    from openrpa import bridge,network
    replies=[];audits=[];calls=[]
    class History:
        def audit(self,action,details):audits.append((action,details))
    monkeypatch.setattr(bridge,"send",replies.append);monkeypatch.setattr(bridge,"history",History())
    monkeypatch.setattr(network,"request",lambda *args:(calls.append(args) or {"status":200,"headers":{"Content-Type":"application/yaml"},"body":"openapi: 3.0.0\npaths: {}"}))
    url="https://docs.example.test/openapi.yaml?version=3"
    bridge.handle({"id":1,"method":"openapi.fetch","params":{"url":url,"allowNetwork":False}})
    assert replies[-1]["error"]["message"]=="Fetching an OpenAPI URL requires enabling Allow network" and not calls
    bridge.handle({"id":2,"method":"openapi.fetch","params":{"url":"http://docs.example.test/openapi.json","allowNetwork":True}})
    assert "HTTPS" in replies[-1]["error"]["message"] and not calls
    bridge.handle({"id":3,"method":"openapi.fetch","params":{"url":"https://user:secret@docs.example.test/openapi.json","allowNetwork":True}})
    assert "HTTPS" in replies[-1]["error"]["message"] and not calls
    bridge.handle({"id":4,"method":"openapi.fetch","params":{"url":url,"allowNetwork":True}})
    assert replies[-1]["result"]["text"]=="openapi: 3.0.0\npaths: {}"
    assert calls[-1][0]==url and calls[-1][1]=="GET" and calls[-1][4:]==(15,2_000_000)
    assert audits==[("openapi.fetch",{"host":"docs.example.test","status":"started"}),("openapi.fetch",{"host":"docs.example.test","status":200,"bytes":len(replies[-1]["result"]["text"].encode("utf-8"))})]
    assert "version=3" not in json.dumps(audits)


def test_openapi_url_fetch_rejects_redirect_and_oversized_body(monkeypatch):
    from openrpa import bridge,network
    replies=[]
    class History:
        def audit(self,*args):pass
    monkeypatch.setattr(bridge,"send",replies.append);monkeypatch.setattr(bridge,"history",History())
    monkeypatch.setattr(network,"request",lambda *args:{"status":302,"redirectBlocked":True,"body":"https://other.example/spec.json"})
    bridge.handle({"id":5,"method":"openapi.fetch","params":{"url":"https://docs.example/spec.json","allowNetwork":True}})
    assert "redirects are not followed" in replies[-1]["error"]["message"]
    monkeypatch.setattr(network,"request",lambda *args:{"status":200,"body":"x"*2_000_001})
    bridge.handle({"id":6,"method":"openapi.fetch","params":{"url":"https://docs.example/spec.json","allowNetwork":True}})
    assert "2 MB limit" in replies[-1]["error"]["message"]
