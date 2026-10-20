from __future__ import annotations

from openrpa import bridge


def test_native_bridge_exports_and_imports_verified_project_package(tmp_path, monkeypatch):
    replies=[]
    audit=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    monkeypatch.setattr(bridge.history,"audit",lambda action,details:audit.append((action,details)))
    source=tmp_path/"source"
    destination=tmp_path/"imported"
    archive=tmp_path/"automation.orpa"

    bridge.handle({"id":1,"method":"project.create","params":{"path":str(source),"name":"Reusable approval"}})
    bridge.handle({"id":2,"method":"project.package.export","params":{"root":str(source),"destination":str(archive)}})
    exported=replies[-1]["result"]
    assert exported["files"]==2 and len(exported["sha256"])==64
    bridge.handle({"id":3,"method":"project.package.import","params":{"package":str(archive),"destination":str(destination)}})
    imported=replies[-1]["result"]
    assert imported["name"]=="Reusable approval" and imported["files"]==2
    assert imported["sha256"]==exported["sha256"]
    assert (destination/"project.json").is_file()
    assert (destination/"workflows"/"main.workflow.json").is_file()
    assert [row[0] for row in audit]==["project.create","project.package.export","project.package.import"]
    assert "path" not in audit[-1][1]
    assert audit[-1][1]["sha256"]==exported["sha256"]


def test_native_bridge_package_import_rejects_nonempty_destination(tmp_path, monkeypatch):
    replies=[]
    monkeypatch.setattr(bridge,"send",replies.append)
    source=tmp_path/"source"
    archive=tmp_path/"automation.orpa"
    bridge.handle({"id":1,"method":"project.create","params":{"path":str(source),"name":"Safe import"}})
    bridge.handle({"id":2,"method":"project.package.export","params":{"root":str(source),"destination":str(archive)}})
    destination=tmp_path/"not-empty"
    destination.mkdir()
    (destination/"keep.txt").write_text("existing",encoding="utf-8")
    bridge.handle({"id":3,"method":"project.package.import","params":{"package":str(archive),"destination":str(destination)}})
    assert "error" in replies[-1] and "empty directory" in replies[-1]["error"]["message"]
