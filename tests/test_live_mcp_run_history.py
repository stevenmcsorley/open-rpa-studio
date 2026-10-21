from __future__ import annotations

from pathlib import Path

from openrpa import bridge
from openrpa.active_project import publish_active_project
from openrpa.app_paths import app_data_dir
from openrpa.history import RunHistory, read_run, read_runs
from openrpa.mcp_server import _history_path


def test_read_only_history_observes_live_mcp_run_without_recovery_write(tmp_path: Path):
    path = tmp_path / "mcp.sqlite3"
    history = RunHistory(path)
    run_id = history.start(str(tmp_path / "project"), "Example", "Main", "a" * 64)
    history.event(run_id, {"event": "activity-started", "activityId": "step-1", "type": "log"})

    assert read_runs(path)[0]["status"] == "running"
    detail = read_run(path, run_id)
    assert detail is not None
    assert detail["status"] == "running"
    assert detail["events"][0]["activityId"] == "step-1"

    # The desktop must not open a second RunHistory instance, whose startup
    # recovery would incorrectly mark this live MCP process as interrupted.
    import sqlite3
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()[0] == "running"


def test_desktop_run_history_merges_active_projects_mcp_runs(tmp_path: Path, monkeypatch):
    data = tmp_path / "app-data"
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setenv("OPENRPA_DATA_DIR", str(data))
    monkeypatch.setenv("OPENRPA_ACTIVE_PROJECT_FILE", str(data / "active-project.json"))
    monkeypatch.setattr(bridge, "history", RunHistory(data / "studio.sqlite3"))
    publish_active_project(project_root)

    mcp_path = bridge._mcp_history_path(project_root)
    assert mcp_path is not None
    mcp_history = RunHistory(mcp_path)
    run_id = mcp_history.start(str(project_root), "MCP project", "Hello UnoVerse", "b" * 64)
    mcp_history.event(run_id, {"event": "log", "message": "hello unoverse"})
    replies: list[dict] = []
    monkeypatch.setattr(bridge, "send", replies.append)

    bridge.handle({"id": 1, "method": "run.history", "params": {"limit": 20}})
    runs = replies.pop()["result"]["runs"]
    assert runs[0]["runId"] == run_id
    assert runs[0]["source"] == "MCP"
    assert runs[0]["status"] == "running"

    bridge.handle({"id": 2, "method": "run.get", "params": {"runId": run_id}})
    detail = replies.pop()["result"]["run"]
    assert detail["source"] == "MCP"
    assert detail["events"][0]["message"] == "hello unoverse"

    import sqlite3
    with sqlite3.connect(mcp_path) as db:
        assert db.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()[0] == "running"


def test_mcp_and_studio_use_the_same_native_app_data_directory(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENRPA_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    root = tmp_path / "project"

    assert _history_path(root).parent == app_data_dir()
    assert bridge._history_path().parent == app_data_dir()
