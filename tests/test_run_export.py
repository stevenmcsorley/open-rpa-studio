from __future__ import annotations

import hashlib
import json

from openrpa import bridge
from openrpa.history import RunHistory


def test_run_export_writes_versioned_evidence_and_audits_digest(tmp_path, monkeypatch):
    replies = []
    history = RunHistory(tmp_path / "history.sqlite3")
    audits = []
    monkeypatch.setattr(bridge, "history", history)
    monkeypatch.setattr(bridge, "send", replies.append)
    monkeypatch.setattr(history, "audit", lambda action, details: audits.append((action, details)))
    run_id = history.start(str(tmp_path / "project"), "Example project", "Main", "a" * 64)
    history.event(run_id, {"event": "activity-completed", "activityId": "step-1", "type": "log", "message": "Finished"})
    history.finish(run_id, "succeeded", {"status": "succeeded", "activities": {"step-1": {"status": "succeeded"}}})
    destination = tmp_path / "review" / "run.json"

    bridge.handle({"id": 1, "method": "run.export", "params": {"runId": run_id, "destination": str(destination)}})

    envelope = json.loads(destination.read_text(encoding="utf-8"))
    expected_bytes = (json.dumps(envelope, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    assert envelope["format"] == "openrpa.run-evidence"
    assert envelope["formatVersion"] == 1
    assert envelope["run"]["runId"] == run_id
    assert envelope["run"]["events"][0]["message"] == "Finished"
    assert replies[-1]["result"] == {"sha256": hashlib.sha256(expected_bytes).hexdigest(), "bytes": len(expected_bytes)}
    assert audits == [("run.export", {"runId": run_id, "sha256": hashlib.sha256(expected_bytes).hexdigest(), "bytes": len(expected_bytes)})]
    assert str(destination) not in json.dumps(audits)


def test_run_export_rejects_unknown_run_without_creating_output(tmp_path, monkeypatch):
    replies = []
    monkeypatch.setattr(bridge, "history", RunHistory(tmp_path / "history.sqlite3"))
    monkeypatch.setattr(bridge, "send", replies.append)
    destination = tmp_path / "must-not-exist.json"

    bridge.handle({"id": 1, "method": "run.export", "params": {"runId": "missing", "destination": str(destination)}})

    assert "no longer exists" in replies[-1]["error"]["message"]
    assert not destination.exists()
