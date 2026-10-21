import json
import os
import copy
import hashlib
import subprocess
import sys
import threading
import time
from queue import Queue
from pathlib import Path

from openrpa.mcp_server import ProjectMCPServer


def make_project(root: Path, activities=None):
    (root / "workflows").mkdir(parents=True)
    (root / "project.json").write_text(json.dumps({
        "format": "openrpa.project", "formatVersion": 1, "name": "MCP fixture",
        "main": "Main", "workflows": {"Main": "workflows/main.workflow.json"},
    }), encoding="utf-8")
    (root / "workflows/main.workflow.json").write_text(json.dumps({
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Main",
        "variables": [], "arguments": [], "activities": activities or [
            {"id": "hello", "type": "log", "level": "info", "message": "hello"}
        ],
    }), encoding="utf-8")


def call(server, name, arguments=None):
    response = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}})
    return response["result"]


def test_tools_are_project_scoped_and_execution_is_opt_in(tmp_path):
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path))
    info = call(server, "openrpa_project_info")["structuredContent"]
    assert info["projectName"] == "MCP fixture"
    assert not info["projectRootExposed"]
    assert "openrpa_run_workflow" not in {item["name"] for item in server._tools()}
    assert "openrpa_update_workflow" not in {item["name"] for item in server._tools()}
    assert "openrpa_create_workflow" not in {item["name"] for item in server._tools()}
    assert "openrpa_activity_catalog" in {item["name"] for item in server._tools()}
    assert call(server, "openrpa_validate_project")["structuredContent"]["valid"]
    assert call(server, "openrpa_read_workflow", {"name": "Main"})["structuredContent"]["workflow"]["name"] == "Main"
    denied = call(server, "openrpa_update_workflow", {"name": "Main"})
    assert denied["isError"] is True
    assert "--allow-edit" in denied["content"][0]["text"]


def test_mcp_activity_catalog_is_native_and_labels_required_permissions(tmp_path):
    from openrpa.activity_catalog import ACTIVITY_CATALOG

    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path))
    result = call(server, "openrpa_activity_catalog")["structuredContent"]["activities"]
    assert [item["type"] for item in result] == [item["type"] for item in ACTIVITY_CATALOG]
    by_type = {item["type"]: item for item in result}
    assert by_type["browser_navigate"]["requiredPermissions"] == ["network"]
    assert by_type["desktop_click"]["requiredPermissions"] == ["desktop"]
    assert by_type["credential_get"]["requiredPermissions"] == ["credentials"]
    assert by_type["file_delete"]["requiredPermissions"] == ["destructive"]


def test_browser_navigation_is_preflighted_as_network_access(tmp_path):
    make_project(tmp_path, [{"id": "navigate", "type": "browser_navigate", "url": "https://example.org"}])
    server = ProjectMCPServer(str(tmp_path), allow_run=True)
    plan = call(server, "openrpa_plan_workflow", {"name": "Main"})["structuredContent"]
    assert plan["requires"]["network"] is True
    result = call(server, "openrpa_run_workflow", {"name": "Main"})
    assert result["isError"] is True
    assert "browser navigation" in result["content"][0]["text"]
    assert "--allow-network" in result["content"][0]["text"]


def test_opt_in_edit_requires_current_digest_and_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_edit=True)
    initial = call(server, "openrpa_read_workflow", {"name": "Main"})["structuredContent"]
    proposed = copy.deepcopy(initial["workflow"])
    proposed["activities"][0]["message"] = "edited by a reviewed agent"
    update = call(server, "openrpa_update_workflow", {"name": "Main", "expectedSha256": initial["sha256"], "workflow": proposed})
    assert update["structuredContent"]["updated"] is True
    saved = call(server, "openrpa_read_workflow", {"name": "Main"})["structuredContent"]
    assert saved["workflow"]["activities"][0]["message"] == "edited by a reviewed agent"
    assert saved["sha256"] == update["structuredContent"]["sha256"]
    stale = call(server, "openrpa_update_workflow", {"name": "Main", "expectedSha256": initial["sha256"], "workflow": initial["workflow"]})
    assert stale["isError"] is True
    invalid = copy.deepcopy(saved["workflow"])
    invalid["activities"][0].pop("type")
    rejected = call(server, "openrpa_update_workflow", {"name": "Main", "expectedSha256": saved["sha256"], "workflow": invalid})
    assert rejected["structuredContent"]["updated"] is False
    assert "type" in json.dumps(rejected["structuredContent"]["problems"])
    assert call(server, "openrpa_read_workflow", {"name": "Main"})["structuredContent"]["sha256"] == saved["sha256"]


