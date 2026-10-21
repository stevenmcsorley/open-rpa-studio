"""Exercise PDF text extraction in the frozen desktop bridge."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from pypdf import PdfWriter


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: installed_pdf_acceptance.py BRIDGE_EXE DATA_DIRECTORY")
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
        created = send(1, "project.create", {"path": str(data_dir / "project"), "name": "PDF acceptance"})
        project, root = created["project"], Path(created["root"])
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        with (root / "pages.pdf").open("wb") as stream:
            writer.write(stream)
        workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Main", "variables": [],
                    "arguments": [], "activities": [{"id": "read", "type": "pdf_read_text", "path": "pages.pdf"}]}
        workflows = {"Main": workflow}
        send(2, "project.save", {"root": str(root), "project": project, "workflows": workflows})
        validation = send(3, "workflow.validate", {"project": project, "workflow": workflow, "workflows": workflows})
        assert validation["valid"], validation["problems"]
        result = send(4, "workflow.run", {"project": project, "root": str(root), "workflow": "Main"})
        assert result["status"] == "succeeded", result
        assert result["variables"]["pageCount"] == 2 and result["variables"]["text"] == "\n\f\n", result
        saved_run = send(5, "run.get", {"runId": result["runId"]})["run"]
        assert any(event.get("event") == "file.read" or event.get("type") == "pdf_read_text" for event in saved_run["events"]), saved_run
        print("PASS: frozen desktop bridge parsed a two-page local PDF, preserved page boundary, returned page count and saved run evidence")
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
