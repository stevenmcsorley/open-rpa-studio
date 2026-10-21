from __future__ import annotations

import json
from pathlib import Path

import pytest

from openrpa import api_connections
from openrpa.engine import RunOptions, run_project


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


def test_api_response_mapping_uses_json_pointers_and_enforces_limits(tmp_path,monkeypatch):
    from openrpa import engine
    from openrpa.model import validate_workflow
    monkeypatch.setattr(api_connections,"assert_public_url",lambda url:None)
    profile=api_connections.save_profile(tmp_path/"connections.json",{"name":"Example","baseUrl":"https://api.example.test/v1"})
    response={"status":200,"headers":{"Content-Type":"application/json"},"body":json.dumps({"data":{"items":[{"id":7,"display/name":"Order A"}]}})}
    monkeypatch.setattr(engine,"restricted_http_request",lambda *args:response)
    mapping={"responseCode":"200","itemsPointer":"/data/items","fields":[{"name":"id","path":"/id"},{"name":"displayName","path":"/display~1name"}],"result":"orders","maxItems":1}
    activity={"id":"fetch","type":"api_request","connectionId":profile["id"],"path":"/orders","result":"response","responseMapping":mapping}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]}
    assert validate_workflow(workflow)==[]
    root,project=_project(tmp_path,workflow)
    result=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
    assert result.status=="succeeded"
    assert result.variables["orders"]==[{"id":7,"displayName":"Order A"}]
    assert result.variables["response"]["status"]==200
    assert result.variables["response"]["body"]==response["body"]

    failures=[
        ({**response,"body":"{"},mapping,"api-response-json"),
        (response,{**mapping,"itemsPointer":"/data/missing"},"api-response-pointer"),
        ({**response,"body":json.dumps({"data":{"items":[{"id":1,"display/name":"A"},{"id":2,"display/name":"B"}]}})},{**mapping,"maxItems":1},"api-response-limit"),
        ({**response,"body":json.dumps({"data":{"items":[{"id":{"nested":1},"display/name":"Order A"}]}})},mapping,"api-response-field-type"),
        ({**response,"status":503},mapping,"api-response-status"),
    ]
    for next_response,next_mapping,code in failures:
        monkeypatch.setattr(engine,"restricted_http_request",lambda *args,reply=next_response:reply)
        activity["responseMapping"]=next_mapping
        root,project=_project(tmp_path,workflow)
        failed=run_project(project,root,"Main",options=RunOptions(allow_network=True,api_connections_path=tmp_path/"connections.json"))
        assert failed.status=="failed" and failed.error["activityId"]=="fetch" and failed.error["code"]==code


def test_api_response_mapping_validation_rejects_unsafe_or_conflicting_configuration():
    from openrpa.model import validate_workflow
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"fetch","type":"api_request","connectionId":"profile","path":"/items","result":"response","responseMapping":{"responseCode":"200","itemsPointer":"/items","fields":[{"name":"id","path":"/id"}],"result":"items","maxItems":10}}]}
    assert validate_workflow(base)==[]
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["itemsPointer"]="items"
    assert "api-response-pointer" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["result"]="response"
    assert "api-response-result-conflict" in {problem["code"] for problem in validate_workflow(bad)}
    bad=json.loads(json.dumps(base));bad["activities"][0]["responseMapping"]["responseCode"]="500"
    assert "api-response-code" in {problem["code"] for problem in validate_workflow(bad)}


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
