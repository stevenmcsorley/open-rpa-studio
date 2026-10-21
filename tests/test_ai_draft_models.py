from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from openrpa import bridge


@pytest.mark.parametrize("execution_model,draft,expected",[
    ("sequence",{"explanation":"ordered steps","activities":[{"id":"message","type":"log","message":"hello"}]},"sequence"),
    ("flowchart",{"explanation":"branched process","flowchart":{"start":"start","nodes":[{"id":"start","kind":"start"},{"id":"action-node","kind":"action","activity":{"id":"log-action","type":"log","message":"hello"}},{"id":"end","kind":"end"}],"transitions":[{"from":"start","to":"action-node"},{"from":"action-node","to":"end"}]}},"flowchart"),
    ("state_machine",{"explanation":"approval route","stateMachine":{"initial":"review","states":[{"id":"review","activities":[]},{"id":"done","final":True,"activities":[]}],"transitions":[{"from":"review","to":"done"}]}},"state_machine"),
])
def test_bridge_validates_each_ai_draft_structure(monkeypatch,execution_model,draft,expected):
    replies=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda *_args,**_kwargs:None)
    monkeypatch.setattr(bridge.ai_providers,"draft",lambda *_args,**_kwargs:draft)
    bridge.handle({"id":7,"method":"ai.draft","params":{"provider":"ollama","model":"local","prompt":"make a workflow","executionModel":execution_model,"workflows":["Main"]}})
    result=replies[-1]["result"]
    assert result["valid"] is True
    if expected=="sequence":
        assert result["workflow"]["activities"][0]["id"]=="message"
        assert "executionModel" not in result["workflow"]
    elif expected=="flowchart":
        assert result["workflow"]["executionModel"]=="flowchart"
        assert result["workflow"]["flowchart"]["start"]=="start"
    else:
        assert result["workflow"]["executionModel"]=="state_machine"
        assert result["workflow"]["stateMachine"]["initial"]=="review"


def test_bridge_rejects_ai_output_for_a_different_model(monkeypatch):
    replies=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda *_args,**_kwargs:None)
    monkeypatch.setattr(bridge.ai_providers,"draft",lambda *_args,**_kwargs:{"explanation":"wrong shape","activities":[]})
    bridge.handle({"id":8,"method":"ai.draft","params":{"provider":"ollama","model":"local","prompt":"make a state machine","executionModel":"state_machine","workflows":["Main"]}})
    assert "error" in replies[-1]
    assert "stateMachine" in replies[-1]["error"]["message"]


def test_bridge_returns_and_audits_provider_reported_token_usage_only(monkeypatch):
    replies=[];audits=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda action,details:audits.append((action,details)))
    monkeypatch.setattr(bridge.ai_providers,"draft",lambda *_args,**_kwargs:{
        "explanation":"safe","activities":[{"id":"message","type":"log","message":"hello"}],
        "_openrpa_usage":{"inputTokens":12,"outputTokens":7,"totalTokens":19}})
    bridge.handle({"id":90,"method":"ai.draft","params":{"provider":"ollama","model":"local","prompt":"make a workflow","workflows":["Main"]}})
    assert replies[-1]["result"]["usage"]=={"inputTokens":12,"outputTokens":7,"totalTokens":19}
    assert ("ai.draft.usage",{"provider":"ollama","model":"local","inputTokens":12,"outputTokens":7,"totalTokens":19}) in audits


def test_bridge_passes_safe_api_profiles_and_rejects_unknown_connection_ids(monkeypatch):
    replies=[];captured={}
    profile={"id":"profile-123","name":"Broker","baseUrl":"https://broker.example/v1","authType":"bearer",
        "headers":{"X-Private":"do-not-send"},"clientId":"do-not-send"}
    payload={"explanation":"Read portfolio","activities":[{"id":"portfolio","type":"api_request","connectionId":"profile-123","method":"GET","path":"/portfolio","query":{},"headers":{},"result":"response"}]}
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda *_args,**_kwargs:None)
    monkeypatch.setattr(bridge.api_connections,"list_profiles",lambda _path,**_kwargs:[profile])
    def draft(*_args,api_connections=None,**_kwargs):
        captured["profiles"]=api_connections
        return payload
    monkeypatch.setattr(bridge.ai_providers,"draft",draft)
    request={"id":91,"method":"ai.draft","params":{"provider":"ollama","model":"local","prompt":"read my portfolio","workflows":["Main"]}}
    bridge.handle(request)
    assert captured["profiles"]==[{key:profile[key] for key in ("id","name","baseUrl","authType")}]
    assert replies[-1]["result"]["valid"] is True

    payload["activities"][0]["connectionId"]="invented-profile"
    bridge.handle(request)
    result=replies[-1]["result"]
    assert result["valid"] is False
    assert any(problem["code"]=="api-connection-unknown" for problem in result["problems"])


