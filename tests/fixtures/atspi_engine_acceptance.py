"""Run semantic desktop activities through the real Open RPA JSON-RPC bridge."""
from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path

from openrpa import linux_atspi


root = Path(__file__).resolve().parents[2]
project_root = root / ".build" / "atspi-engine-acceptance"
workflow_path = project_root / "workflows" / "main.workflow.json"
project_root.joinpath("workflows").mkdir(parents=True, exist_ok=True)
fixture_pid = int(os.environ["OPENRPA_ATSPI_FIXTURE_PID"])
windows = linux_atspi.list_windows()
fixture_window = next((window for window in windows
                       if window["title"] == "Open RPA AT-SPI Acceptance Fixture"
                       and window["processId"] == fixture_pid), None)
if fixture_window is None:
    raise SystemExit(f"AT-SPI fixture window missing for PID {fixture_pid}: {windows!r}")
controls = linux_atspi.list_controls(fixture_window["title"], fixture_pid)
control_names = {control["name"] for control in controls}
if not {"Organisation", "Save", "Status"}.issubset(control_names):
    raise SystemExit(f"Required AT-SPI fixture controls are missing: {controls!r}")
if "Password" in control_names:
    raise SystemExit("AT-SPI inspector exposed a password control")
project = {
    "format": "openrpa.project", "formatVersion": 1, "name": "Linux AT-SPI acceptance",
    "main": "Main", "workflows": {"Main": "workflows/main.workflow.json"},
}
workflow = {
    "format": "openrpa.workflow", "formatVersion": 1, "name": "AT-SPI interaction",
    "variables": [{"name": "savedStatus", "type": "string", "value": ""}], "arguments": [],
    "activities": [
        {"id": "wait-entry", "type": "desktop_ui_wait", "windowTitle": "Open RPA AT-SPI Acceptance Fixture",
         "processId": fixture_pid, "name": "Organisation", "automationId": "", "controlType": "Entry",
         "state": "enabled", "timeoutSeconds": 10},
        {"id": "fill-entry", "type": "desktop_ui_fill", "windowTitle": "Open RPA AT-SPI Acceptance Fixture",
         "processId": fixture_pid, "name": "Organisation", "automationId": "", "controlType": "Entry",
         "value": "Northshire Council", "timeoutSeconds": 10},
        {"id": "save", "type": "desktop_ui_click", "windowTitle": "Open RPA AT-SPI Acceptance Fixture",
         "processId": fixture_pid, "name": "Save", "automationId": "", "controlType": "Push Button",
         "timeoutSeconds": 10},
        {"id": "read-status", "type": "desktop_ui_text", "windowTitle": "Open RPA AT-SPI Acceptance Fixture",
         "processId": fixture_pid, "name": "Status", "automationId": "", "controlType": "Label",
         "result": "savedStatus", "timeoutSeconds": 10},
    ],
}
workflow_path.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
(project_root / "project.json").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")

environment = os.environ.copy()
environment["OPENRPA_DATA_DIR"] = str(root / ".build" / "atspi-engine-data")
process = subprocess.Popen([sys.executable, "-m", "openrpa.bridge"], cwd=root, env=environment,
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, encoding="utf-8", bufsize=1)
request = {"id": 701, "method": "workflow.run", "params": {
    "root": str(project_root), "project": project, "workflow": "Main", "allowDesktop": True,
}}
assert process.stdin and process.stdout
process.stdin.write(json.dumps(request) + "\n")
process.stdin.flush()
selector = selectors.DefaultSelector()
selector.register(process.stdout, selectors.EVENT_READ)
deadline = time.monotonic() + 60
events = []
result = None
try:
    while time.monotonic() < deadline:
        ready = selector.select(timeout=max(0.0, deadline - time.monotonic()))
        if not ready:
            break
        line = process.stdout.readline()
        if not line:
            break
        message = json.loads(line)
        if message.get("event") == "run.event":
            events.append(message)
        elif message.get("id") == 701:
            result = message.get("result")
            if result is None:
                raise RuntimeError(json.dumps(message))
            break
finally:
    selector.close()
    process.stdin.close()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

if not result:
    raise SystemExit("The workflow bridge did not return a workflow result")
if result["status"] != "succeeded" or result["variables"].get("savedStatus") != "Saved Northshire Council":
    raise SystemExit(json.dumps(result, indent=2))
if any(value["status"] != "succeeded" for value in result["activities"].values()):
    raise SystemExit(json.dumps(result["activities"], indent=2))

evidence = {"status": result["status"], "runId": result["runId"], "eventCount": len(events),
            "activities": result["activities"], "savedStatus": result["variables"]["savedStatus"]}
(root / ".build" / "atspi-engine-run-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
print(json.dumps(evidence, indent=2))
