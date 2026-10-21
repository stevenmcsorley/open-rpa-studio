from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openrpa.orchestration import JobQueue, read_jobs, request_job_cancel
from openrpa.mcp_server import ProjectMCPServer


def _project(root: Path) -> None:
    (root / "workflows").mkdir(parents=True)
    (root / "project.json").write_text(json.dumps({
        "format": "openrpa.project", "formatVersion": 1, "name": "Queue test",
        "main": "Main", "workflows": {"Main": "workflows/main.workflow.json"},
    }), encoding="utf-8")
    (root / "workflows/main.workflow.json").write_text(json.dumps({
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Main",
        "variables": [], "arguments": [],
        "activities": [{"id": "hello", "type": "log", "level": "info", "message": "queued run completed"}],
    }), encoding="utf-8")


def _call(server: ProjectMCPServer, name: str, arguments: dict | None = None) -> dict:
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": name, "arguments": arguments or {}}})
    return response["result"]["structuredContent"]


def test_queue_is_durable_idempotent_scheduled_and_never_replays(tmp_path: Path):
    queue = JobQueue(tmp_path / "queue.sqlite3")
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    first = queue.enqueue(project_path="/project", project_name="P", workflow="Main",
                          snapshot_sha256="a" * 64, inputs={}, available_at=future, idempotency_key="once")
    repeated = queue.enqueue(project_path="/project", project_name="P", workflow="Main",
                             snapshot_sha256="a" * 64, inputs={}, available_at=future, idempotency_key="once")
    assert first["status"] == "scheduled"
    assert repeated["jobId"] == first["jobId"] and repeated["alreadyExisted"]
    assert queue.claim_due("/project") is None
    assert queue.cancel("/project", first["jobId"])["status"] == "cancelled"

    immediate = queue.enqueue(project_path="/project", project_name="P", workflow="Main",
                              snapshot_sha256="b" * 64, inputs={}, available_at=datetime.now(timezone.utc).isoformat())
    claimed = queue.claim_due("/project")
    assert claimed["jobId"] == immediate["jobId"] and claimed["status"] == "running"
    restarted = JobQueue(tmp_path / "queue.sqlite3")
    record = restarted.get("/project", immediate["jobId"])
    assert record["status"] == "interrupted"
    assert restarted.claim_due("/project") is None


def test_queue_read_only_view_and_cross_process_cancel_request(tmp_path: Path):
    path = tmp_path / "queue.sqlite3"
    queue = JobQueue(path)
    queued = queue.enqueue(project_path="/project", project_name="P", workflow="Main",
                           snapshot_sha256="c" * 64, inputs={"secret": "never shown"},
                           available_at=datetime.now(timezone.utc).isoformat())
    assert read_jobs(path, "/project")[0]["jobId"] == queued["jobId"]
    assert "inputs" not in read_jobs(path, "/project")[0]
    queue.claim_due("/project")
    cancelled = request_job_cancel(path, "/project", queued["jobId"])
    assert cancelled["status"] == "running" and cancelled["cancelRequested"] is True
    assert queue.get("/project", queued["jobId"])["status"] == "running"


def test_mcp_job_worker_runs_saved_workflow_and_links_run_history(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(data_dir))
    _project(tmp_path / "project")
    server = ProjectMCPServer(str(tmp_path / "project"), allow_run=True)
    tool_names = {tool["name"] for tool in server._tools()}
    assert {"openrpa_submit_job", "openrpa_get_job", "openrpa_list_jobs", "openrpa_cancel_job"} <= tool_names

    submitted = _call(server, "openrpa_submit_job", {"name": "Main", "idempotencyKey": "run-once"})
    assert submitted["status"] in {"queued", "running", "succeeded"}
    assert "inputs" not in submitted and "idempotencyKey" not in submitted
    deadline = time.monotonic() + 5
    job = submitted
    while time.monotonic() < deadline and job["status"] not in {"succeeded", "failed", "cancelled", "workflow_changed"}:
        time.sleep(0.02)
        job = _call(server, "openrpa_get_job", {"jobId": submitted["jobId"]})
    assert job["status"] == "succeeded", job
    assert job["runId"]
    assert _call(server, "openrpa_list_jobs")["automaticRetries"] is False


def test_mcp_job_submit_rejects_unsafe_schedule_and_permissions(tmp_path: Path):
    _project(tmp_path / "project")
    server = ProjectMCPServer(str(tmp_path / "project"), allow_run=True)
    future = (datetime.now(timezone.utc) + timedelta(days=400)).isoformat()
    response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "openrpa_submit_job", "arguments": {"name": "Main", "runAt": future}}})
    assert response["result"]["isError"] is True
    assert "365 days" in response["result"]["content"][0]["text"]


def test_mcp_job_cooperative_cancellation_stops_at_activity_boundary(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    _project(tmp_path / "project")
    workflow_path = tmp_path / "project" / "workflows" / "main.workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["activities"] = [{"id": "wait", "type": "wait", "seconds": 8}]
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    server = ProjectMCPServer(str(tmp_path / "project"), allow_run=True)
    submitted = _call(server, "openrpa_submit_job", {"name": "Main"})
    deadline = time.monotonic() + 5
    job = submitted
    while time.monotonic() < deadline and job["status"] not in {"running", "failed"}:
        time.sleep(0.02)
        job = _call(server, "openrpa_get_job", {"jobId": submitted["jobId"]})
    assert job["status"] == "running", job
    requested = _call(server, "openrpa_cancel_job", {"jobId": submitted["jobId"]})
    assert requested["cancelRequested"] is True
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and job["status"] not in {"cancelled", "failed"}:
        time.sleep(0.02)
        job = _call(server, "openrpa_get_job", {"jobId": submitted["jobId"]})
    assert job["status"] == "cancelled", job
    assert job["runId"]


def test_queued_job_fails_closed_if_saved_workflow_changes(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(data_dir))
    project = tmp_path / "project"
    _project(project)
    server = ProjectMCPServer(str(project), allow_run=True)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    submitted = _call(server, "openrpa_submit_job", {"name": "Main", "runAt": future})
    queue_path = next(data_dir.glob("job-queue-*.sqlite3"))
    workflow_path = project / "workflows" / "main.workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["activities"][0]["message"] = "changed after queue submission"
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")
    with sqlite3.connect(queue_path) as db:
        db.execute("UPDATE jobs SET available_at=? WHERE job_id=?", (datetime.now(timezone.utc).isoformat(), submitted["jobId"]))
    server._job_worker_wake.set()
    deadline = time.monotonic() + 5
    job = submitted
    while time.monotonic() < deadline and job["status"] not in {"workflow_changed", "failed"}:
        time.sleep(0.02)
        job = _call(server, "openrpa_get_job", {"jobId": submitted["jobId"]})
    assert job["status"] == "workflow_changed", job
    assert job["runId"] is None
