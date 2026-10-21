"""Exercise bounded SQLite queries in the frozen desktop bridge."""
from __future__ import annotations

import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: installed_sqlite_acceptance.py BRIDGE_EXE DATA_DIRECTORY")
    executable, data_dir = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if data_dir.exists() and any(data_dir.iterdir()):
        raise SystemExit(f"Refusing non-empty acceptance directory: {data_dir}")
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", bufsize=1,
                               env={**os.environ, "OPENRPA_DATA_DIR": str(data_dir / "bridge-data")})
    messages: queue.Queue[dict] = queue.Queue()

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except json.JSONDecodeError:
                messages.put({"unparsed": line})

    threading.Thread(target=read_output, daemon=True).start()

    def send(request_id: int, method: str, params: dict) -> dict:
        assert process.stdin is not None
        process.stdin.write(json.dumps({"id": request_id, "method": method, "params": params}) + "\n")
        process.stdin.flush()
        while True:
            row = messages.get(timeout=45)
            if row.get("id") != request_id:
                continue
            if "error" in row:
                raise AssertionError(row["error"])
            return row["result"]

    try:
        created = send(1, "project.create", {"path": str(data_dir / "project"), "name": "SQLite acceptance"})
        project, root = created["project"], Path(created["root"])
        database = root / "records.sqlite"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE packages (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            connection.executemany("INSERT INTO packages(name) VALUES (?)", [("alpha",), ("beta",)])
        workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Main", "variables": [], "arguments": [],
                    "activities": [{"id": "query", "type": "sqlite_query", "path": "records.sqlite",
                                    "query": "SELECT id, name FROM packages WHERE id = ?", "parameters": [2],
                                    "result": "matches", "maxRows": 10, "timeoutSeconds": 5}]}
        workflows = {"Main": workflow}
        send(2, "project.save", {"root": str(root), "project": project, "workflows": workflows})
        validation = send(3, "workflow.validate", {"project": project, "workflow": workflow, "workflows": workflows})
        assert validation["valid"], validation["problems"]
        result = send(4, "workflow.run", {"project": project, "root": str(root), "workflow": "Main"})
        assert result["status"] == "succeeded", result
        assert result["variables"]["matches"] == [{"id": 2, "name": "beta"}], result
        audits = send(5, "audit.history", {"limit": 100})["events"]
        attempts = [row for row in audits if row["action"] == "database.query.attempt"]
        completions = [row for row in audits if row["action"] == "database.query.completed"]
        assert attempts and completions, audits
        assert attempts[0]["details"]["path"] == "records.sqlite"
        assert completions[0]["details"]["rowCount"] == 1
        audit_json=json.dumps(attempts[0]["details"])
        assert "SELECT id, name FROM packages" not in audit_json and "beta" not in audit_json

        workflow["activities"][0].update(query="DELETE FROM packages", parameters=[])
        send(6, "project.save", {"root": str(root), "project": project, "workflows": workflows})
        blocked = send(7, "workflow.run", {"project": project, "root": str(root), "workflow": "Main"})
        assert blocked["status"] == "failed" and blocked["error"]["code"] == "sqlite-readonly-policy", blocked
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT count(*) FROM packages").fetchone()[0] == 2
        print("PASS: frozen bridge ran a parameterized local SQLite read, persisted value-free audit evidence and blocked DELETE without changing the database")
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
