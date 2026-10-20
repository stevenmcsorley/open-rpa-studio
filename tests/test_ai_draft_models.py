from __future__ import annotations

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
