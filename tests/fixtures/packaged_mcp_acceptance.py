"""Acceptance-test the frozen console engine as an MCP stdio server."""
import json
import hashlib
import os
import threading
from queue import Queue
import subprocess
import sys
import tempfile
from pathlib import Path


executable = Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix="openrpa-packaged-mcp-") as directory:
    root = Path(directory)
    (root / "workflows").mkdir()
    (root / "project.json").write_text(json.dumps({
        "format": "openrpa.project", "formatVersion": 1, "name": "Frozen MCP acceptance",
        "main": "Main", "workflows": {"Main": "workflows/main.workflow.json"},
    }), encoding="utf-8")
    workflow_path = root / "workflows/main.workflow.json"
    workflow_path.write_text(json.dumps({
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Main",
        "variables": [], "arguments": [], "activities": [
            {"id": "acceptance-log", "type": "log", "level": "info", "message": "packaged MCP succeeded"}
        ],
    }), encoding="utf-8")
    def exchange(requests, extra_args=()):
        process = subprocess.Popen([str(executable), "mcp", str(root), "--mcp-mode", "full", *extra_args],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, bufsize=1,
                                   env=dict(os.environ, OPENRPA_DATA_DIR=str(root / "acceptance-data")))
        responses = Queue()
        def read_responses():
            for line in process.stdout:
                responses.put(json.loads(line))
        reader = threading.Thread(target=read_responses, daemon=True)
        reader.start()
        collected = []
        try:
            for request in requests:
                process.stdin.write(json.dumps(request) + "\n")
                process.stdin.flush()
                if "id" in request:
                    response = responses.get(timeout=60)
                    assert response["id"] == request["id"], response
                    collected.append(response)
        finally:
            process.stdin.close()
            process.wait(timeout=60)
            stderr = process.stderr.read()
            process.stdout.close()
            process.stderr.close()
            assert process.returncode == 0, f"frozen MCP exit={process.returncode}; stderr={stderr!r}"
            assert not stderr, stderr
            reader.join(timeout=5)
        return collected

    read_only = exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "openrpa_run_workflow", "arguments": {"name": "Main"}}},
    ])
    listed = read_only[1]["result"]["tools"]
    assert "openrpa_run_workflow" not in {tool["name"] for tool in listed}
    assert "openrpa_update_workflow" not in {tool["name"] for tool in listed}
    assert read_only[2]["result"]["isError"] is True
    assert "--allow-run" in read_only[2]["result"]["content"][0]["text"]
    enabled = exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "openrpa_run_workflow", "arguments": {"name": "Main"}}},
    ], ("--allow-run",))
    assert enabled[2]["result"]["isError"] is False
    assert enabled[2]["result"]["structuredContent"]["status"] == "succeeded"
    proposed = json.loads(workflow_path.read_text(encoding="utf-8"))
    proposed["activities"][0]["message"] = "frozen agent edit was validated"
    editable = exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "openrpa_update_workflow", "arguments": {"name": "Main", "expectedSha256": hashlib.sha256(workflow_path.read_bytes()).hexdigest(), "workflow": proposed}}},
    ], ("--allow-edit",))
    assert "openrpa_update_workflow" in {tool["name"] for tool in editable[1]["result"]["tools"]}
    assert editable[2]["result"]["structuredContent"]["updated"] is True
    credential_workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    credential_workflow["activities"] = [{"id": "read-secret", "type": "credential_get", "service": "acceptance", "username": "unused", "result": "secret"}]
    workflow_path.write_text(json.dumps(credential_workflow), encoding="utf-8")
    credential_guard = exchange([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "openrpa_plan_workflow", "arguments": {"name": "Main"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "openrpa_run_workflow", "arguments": {"name": "Main"}}},
    ], ("--allow-run",))
    assert credential_guard[1]["result"]["structuredContent"]["requires"]["credentials"] is True
    assert credential_guard[2]["result"]["isError"] is True
    assert "--allow-credentials" in credential_guard[2]["result"]["content"][0]["text"]

print("Frozen MCP acceptance passed: initialize, discovery, default denials, validated edit, credential guard and opted-in engine run.")
