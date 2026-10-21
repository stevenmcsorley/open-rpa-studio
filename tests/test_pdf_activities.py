from __future__ import annotations

import json
import io
from pathlib import Path

from openrpa.engine import RunOptions, run_project
from openrpa.model import validate_workflow


def make_pdf(path: Path, pages: list[str], encrypted: bool = False) -> None:
    """Write a tiny standards-shaped PDF fixture without adding a test-only writer dependency."""
    objects: list[bytes] = []
    kids: list[str] = []
    for index, text in enumerate(pages):
        page_id = 3 + index * 3
        font_id = page_id + 1
        stream_id = page_id + 2
        kids.append(f"{page_id} 0 R")
        safe_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")
        content = b"BT /F1 12 Tf 72 720 Td (" + safe_text + b") Tj ET\n"
        objects.extend([
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>".encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        ])
    root = b"<< /Type /Catalog /Pages 2 0 R >>"
    pages_obj = b"<< /Type /Pages /Kids [" + " ".join(kids).encode() + b"] /Count " + str(len(pages)).encode() + b" >>"
    document_objects = [root, pages_obj, *objects]
    content = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(document_objects, start=1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    if encrypted:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(io.BytesIO(bytes(content)))
        writer = PdfWriter()
        writer.append(reader)
        writer.encrypt("test-password")
        with path.open("wb") as stream:
            writer.write(stream)
    else:
        path.write_bytes(content)


def project_with(activity: dict) -> dict:
    return {"format": "openrpa.project", "formatVersion": 1, "name": "PDF", "main": "Main", "workflows": {"Main": "main.json"}}


def workflow_with(activity: dict) -> dict:
    return {"format": "openrpa.workflow", "formatVersion": 1, "name": "PDF", "variables": [], "arguments": [], "activities": [activity]}


def test_pdf_read_extracts_text_with_page_boundaries_and_audit(tmp_path: Path):
    make_pdf(tmp_path / "input.pdf", ["Invoice 1001", "Total 42"])
    workflow = workflow_with({"id": "read-pdf", "type": "pdf_read_text", "path": "input.pdf"})
    (tmp_path / "main.json").write_text(json.dumps(workflow), encoding="utf-8")
    audits = []
    result = run_project(project_with(workflow["activities"][0]), tmp_path,
                         options=RunOptions(audit=lambda action, details: audits.append((action, details))))
    assert result.status == "succeeded", result.error
    assert result.variables["pageCount"] == 2
    assert "Invoice 1001" in result.variables["text"]
    assert "\f" in result.variables["text"]
    assert "Total 42" in result.variables["text"]
    assert ("file.read", {"activityId": "read-pdf", "path": "input.pdf"}) in audits


def test_pdf_read_enforces_page_and_encryption_limits(tmp_path: Path):
    make_pdf(tmp_path / "input.pdf", ["one", "two"])
    workflow = workflow_with({"id": "read-pdf", "type": "pdf_read_text", "path": "input.pdf", "maxPages": 1})
    (tmp_path / "main.json").write_text(json.dumps(workflow), encoding="utf-8")
    result = run_project(project_with(workflow["activities"][0]), tmp_path)
    assert result.status == "failed" and result.error["code"] == "pdf-page-limit"

    make_pdf(tmp_path / "input.pdf", ["secret"], encrypted=True)
    result = run_project(project_with(workflow["activities"][0]), tmp_path)
    assert result.status == "failed" and result.error["code"] == "pdf-encrypted"


def test_pdf_schema_rejects_bad_limits_and_overlapping_outputs():
    activity = {"id": "pdf", "type": "pdf_read_text", "path": "input.pdf", "result": "same", "pageCountResult": "same", "maxPages": 0}
    problems = validate_workflow(workflow_with(activity))
    assert {problem["code"] for problem in problems} >= {"pdf-page-count-result", "pdf-page-limit"}