def test_create_workflow_is_project_hash_guarded_and_validates_bindings(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_edit=True)
    initial = call(server, "openrpa_project_info")["structuredContent"]
    workflow = {
        "format": "openrpa.workflow", "formatVersion": 1, "name": "ignored supplied name",
        "variables": [], "arguments": [], "activities": [
            {"id": "helper-log", "type": "log", "level": "info", "message": "shared helper"}
        ],
    }
    created = call(server, "openrpa_create_workflow", {
        "name": "Shared Helper", "expectedProjectSha256": initial["projectSha256"], "workflow": workflow,
    })["structuredContent"]
    assert created["created"] is True
    assert created["workflowPath"] == "workflows/shared-helper.workflow.json"
    assert created["projectSha256"] == hashlib.sha256((tmp_path / "project.json").read_bytes()).hexdigest()
    assert call(server, "openrpa_list_workflows")["structuredContent"]["workflows"][-1]["name"] == "Shared Helper"
    saved = call(server, "openrpa_read_workflow", {"name": "Shared Helper"})["structuredContent"]
    assert saved["workflow"]["name"] == "Shared Helper"
    assert saved["sha256"] == created["workflowSha256"]
    assert call(server, "openrpa_validate_project")["structuredContent"]["workflowCount"] == 2
    reopened = ProjectMCPServer(str(tmp_path))
    assert call(reopened, "openrpa_validate_project")["structuredContent"]["workflowCount"] == 2

    stale = call(server, "openrpa_create_workflow", {
        "name": "Second Helper", "expectedProjectSha256": initial["projectSha256"], "workflow": workflow,
    })
    assert stale["isError"] is True
    assert "Project changed since it was read" in stale["content"][0]["text"]
    assert call(server, "openrpa_list_workflows")["structuredContent"]["workflows"][-1]["name"] == "Shared Helper"


def test_create_workflow_rejects_unresolved_invocations_without_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_edit=True)
    project_hash = call(server, "openrpa_project_info")["structuredContent"]["projectSha256"]
    invalid = {
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Unresolved",
        "variables": [], "arguments": [], "activities": [
            {"id": "call-missing", "type": "invoke_workflow", "workflow": "Missing", "inputs": {}}
        ],
    }
    result = call(server, "openrpa_create_workflow", {
        "name": "Unresolved", "expectedProjectSha256": project_hash, "workflow": invalid,
    })["structuredContent"]
    assert result["created"] is False
    assert any(problem.get("code") == "workflow-ref" for problem in result["problems"])
    assert not (tmp_path / "workflows/unresolved.workflow.json").exists()
    assert call(server, "openrpa_validate_project")["structuredContent"]["workflowCount"] == 1


def test_create_workflow_rejects_path_separators(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_edit=True)
    project_hash = call(server, "openrpa_project_info")["structuredContent"]["projectSha256"]
    workflow = {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": []}
    result = call(server, "openrpa_create_workflow", {
        "name": "../escaped", "expectedProjectSha256": project_hash, "workflow": workflow,
    })
    assert result["isError"] is True
    assert "path separators" in result["content"][0]["text"]
    assert call(server, "openrpa_validate_project")["structuredContent"]["workflowCount"] == 1


def test_validate_workflow_draft_bundle_checks_cross_references_without_writing(tmp_path):
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path))
    manifest = (tmp_path / "project.json").read_bytes()
    drafts = {
        "Wrapper": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [
            {"id": "call-helper", "type": "invoke_workflow", "workflow": "Helper", "inputs": {}}
        ]},
        "Helper": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [
            {"id": "helper-log", "type": "log", "level": "info", "message": "draft only"}
        ]},
    }
    result = call(server, "openrpa_validate_workflow_drafts", {"workflows": drafts})["structuredContent"]
    assert result["valid"] is True
    assert result["workflowNames"] == ["Wrapper", "Helper"]
    assert result["problems"] == []
    assert (tmp_path / "project.json").read_bytes() == manifest
    assert not (tmp_path / "workflows/wrapper.workflow.json").exists()
    assert not (tmp_path / "workflows/helper.workflow.json").exists()

    invalid = {"Broken": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [
        {"id": "call-missing", "type": "invoke_workflow", "workflow": "Unknown", "inputs": {}}
    ]}}
    failed = call(server, "openrpa_validate_workflow_drafts", {"workflows": invalid})["structuredContent"]
    assert failed["valid"] is False
    assert any(item.get("workflow") == "Broken" and item.get("code") == "workflow-ref" for item in failed["problems"])
    assert (tmp_path / "project.json").read_bytes() == manifest


def test_nested_destructive_permissions_are_detected(tmp_path):
    make_project(tmp_path, [{"id": "invoke", "type": "invoke_workflow", "workflow": "Cleanup"}])
    (tmp_path / "workflows/cleanup.workflow.json").write_text(json.dumps({
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Cleanup",
        "variables": [], "arguments": [],
        "activities": [{"id": "delete", "type": "file_delete", "path": "output.txt"}],
    }), encoding="utf-8")
    project = json.loads((tmp_path / "project.json").read_text(encoding="utf-8"))
    project["workflows"]["Cleanup"] = "workflows/cleanup.workflow.json"
    (tmp_path / "project.json").write_text(json.dumps(project), encoding="utf-8")
    server = ProjectMCPServer(str(tmp_path), allow_run=True)
    plan = call(server, "openrpa_plan_workflow", {"name": "Main"})["structuredContent"]
    assert plan["requires"]["destructive"] is True
    result = call(server, "openrpa_run_workflow", {"name": "Main"})
    assert result["isError"] is True
    assert "--allow-destructive" in result["content"][0]["text"]