def test_bridge_returns_and_audits_structured_output_compatibility_fallback(monkeypatch):
    replies=[];audits=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda action,details:audits.append((action,details)))
    def draft(*_args,on_compatibility_fallback=None,**_kwargs):
        on_compatibility_fallback("Retried with schema-guided JSON")
        return {"explanation":"safe","activities":[{"id":"message","type":"log","message":"hello"}]}
    monkeypatch.setattr(bridge.ai_providers,"draft",draft)
    bridge.handle({"id":9,"method":"ai.draft","params":{"provider":"openai_compatible","model":"model-1","prompt":"create a log","executionModel":"sequence","workflows":["Main"]}})
    assert replies[-1]["result"]["warnings"]==["Retried with schema-guided JSON"]
    assert ("ai.structured_output_fallback",{"provider":"openai_compatible","model":"model-1"}) in audits


def test_bridge_forwards_custom_auth_header_to_model_catalog_and_drafting(monkeypatch):
    replies=[];seen={}
    monkeypatch.setattr(bridge,"send",replies.append)
    def models(*args):
        seen["models"]=args
        return ["model-x"]
    monkeypatch.setattr(bridge.ai_providers,"models",models)
    def draft(*args,**kwargs):
        seen["draft"]=(args,kwargs)
        return {"explanation":"ok","activities":[{"id":"message","type":"log","message":"hello"}]}
    monkeypatch.setattr(bridge.ai_providers,"draft",draft)
    common={"provider":"openai_compatible","baseUrl":"https://gateway.example/v1","credentialService":"vault-service",
        "credentialUsername":"primary","credentialMode":"api_key_header","credentialHeader":"x-api-key"}
    bridge.handle({"id":31,"method":"ai.models","params":common})
    bridge.handle({"id":32,"method":"ai.draft","params":{**common,"model":"model-x","prompt":"write a log","workflows":["Main"]}})
    assert seen["models"]==("openai_compatible","https://gateway.example/v1","vault-service","primary","api_key_header","x-api-key")
    assert seen["draft"][1]["credential_mode"]=="api_key_header"
    assert seen["draft"][1]["credential_header"]=="x-api-key"
    assert seen["draft"][1]["activity_catalog"]==bridge.ACTIVITY_CATALOG
    assert "vault-secret" not in str(replies)


def test_bridge_end_to_end_local_provider_fallback_is_validated_and_disclosed(monkeypatch):
    replies=[];audits=[];requests=[]
    payload={"explanation":"Write a log entry.","activities":[{"id":"message","type":"log","message":"hello"}]}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))))
            requests.append(body)
            if "response_format" in body:
                self.send_response(400);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(b'{"error":{"message":"response_format json_schema is not supported"}}')
                return
            encoded=json.dumps({"choices":[{"message":{"content":json.dumps(payload)}}]}).encode()
            self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(encoded)));self.end_headers()
            self.wfile.write(encoded)
        def log_message(self,*_args):pass
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda action,details:audits.append((action,details)))
    try:
        bridge.handle({"id":10,"method":"ai.draft","params":{"provider":"local_openai_compatible","model":"test-model","baseUrl":f"http://127.0.0.1:{server.server_port}/v1","prompt":"write a log","executionModel":"sequence","workflows":["Main"]}})
    finally:
        server.shutdown();thread.join(timeout=2);server.server_close()
    result=replies[-1]["result"]
    assert result["valid"] is True and result["workflow"]["activities"]==payload["activities"]
    assert len(result["warnings"])==1 and len(requests)==2
    assert ("ai.structured_output_fallback",{"provider":"local_openai_compatible","model":"test-model"}) in audits
