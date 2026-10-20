"""Verify per-call reusable workflow bindings through the installed Windows bridge."""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: installed_reusable_binding_acceptance.py BRIDGE_EXE ACCEPTANCE_ROOT")
    executable = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    if root.exists():
        raise SystemExit(f"Refusing existing acceptance root: {root}")
    root.mkdir(parents=True)
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", bufsize=1,
                               env={**__import__("os").environ, "OPENRPA_DATA_DIR": str(root / "bridge-data")})
    messages: queue.Queue[dict] = queue.Queue()
    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try: messages.put(json.loads(line))
            except json.JSONDecodeError: messages.put({"unparsed": line})
    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    def send(request_id: int, method: str, params: dict) -> dict:
        assert process.stdin is not None
        process.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}) + "\n")
        process.stdin.flush()
        while True:
            try: row = messages.get(timeout=30)
            except queue.Empty: raise AssertionError(f"Timed out waiting for {method}; return code {process.poll()}")
            if row.get("id") == request_id:
                if "error" in row: raise AssertionError(row["error"])
                return row["result"]
    try:
        created = send(1, "project.create", {"path": str(root / "project"), "name": "Reusable bindings acceptance"})
        project = created["project"]
        project["workflows"]["Normalize"] = "workflows/normalize.workflow.json"
        main = {"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[
            {"name":"rawOne","type":"string","value":"Alpha"},{"name":"rawTwo","type":"string","value":"Beta"}],"arguments":[],"activities":[
            {"id":"normalize-one","type":"invoke_workflow","workflow":"Normalize","inputs":{"value":"{{rawOne}}"},"outputs":{"result":"firstResult"}},
            {"id":"normalize-two","type":"invoke_workflow","workflow":"Normalize","inputs":{"value":"{{rawTwo}}"},"outputs":{"result":"secondResult"}}]}
        child = {"format":"openrpa.workflow","formatVersion":1,"name":"Normalize","variables":[],"arguments":[
            {"name":"value","type":"string","direction":"in"},{"name":"result","type":"string","direction":"out"}],"activities":[
            {"id":"copy-value","type":"assign","target":"result","value":"{{value}}"}]}
        workflows = {"Main": main, "Normalize": child}
        send(2, "project.save", {"root": created["root"], "project": project, "workflows": workflows})
        validation = send(3, "workflow.validate", {"project": project, "workflow": main, "workflows": workflows})
        assert validation["valid"], validation["problems"]
        invalid = {**main, "activities": [{**main["activities"][0], "inputs": {}}]}
        rejected = send(4, "workflow.validate", {"project": project, "workflow": invalid, "workflows": {"Main": invalid, "Normalize": child}})
        assert not rejected["valid"] and any(problem["code"] == "argument-missing" for problem in rejected["problems"]), rejected
        result = send(5, "workflow.run", {"project": project, "root": created["root"], "workflow": "Main"})
        assert result["status"] == "succeeded", result
        assert result["variables"]["firstResult"] == "Alpha"
        assert result["variables"]["secondResult"] == "Beta"
        print("PASS: installed bridge preflighted reusable argument contracts and mapped outputs independently per call site")
    finally:
        if process.stdin is not None: process.stdin.close()
        try: process.wait(timeout=30)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
        reader.join(timeout=2)


if __name__ == "__main__":
    main()
