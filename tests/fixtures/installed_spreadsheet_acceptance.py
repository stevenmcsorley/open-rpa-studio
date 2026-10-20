"""Verify XLSX execution through the frozen Windows bridge."""
from __future__ import annotations

import json
import io
import os
import queue
import subprocess
import sys
import threading
import zipfile
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: installed_spreadsheet_acceptance.py BRIDGE_EXE ACCEPTANCE_ROOT")
    executable = Path(sys.argv[1]).resolve()
    root = Path(sys.argv[2]).resolve()
    if root.exists():
        raise SystemExit(f"Refusing existing acceptance root: {root}")
    root.mkdir(parents=True)
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", bufsize=1,
                               env={**os.environ, "OPENRPA_DATA_DIR": str(root / "bridge-data")})
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
            try:
                row = messages.get(timeout=30)
            except queue.Empty as exc:
                raise AssertionError(f"Timed out waiting for {method}; return code {process.poll()}") from exc
            if row.get("id") == request_id:
                if "error" in row:
                    raise AssertionError(row["error"])
                return row["result"]

    try:
        created = send(1, "project.create", {"path": str(root / "project"), "name": "Spreadsheet acceptance"})
        project = created["project"]
        workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Main",
                    "variables": [{"name": "records", "type": "array", "value": [{"name": "=1+1", "amount": 6}]}],
                    "arguments": [],
                    "activities": [
                        {"id": "write-sheet", "type": "xlsx_write", "path": "result.xlsx", "rows": "records"},
                        {"id": "read-sheet", "type": "xlsx_read", "path": "result.xlsx", "result": "loaded"},
                    ]}
        workflows = {"Main": workflow}
        send(2, "project.save", {"root": created["root"], "project": project, "workflows": workflows})
        validation = send(3, "workflow.validate", {"project": project, "workflow": workflow, "workflows": workflows})
        assert validation["valid"], validation["problems"]
        result = send(4, "workflow.run", {"project": project, "root": created["root"], "workflow": "Main"})
        assert result["status"] == "succeeded", result
        assert result["variables"]["loaded"] == [{"name": "=1+1", "amount": 6}], result
        workbook_path = Path(created["root"]) / "result.xlsx"
        contents = {}
        with zipfile.ZipFile(workbook_path) as source:
            contents = {item.filename: source.read(item.filename) for item in source.infolist()}
        xml = contents["xl/worksheets/sheet1.xml"]
        xml = xml.replace(b"<worksheet ", b'<!DOCTYPE worksheet [<!ENTITY e "EXPANDED">]><worksheet ', 1)
        xml = xml.replace(b"<t>=1+1</t>", b"<t>&e;</t>", 1)
        contents["xl/worksheets/sheet1.xml"] = xml
        attacked = io.BytesIO()
        with zipfile.ZipFile(attacked, "w", compression=zipfile.ZIP_DEFLATED) as destination:
            for name, data in contents.items():
                destination.writestr(name, data)
        workbook_path.write_bytes(attacked.getvalue())
        rejected_workflow = {**workflow, "activities": [
            {"id": "read-entity", "type": "xlsx_read", "path": "result.xlsx", "result": "loaded"}]}
        workflows = {"Main": rejected_workflow}
        send(5, "project.save", {"root": created["root"], "project": project, "workflows": workflows})
        validation = send(6, "workflow.validate", {"project": project, "workflow": rejected_workflow, "workflows": workflows})
        assert validation["valid"], validation["problems"]
        rejected = send(7, "workflow.run", {"project": project, "root": created["root"], "workflow": "Main"})
        assert rejected["status"] == "failed" and rejected["error"]["code"] == "spreadsheet-xml-entity", rejected
        assert "DTD or entity declarations" in rejected["error"]["message"], rejected
        print("PASS: installed bridge read/wrote XLSX and rejected DTD/entity declarations before XML parsing")
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
