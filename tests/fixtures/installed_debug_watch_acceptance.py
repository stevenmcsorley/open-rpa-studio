"""Exercise safe live debugger watches through the frozen Windows bridge."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: installed_debug_watch_acceptance.py BRIDGE_EXE ACCEPTANCE_ROOT")
    executable = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    if root.exists():
        raise SystemExit(f"Refusing existing acceptance root: {root}")
    root.mkdir(parents=True)
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", bufsize=1,
                               env={**os.environ, "OPENRPA_DATA_DIR": str(root / "app-data")})
    responses: queue.Queue[dict] = queue.Queue()
    events: queue.Queue[dict] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            (responses if "id" in message else events).put(message)

    def drain_errors() -> None:
        assert process.stderr is not None
        for _ in process.stderr:
            pass

    threading.Thread(target=read_output, daemon=True).start()
    threading.Thread(target=drain_errors, daemon=True).start()
    request_id = 0

    def send(method: str, params: dict, expected_id: int | None = None) -> dict:
        nonlocal request_id
        request_id += 1
        current = request_id
        assert process.stdin is not None
        process.stdin.write(json.dumps({"id": current, "method": method, "params": params}) + "\n")
        process.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            row = responses.get(timeout=max(0.01, deadline - time.monotonic()))
            if row.get("id") == current:
                if "error" in row:
                    raise AssertionError(row["error"])
                return row["result"]
            raise AssertionError(f"Unexpected bridge response while waiting for {method}: {row}")
        raise AssertionError(f"Timed out waiting for bridge method {method}")

    def wait_event(name: str, timeout: float = 10) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = events.get(timeout=max(0.01, deadline - time.monotonic()))
            data = row.get("data", {})
            if data.get("event") == name:
                return data
        raise AssertionError(f"Timed out waiting for run event {name}")

    try:
        created = send("project.create", {"path": str(root / "project"), "name": "Debug watch acceptance"})
        project = created["project"]
        workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Main",
                    "variables": [{"name": "rows", "type": "array", "value": [{"total": 12}, {"total": 34}]}],
                    "arguments": [], "activities": [{"id": "inspect", "type": "log", "message": "inspect"}]}
        send("project.save", {"root": created["root"], "project": project, "workflows": {"Main": workflow}})
        request_id += 1
        run_id = request_id
        assert process.stdin is not None
        process.stdin.write(json.dumps({"id": run_id, "method": "workflow.run", "params": {
            "project": project, "root": created["root"], "workflow": "Main", "debug": True}}) + "\n")
        process.stdin.flush()
        paused = wait_event("debug.paused")
        assert paused["activityId"] == "inspect", paused
        assert send("debug.evaluate_watch", {"expression": "rows[1].total"}) == {"status": "ok", "type": "int", "value": 34}
        assert send("debug.evaluate_watch", {"expression": "len(rows)"}) == {"status": "ok", "type": "int", "value": 2}
        assert send("debug.evaluate_watch", {"expression": "__import__('os')"})["status"] == "error"
        send("debug.resume", {})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            row = responses.get(timeout=max(0.01, deadline - time.monotonic()))
            if row.get("id") == run_id:
                result = row["result"]
                assert result["status"] == "succeeded", result
                print("PASS: frozen bridge evaluated safe live-scope watches while paused, rejected Python, and resumed normally")
                return
            raise AssertionError(f"Unexpected bridge response during debug run: {row}")
        raise AssertionError("Timed out waiting for debug run completion")
    finally:
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
