from __future__ import annotations

import json
import queue
import time
from pathlib import Path

from openrpa import bridge
from openrpa.history import RunHistory


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
