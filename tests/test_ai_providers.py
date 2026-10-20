import json

import pytest

from openrpa import ai_providers as ai


def test_provider_catalog_includes_local_and_remote_families():
    ids={item["id"] for item in ai.catalog()}
    assert {"ollama","lm_studio","local_openai_compatible","openai","claude","openrouter","openai_compatible"} <= ids


@pytest.mark.parametrize("provider,url",[
    ("ollama","http://127.0.0.1:11434"),
    ("lm_studio","http://localhost:1234/v1"),
    ("local_openai_compatible","http://127.0.0.1:8000/v1"),
])
def test_local_providers_are_loopback_only(provider,url):
    endpoint,local=ai._endpoint(provider,url,"/models")
    assert local and endpoint.endswith("/models")
    with pytest.raises(ValueError): ai._endpoint(provider,url.replace("127.0.0.1","192.168.1.2").replace("localhost","192.168.1.2"),"/models")


def test_remote_provider_requires_https_and_public_host():
    with pytest.raises(ValueError,match="HTTPS"):
        ai._endpoint("openai_compatible","http://example.com/v1","/models")
    with pytest.raises(ValueError,match="loopback"):
        ai._endpoint("openai_compatible","https://127.0.0.1/v1","/models")


def test_models_calls_openai_compatible_endpoint(monkeypatch):
    seen={}
    def call(url,local,**kwargs):
        seen["url"]=url
        return {"data":[{"id":"model-a"},{"id":"model-b"}]}
    monkeypatch.setattr(ai,"_call",call)
    assert ai.models("openai_compatible","https://api.example/v1")==["model-a","model-b"]
    assert seen["url"]=="https://api.example/v1/models"


def test_openai_draft_is_json_parsed_and_uses_schema(monkeypatch):
    seen={}
    def call(url,local,method="GET",**kwargs):
        seen.update(url=url,method=method,body=kwargs["body"])
        return {"choices":[{"message":{"content":json.dumps({"explanation":"safe","activities":[{"id":"x","type":"log","message":"hello"}]})}}]}
    monkeypatch.setattr(ai,"_call",call)
    result=ai.draft("openai_compatible","model-x","make a log",["log"],"https://api.example/v1")
    assert result["activities"][0]["type"]=="log"
    assert seen["url"].endswith("/chat/completions") and seen["method"]=="POST"
    assert seen["body"]["response_format"]["type"]=="json_schema"


def test_claude_draft_uses_tool_schema(monkeypatch):
    monkeypatch.setattr(ai,"_credential",lambda *_:"secret-token")
    seen={}
    def call(url,local,method="GET",**kwargs):
        seen.update(url=url,body=kwargs["body"],secret=kwargs["secret"])
        return {"content":[{"type":"tool_use","name":"create_workflow","input":{"explanation":"x","activities":[{"id":"a","type":"log"}]}}]}
    monkeypatch.setattr(ai,"_call",call)
    result=ai.draft("claude","claude-test","write log",["log"],credential_service="s",credential_username="u")
    assert result["activities"][0]["id"]=="a"
    assert seen["url"]=="https://api.anthropic.com/v1/messages"
    assert seen["body"]["tool_choice"]["name"]=="create_workflow"
    assert seen["secret"]=="secret-token"


def test_ollama_malformed_draft_fails_closed(monkeypatch):
    monkeypatch.setattr(ai,"_call",lambda *a,**k:{"response":"not json"})
    with pytest.raises(ValueError,match="malformed structured output"):
        ai.draft("ollama","model-x","do a thing",["log"])
