from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from openrpa.engine import RunOptions, run_project
from openrpa.model import validate_workflow


def make_project(root: Path, activity: dict) -> dict:
    workflow = {"format": "openrpa.workflow", "formatVersion": 1, "name": "Main", "variables": [], "arguments": [], "activities": [activity]}
    (root / "main.json").write_text(json.dumps(workflow), encoding="utf-8")
    return {"format": "openrpa.project", "formatVersion": 1, "name": "SQLite test", "main": "Main", "workflows": {"Main": "main.json"}}


def make_database(path: Path) -> None:
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT, active INTEGER)")
        database.executemany("INSERT INTO people(name,active) VALUES (?,?)", [("Ada", 1), ("Grace", 1), ("Edsger", 0)])


def activity(**values) -> dict:
    return {"id": "query", "type": "sqlite_query", "path": "people.sqlite", "query": "SELECT id, name FROM people WHERE active = ? ORDER BY id", "parameters": [1], **values}


def test_sqlite_query_returns_rows_using_bound_parameters_and_audit(tmp_path: Path):
    make_database(tmp_path / "people.sqlite")
    project = make_project(tmp_path, activity(result="matches"))
    audits = []
    result = run_project(project, tmp_path, options=RunOptions(audit=lambda action, details: audits.append((action, details))))

    assert result.status == "succeeded", result.error
    assert result.variables["matches"] == [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"}]
    assert result.activities["query"]["status"] == "succeeded"
    relative_path=str(Path("people.sqlite"))
    assert ("database.query.attempt", {"activityId": "query", "path": relative_path, "parameterCount": 1}) in audits
    assert ("database.query.completed", {"activityId": "query", "path": relative_path, "rowCount": 2, "parameterCount": 1}) in audits
    assert ("file.read", {"activityId": "query", "path": "people.sqlite"}) in audits


@pytest.mark.parametrize("sql", [
    "INSERT INTO people(name,active) VALUES ('Mallory',1)",
    "UPDATE people SET active=0",
    "DELETE FROM people",
    "PRAGMA user_version=99",
    "ATTACH DATABASE 'other.sqlite' AS other",
    "CREATE TABLE other (id INTEGER)",
    "SELECT load_extension('untrusted-extension.dll')",
])
def test_sqlite_query_rejects_mutation_pragma_and_attach(sql: str, tmp_path: Path):
    database = tmp_path / "people.sqlite"
    make_database(database)
    project = make_project(tmp_path, activity(query=sql, parameters=[]))

    result = run_project(project, tmp_path)

    assert result.status == "failed"
    assert result.error["code"] == "sqlite-readonly-policy"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM people").fetchone()[0] == 3
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0


def test_sqlite_query_rejects_path_escape(tmp_path: Path):
    outside = tmp_path.parent / "outside.sqlite"
    make_database(outside)
    result = run_project(make_project(tmp_path, activity(path="../outside.sqlite")), tmp_path)

    assert result.status == "failed"
    assert result.error["code"] == "file-permission-denied"


def test_sqlite_query_reads_explicit_extra_root_and_keeps_audit_path_relative(tmp_path: Path):
    project_root=tmp_path/"project";project_root.mkdir()
    approved_root=tmp_path/"approved";approved_root.mkdir()
    make_database(approved_root/"people.sqlite")
    project=make_project(project_root,activity(path=str(approved_root/"people.sqlite")))
    audits=[]

    result=run_project(project,project_root,options=RunOptions(extra_file_roots=(approved_root,),audit=lambda action,details:audits.append((action,details))))

    assert result.status=="succeeded",result.error
    assert any(action=="database.query.completed" and details["path"]==str(Path("approved-root-1")/"people.sqlite") for action,details in audits)


def test_sqlite_query_enforces_row_limit_and_single_statement(tmp_path: Path):
    make_database(tmp_path / "people.sqlite")
    too_many = run_project(make_project(tmp_path, activity(maxRows=1)), tmp_path)
    assert too_many.status == "failed"
    assert too_many.error["code"] == "sqlite-row-limit"

    multi = run_project(make_project(tmp_path, activity(query="SELECT id FROM people; DELETE FROM people", parameters=[])), tmp_path)
    assert multi.status == "failed"
    with sqlite3.connect(tmp_path / "people.sqlite") as connection:
        assert connection.execute("SELECT count(*) FROM people").fetchone()[0] == 3


@pytest.mark.parametrize("override,code", [
    ({"maxRows": 0}, "sqlite-row-limit"),
    ({"maxRows": True}, "sqlite-row-limit"),
    ({"timeoutSeconds": 0}, "sqlite-timeout"),
    ({"query": ""}, "sqlite-query"),
    ({"result": "bad-name"}, "sqlite-result"),
])
def test_sqlite_query_configuration_is_validated(override: dict, code: str):
    problems = validate_workflow({"format": "openrpa.workflow", "formatVersion": 1, "name": "M", "variables": [], "arguments": [], "activities": [activity(**override)]})
    assert any(problem["code"] == code for problem in problems)


def test_sqlite_query_handles_binary_results_as_tagged_base64(tmp_path: Path):
    database = tmp_path / "people.sqlite"
    make_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE people ADD COLUMN blob_data BLOB")
        connection.execute("UPDATE people SET blob_data=? WHERE id=1", (b"\x00\xff",))
    result = run_project(make_project(tmp_path, activity(query="SELECT blob_data FROM people WHERE id=1", parameters=[])), tmp_path)

    assert result.status == "succeeded", result.error
    assert result.variables["rows"] == [{"blob_data": {"$binaryBase64": "AP8="}}]


def test_sqlite_query_applies_vm_time_quota(tmp_path: Path):
    make_database(tmp_path / "people.sqlite")
    sql="WITH RECURSIVE counter(value) AS (VALUES(1) UNION ALL SELECT value+1 FROM counter WHERE value<100000000) SELECT sum(value) FROM counter"
    result=run_project(make_project(tmp_path,activity(query=sql,parameters=[],timeoutSeconds=1)),tmp_path)

    assert result.status=="failed"
    assert result.error["code"]=="sqlite-timeout"
    assert result.error["activityId"]=="query"


def test_sqlite_query_checks_cancellation_during_long_running_statement(tmp_path: Path):
    make_database(tmp_path / "people.sqlite")
    calls=0

    def cancel() -> bool:
        nonlocal calls
        calls+=1
        return calls>=3

    sql="WITH RECURSIVE counter(value) AS (VALUES(1) UNION ALL SELECT value+1 FROM counter WHERE value<100000000) SELECT sum(value) FROM counter"
    result=run_project(make_project(tmp_path,activity(query=sql,parameters=[],timeoutSeconds=30)),tmp_path,options=RunOptions(cancel=cancel))

    assert result.status=="cancelled"
    assert calls>=3


def test_sqlite_query_disambiguates_duplicate_column_names_without_dropping_values(tmp_path: Path):
    make_database(tmp_path / "people.sqlite")
    result=run_project(make_project(tmp_path,activity(query="SELECT id AS value, name AS value FROM people WHERE id=1",parameters=[])),tmp_path)

    assert result.status=="succeeded",result.error
    assert result.variables["rows"]==[{"value":1,"value_2":"Ada"}]
