from __future__ import annotations

import json
import uuid

import pytest

from openrpa import ai_connections


def test_local_profiles_persist_endpoint_model_and_update_by_id(tmp_path):
    path=tmp_path/"ai-connections.json"
    saved=ai_connections.save_profile(path,{"name":"Local Ollama","provider":"ollama","baseUrl":"http://127.0.0.1:11434","model":"qwen3"})
    assert saved["id"]
    assert ai_connections.list_profiles(path)==[saved]
    updated=ai_connections.save_profile(path,{**saved,"model":"llama3"})
    assert updated["id"]==saved["id"] and updated["model"]=="llama3"
    document=json.loads(path.read_text(encoding="utf-8"))
    assert document["format"]=="openrpa.ai-connections"
    assert len(document["profiles"])==1


def test_remote_profile_persists_only_os_vault_references(tmp_path):
    path=tmp_path/"ai-connections.json"
    profile=ai_connections.save_profile(path,{"name":"OpenRouter work","provider":"openrouter","model":"openai/gpt-4o-mini",
        "credentialService":"openrpa-openrouter","credentialUsername":"work-key"})
    text=path.read_text(encoding="utf-8")
    assert profile["credentialService"]=="openrpa-openrouter"
    assert "secret" not in text.lower() and "apiKey" not in text
    assert "work-key" in text and "openai/gpt-4o-mini" in text


def test_openai_responses_profile_is_distinct_and_round_trips(tmp_path):
    path=tmp_path/"ai-connections.json"
    profile=ai_connections.save_profile(path,{"name":"OpenAI Responses","provider":"openai_responses",
        "credentialService":"openrpa-openai_responses","credentialUsername":"work-key"})
    assert profile["provider"]=="openai_responses"
    assert ai_connections.list_profiles(path)==[profile]


@pytest.mark.parametrize("profile,match",[
    ({"name":"Missing key","provider":"openai"},"vault service and username"),
    ({"name":"Remote HTTP","provider":"openai_compatible","baseUrl":"http://api.example/v1","credentialService":"s","credentialUsername":"u"},"HTTPS"),
    ({"name":"Remote loopback","provider":"openai_compatible","baseUrl":"https://127.0.0.1/v1","credentialService":"s","credentialUsername":"u"},"loopback"),
    ({"name":"Local network","provider":"ollama","baseUrl":"http://192.168.1.3:11434"},"loopback"),
])
def test_connection_profiles_validate_provider_security(profile,match):
    with pytest.raises(ValueError,match=match):
        ai_connections._normalize(profile)


def test_profiles_reject_secret_fields_and_duplicate_names(tmp_path):
    path=tmp_path/"ai-connections.json"
    with pytest.raises(ValueError,match="unsupported fields"):
        ai_connections.save_profile(path,{"name":"Local","provider":"ollama","secret":"not allowed"})
    ai_connections.save_profile(path,{"name":"Primary","provider":"ollama"})
    with pytest.raises(ValueError,match="already exists"):
        ai_connections.save_profile(path,{"name":"primary","provider":"ollama"})


def test_profiles_reject_corrupt_documents_and_delete(tmp_path):
    path=tmp_path/"ai-connections.json"
    profile=ai_connections.save_profile(path,{"name":"Local","provider":"lm_studio"})
    ai_connections.delete_profile(path,profile["id"])
    assert ai_connections.list_profiles(path)==[]
    path.write_text(json.dumps({"format":"wrong","formatVersion":1,"profiles":[]}),encoding="utf-8")
    with pytest.raises(ValueError,match="Unsupported"):
        ai_connections.list_profiles(path)


def test_delete_requires_existing_well_formed_uuid(tmp_path):
    path=tmp_path/"ai-connections.json"
    with pytest.raises(ValueError,match="invalid"):
        ai_connections.delete_profile(path,"bad-id")
    with pytest.raises(ValueError,match="not found"):
        ai_connections.delete_profile(path,str(uuid.uuid4()))


def test_native_bridge_lists_saves_and_deletes_connection_profiles(tmp_path,monkeypatch):
    from openrpa import bridge
    replies=[]
    audit=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge,"_ai_connections_path",lambda:tmp_path/"ai-connections.json")
    monkeypatch.setattr(bridge.history,"audit",lambda action,details:audit.append((action,details)))
    bridge.handle({"id":1,"method":"ai.connections.save","params":{"profile":{"name":"Dev Ollama","provider":"ollama","model":"qwen3"}}})
    saved=replies[-1]["result"]["profile"]
    assert saved["model"]=="qwen3"
    bridge.handle({"id":2,"method":"ai.connections.list","params":{}})
    assert replies[-1]["result"]["profiles"]==[saved]
    bridge.handle({"id":3,"method":"ai.connections.delete","params":{"profileId":saved["id"]}})
    assert replies[-1]["result"]["deleted"] is True
    assert [row[0] for row in audit]==["ai.connection.save","ai.connection.delete"]
    assert "secret" not in str(audit).lower()
