from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from openrpa.engine import RunOptions, run_project
from openrpa.model import validate_workflow


def _project(root: Path, activity: dict) -> dict:
    workflow = {
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Launch test",
        "variables": [], "arguments": [], "activities": [activity],
    }
    (root / "main.json").write_text(json.dumps(workflow), encoding="utf-8")
    return {"format": "openrpa.project", "formatVersion": 1, "name": "Launch test",
            "main": "Main", "workflows": {"Main": "main.json"}}


def test_desktop_launch_validates_executable_arguments_and_result(tmp_path: Path):
    valid = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Launch",
             "variables": [], "arguments": [], "activities": [
                 {"id": "launch", "type": "desktop_launch_app", "executable": str(tmp_path / "app.exe"),
                  "arguments": ["--document", "file name.txt"], "result": "pid"}]}
    assert validate_workflow(valid) == []
    activity = valid["activities"][0]
    activity["executable"] = "notepad.exe"
    assert "desktop-app-executable" in {problem["code"] for problem in validate_workflow(valid)}
    activity["executable"] = str(tmp_path / "app.exe")
    activity["arguments"] = ["\x00"]
    assert "desktop-app-arguments" in {problem["code"] for problem in validate_workflow(valid)}
    activity["arguments"] = []
    activity["result"] = "not a variable"
    assert "desktop-app-result" in {problem["code"] for problem in validate_workflow(valid)}


def test_desktop_launch_requires_explicit_per_run_permission(tmp_path: Path, monkeypatch):
    import openrpa.engine as engine_module

    activity = {"id": "launch", "type": "desktop_launch_app", "executable": sys.executable,
                "arguments": [], "result": "pid"}
    project = _project(tmp_path, activity)
    monkeypatch.setattr(engine_module.subprocess, "Popen", lambda *_args, **_kwargs: pytest.fail("must not launch without desktop permission"))
    result = run_project(project, tmp_path, options=RunOptions(allow_desktop=False))
    assert result.status == "failed"
    assert result.error["code"] == "desktop-permission-denied"


def test_desktop_launch_runs_argument_vector_without_a_shell_and_returns_pid(tmp_path: Path):
    marker = tmp_path / "launched.txt"
    script = "from pathlib import Path; Path(__import__('sys').argv[1]).write_text('started', encoding='utf-8')"
    audit: list[tuple[str, dict]] = []
    activity = {"id": "launch", "type": "desktop_launch_app", "executable": sys.executable,
                "arguments": ["-c", script, str(marker)], "result": "childPid"}
    project = _project(tmp_path, activity)
    result = run_project(project, tmp_path, options=RunOptions(allow_desktop=True, audit=lambda action, details: audit.append((action, details))))
    assert result.status == "succeeded", result.error
    assert result.variables["childPid"] > 0
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.read_text(encoding="utf-8") == "started"
    assert audit == [("desktop.application_launched", {
        "activityId": "launch", "executable": Path(sys.executable).name,
        "argumentCount": 3, "processId": result.variables["childPid"],
    })]
