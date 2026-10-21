from __future__ import annotations

import json
import queue
import time
from pathlib import Path

from openrpa import bridge
from openrpa.history import RunHistory
from openrpa.mcp_server import ProjectMCPServer


def test_desktop_bridge_passes_run_inputs_into_workflow_execution(tmp_path: Path, monkeypatch):
    messages: queue.Queue = queue.Queue()
    monkeypatch.setattr(bridge, "send", messages.put)
    monkeypatch.setattr(bridge, "history", RunHistory(tmp_path / "history.sqlite3"))
    root = tmp_path / "project"
    root.mkdir()
    workflow = {
        "format": "openrpa.workflow",
        "formatVersion": 1,
        "name": "Main",
        "variables": [],
        "arguments": [
            {"name": "supplier", "type": "string", "direction": "in"},
            {"name": "limit", "type": "integer", "direction": "in"},
        ],
        "activities": [{"id": "log-inputs", "type": "log", "message": "{{supplier}} / {{limit}}"}],
    }
    project = {"format": "openrpa.project", "formatVersion": 1, "name": "Input acceptance", "main": "Main", "workflows": {"Main": "main.json"}}
    (root / "main.json").write_text(json.dumps(workflow), encoding="utf-8")

    bridge.handle({"id": 1, "method": "workflow.run", "params": {"project": project, "root": str(root), "workflow": "Main", "inputs": {"supplier": "Northwind", "limit": 12}}})

    result_message = None
    run_events = []
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        message = messages.get(timeout=max(0.01, deadline - time.monotonic()))
        if message.get("id") == 1:
            result_message = message
            break
        if message.get("event") == "run.event":
            run_events.append(message["data"])
    assert result_message is not None
    result = result_message["result"]
    assert result["status"] == "succeeded"
    assert result["variables"]["supplier"] == "Northwind"
    assert result["variables"]["limit"] == 12
    assert any(event.get("event") == "log" and event.get("message") == "Northwind / 12" for event in run_events)


def test_desktop_bridge_reads_and_clears_validated_mcp_live_draft(tmp_path:Path,monkeypatch):
    messages:queue.Queue=queue.Queue();monkeypatch.setattr(bridge,"send",messages.put);monkeypatch.setattr(bridge,"history",RunHistory(tmp_path/"history.sqlite3"))
    root=tmp_path/"project";root.mkdir();(root/"workflows").mkdir()
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"saved","type":"log","level":"info","message":"saved"}]}
    project={"format":"openrpa.project","formatVersion":1,"name":"Live preview","main":"Main","workflows":{"Main":"workflows/main.json"}}
    (root/"project.json").write_text(json.dumps(project),encoding="utf-8");(root/"workflows/main.json").write_text(json.dumps(workflow),encoding="utf-8")
    draft={"format":"openrpa.live-workflow-draft","formatVersion":1,"draftId":"preview-1","name":"Main","updatedAt":1234,"workflow":{**workflow,"activities":[{"id":"draft","type":"log","level":"info","message":"preview"}]}}
    (root/".openrpa").mkdir();(root/".openrpa/mcp-live-draft.json").write_text(json.dumps(draft),encoding="utf-8")
    bridge.handle({"id":2,"method":"project.live_draft.read","params":{"root":str(root)}})
    result=messages.get_nowait()["result"]["draft"]
    assert result["draftId"]=="preview-1" and result["workflow"]["activities"][0]["message"]=="preview"
    bridge.handle({"id":3,"method":"project.live_draft.clear","params":{"root":str(root),"draftId":"old-preview"}})
    assert messages.get_nowait()["result"]["cleared"] is False
    bridge.handle({"id":4,"method":"project.live_draft.clear","params":{"root":str(root),"draftId":"preview-1"}})
    assert messages.get_nowait()["result"]["cleared"] is True and not (root/".openrpa/mcp-live-draft.json").exists()
    unrelated=tmp_path/"unrelated";target=unrelated/".openrpa/mcp-live-draft.json";target.parent.mkdir(parents=True);target.write_text("keep",encoding="utf-8")
    bridge.handle({"id":5,"method":"project.live_draft.clear","params":{"root":str(unrelated)}})
    assert "error" in messages.get_nowait() and target.read_text(encoding="utf-8")=="keep"


def test_mcp_staged_snapshot_flows_into_studio_bridge_and_commit_clears_it(tmp_path:Path,monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR",str(tmp_path/"app-data"))
    replies=[];monkeypatch.setattr(bridge,"send",replies.append)
    root=tmp_path/"shared";root.mkdir();(root/"workflows").mkdir()
    saved={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"old","type":"log","level":"info","message":"saved"}]}
    project={"format":"openrpa.project","formatVersion":1,"name":"Shared","main":"Main","workflows":{"Main":"workflows/main.json"}}
    (root/"project.json").write_text(json.dumps(project),encoding="utf-8");path=root/"workflows/main.json";path.write_text(json.dumps(saved),encoding="utf-8")
    server=ProjectMCPServer(str(root),allow_edit=True)
    draft={**saved,"activities":[{"id":"new","type":"log","level":"info","message":"building live"}]}
    response=server.handle({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"openrpa_stage_workflow_draft","arguments":{"name":"Main","workflow":draft}}})["result"]["structuredContent"]
    assert response["staged"] is True
    bridge.handle({"id":2,"method":"project.live_draft.read","params":{"root":str(root)}})
    assert replies[-1]["result"]["draft"]["workflow"]["activities"][0]["message"]=="building live"
    current=server.handle({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"openrpa_read_workflow","arguments":{"name":"Main"}}})["result"]["structuredContent"]
    final={**draft,"activities":[*draft["activities"],{"id":"done","type":"log","level":"info","message":"complete"}]}
    updated=server.handle({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"openrpa_update_workflow","arguments":{"name":"Main","expectedSha256":current["sha256"],"workflow":final}}})["result"]["structuredContent"]
    assert updated["updated"] is True and not (root/".openrpa/mcp-live-draft.json").exists()
