import json

import pytest

from openrpa.active_project import active_project_file, publish_active_project, read_active_project


def test_active_project_pointer_is_atomic_and_resolved(tmp_path, monkeypatch):
    pointer=tmp_path/"state"/"active-project.json"
    monkeypatch.setenv("OPENRPA_ACTIVE_PROJECT_FILE",str(pointer))
    project=tmp_path/"project"
    project.mkdir()

    assert active_project_file()==pointer
    assert publish_active_project(project)==pointer
    payload=json.loads(pointer.read_text(encoding="utf-8"))
    assert payload["format"]=="openrpa.active-project"
    assert payload["formatVersion"]==1
    assert read_active_project()==project.resolve()
    assert not list(pointer.parent.glob(".active-project-*.tmp"))


def test_active_project_pointer_rejects_malformed_or_unsupported_data(tmp_path, monkeypatch):
    pointer=tmp_path/"active-project.json"
    monkeypatch.setenv("OPENRPA_ACTIVE_PROJECT_FILE",str(pointer))
    assert read_active_project() is None
    pointer.write_text("not json",encoding="utf-8")
    with pytest.raises(ValueError,match="malformed"):
        read_active_project()
    pointer.write_text(json.dumps({"format":"wrong","root":str(tmp_path)}),encoding="utf-8")
    with pytest.raises(ValueError,match="unsupported format"):
        read_active_project()