def test_vault_credential_use_has_separate_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path, [{"id": "read-secret", "type": "credential_get", "service": "test", "username": "test", "result": "secret"}])
    server = ProjectMCPServer(str(tmp_path), allow_run=True)
    plan = call(server, "openrpa_plan_workflow", {"name": "Main"})["structuredContent"]
    assert plan["requires"]["credentials"] is True
    result = call(server, "openrpa_run_workflow", {"name": "Main"})
    assert result["isError"] is True
    assert "--allow-credentials" in result["content"][0]["text"]


def test_stdio_protocol_end_to_end(tmp_path):
    make_project(tmp_path)
    repository = Path(__file__).resolve().parents[1]
    manifest_hash=hashlib.sha256((tmp_path / "project.json").read_bytes()).hexdigest()
    env = dict(os.environ, PYTHONPATH=str(repository), OPENRPA_DATA_DIR=str(tmp_path / "data"))
    request_lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "openrpa_list_workflows", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "openrpa_activity_catalog", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "openrpa_validate_workflow_drafts", "arguments": {"workflows": {"Shared Helper": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [{"id": "helper-log", "type": "log", "level": "info", "message": "validated draft"}]}}}}},
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "openrpa_create_workflow", "arguments": {"name": "Shared Helper", "expectedProjectSha256": manifest_hash, "workflow": {"format": "openrpa.workflow", "formatVersion": 1, "variables": [], "arguments": [], "activities": [{"id": "helper-log", "type": "log", "level": "info", "message": "created over MCP"}]}}}},
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "openrpa_validate_project", "arguments": {}}},
    ]
    payload = "".join(json.dumps(line) + "\n" for line in request_lines)
    process = subprocess.run([sys.executable, "-m", "openrpa", "mcp", str(tmp_path), "--allow-edit"], cwd=repository,
                             env=env, input=payload, text=True, capture_output=True, timeout=15)
    assert process.returncode == 0, process.stderr
    assert process.stderr == ""
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert [response["id"] for response in responses] == [1, 2, 3, 4, 5, 6, 7]
    assert responses[0]["result"]["serverInfo"]["name"] == "open-rpa-studio"
    assert responses[2]["result"]["structuredContent"]["workflows"][0]["name"] == "Main"
    activities = responses[3]["result"]["structuredContent"]["activities"]
    assert any(item["type"] == "browser_navigate" and item["requiredPermissions"] == ["network"] for item in activities)
    assert responses[4]["result"]["structuredContent"]["valid"] is True
    assert responses[5]["result"]["structuredContent"]["created"] is True
    assert responses[6]["result"]["structuredContent"]["workflowCount"] == 2


def test_run_opt_in_executes_a_real_workflow_and_records_durable_history(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(tmp_path / "data"))
    make_project(tmp_path)
    server = ProjectMCPServer(str(tmp_path), allow_run=True)
    result = call(server, "openrpa_run_workflow", {"name": "Main"})
    assert result["isError"] is False
    assert result["structuredContent"]["status"] == "succeeded"
    assert result["structuredContent"]["runId"]
    runs = call(server, "openrpa_list_run_history")["structuredContent"]["runs"]
    assert runs[0]["status"] == "succeeded"
    assert "projectPath" not in runs[0]


def test_stdio_cancellation_notification_stops_active_run(tmp_path):
    make_project(tmp_path, [{"id": "loop", "type": "while", "condition": "True", "body": [
        {"id": "wait", "type": "wait", "seconds": 30}
    ]}])
    repository = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(repository), OPENRPA_DATA_DIR=str(tmp_path / "data"))
    process = subprocess.Popen([sys.executable, "-m", "openrpa", "mcp", str(tmp_path), "--allow-run"],
                               cwd=repository, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, bufsize=1)
    responses = Queue()
    def read_stdout():
        for line in process.stdout:
            responses.put(json.loads(line))
    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    try:
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}}) + "\n")
        process.stdin.flush()
        assert responses.get(timeout=5)["id"] == 1
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "openrpa_run_workflow", "arguments": {"name": "Main"}}}) + "\n")
        process.stdin.flush()
        time.sleep(0.15)
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 7, "reason": "acceptance test"}}) + "\n")
        process.stdin.flush()
        response = responses.get(timeout=5)
        assert response["id"] == 7
        run_result = response["result"]["structuredContent"]
        assert response["result"]["isError"] is False
        assert run_result["status"] == "cancelled"
        assert run_result["runId"]
    finally:
        process.stdin.close()
        process.wait(timeout=5)
        stderr = process.stderr.read()
        process.stdout.close()
        process.stderr.close()
        assert process.returncode == 0, stderr
        assert stderr == ""
