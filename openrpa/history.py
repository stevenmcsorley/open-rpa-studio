"""Crash-resilient, local execution history. Interrupted runs are never replayed."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_EVENT_CHARS = 16_384
SCHEMA_VERSION = 1
MAX_RUN_EVENT_BYTES = 512_000
MAX_RUNS = 300
MAX_AUDIT_EVENTS = 10_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _bounded_json(value: Any, limit: int = MAX_EVENT_CHARS) -> str:
    raw = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(raw) > limit:
        raw = json.dumps({"truncated": True, "preview": raw[: limit - 100]}, ensure_ascii=False)
    return raw


class RunHistory:
    """SQLite WAL ledger. Each mutation commits synchronously before returning."""

    def __init__(self, path: Path):
        self.path = path
        self._event_lock=threading.Lock()
        self._event_bytes:dict[str,int]={}
        self._truncated_runs:set[str]=set()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables:
                self._create_schema(db)
                db.execute("INSERT INTO schema_version(version) VALUES(?)",(SCHEMA_VERSION,))
            elif "schema_version" not in tables:
                raise RuntimeError("Run history database has no schema version; it was left unchanged for manual recovery")
            else:
                version_row=db.execute("SELECT version FROM schema_version").fetchone()
                version=int(version_row[0]) if version_row else 0
                if version>SCHEMA_VERSION:
                    raise RuntimeError(f"Run history schema {version} is newer than this application supports")
                while version<SCHEMA_VERSION:
                    self._backup(version)
                    self._migrate(version,db)
                    version+=1
                    db.execute("UPDATE schema_version SET version=?",(version,))
        self.recover_interrupted()

    def _create_schema(self, db: sqlite3.Connection) -> None:
        db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY, project_path TEXT NOT NULL, project_name TEXT NOT NULL,
                    workflow_name TEXT NOT NULL, workflow_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
                    result_json TEXT, error_json TEXT, recovery_note TEXT
                );
                CREATE TABLE IF NOT EXISTS run_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(run_id),
                    created_at TEXT NOT NULL, event_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, sequence);
                CREATE TABLE IF NOT EXISTS audit_events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,
                    action TEXT NOT NULL, details_json TEXT NOT NULL
                );
            """)

    def _backup(self, version: int) -> None:
        backup=self.path.with_name(f"{self.path.name}.v{version}.bak")
        if backup.exists():
            raise RuntimeError(f"Migration backup already exists; refusing to overwrite it: {backup}")
        source=sqlite3.connect(self.path)
        target=sqlite3.connect(backup)
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close();source.close()

    def _migrate(self, version: int, db: sqlite3.Connection) -> None:
        if version!=0:
            raise RuntimeError(f"No run history migration is defined from schema {version}")
        self._create_schema(db)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA foreign_keys=ON")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def recover_interrupted(self) -> int:
        with self._db() as db:
            cur = db.execute("UPDATE runs SET status='interrupted', ended_at=?, recovery_note=? WHERE status='running'",
                             (_now(), "Application stopped before completion. External side effects are unknown; inspect them before manually restarting."))
            return cur.rowcount

    def start(self, project_path: str, project_name: str, workflow: str, digest: str) -> str:
        run_id = str(uuid.uuid4())
        with self._db() as db:
            excess=db.execute("SELECT run_id FROM runs WHERE status!='running' ORDER BY started_at DESC LIMIT -1 OFFSET ?",(MAX_RUNS-1,)).fetchall()
            for (expired,) in excess:
                db.execute("DELETE FROM run_events WHERE run_id=?",(expired,))
                db.execute("DELETE FROM runs WHERE run_id=?",(expired,))
            db.execute("INSERT INTO runs(run_id,project_path,project_name,workflow_name,workflow_sha256,status,started_at) VALUES(?,?,?,?,?,'running',?)",
                       (run_id, project_path, project_name, workflow, digest, _now()))
        self._event_bytes[run_id]=0
        return run_id

    def event(self, run_id: str, value: dict[str, Any]) -> None:
        encoded=_bounded_json(value, min(MAX_EVENT_CHARS,8192))
        with self._event_lock:
            used=self._event_bytes.get(run_id,0)
            if used+len(encoded)>MAX_RUN_EVENT_BYTES:
                if run_id not in self._truncated_runs:
                    marker=_bounded_json({"event":"history-truncated","reason":"per-run event storage quota reached"})
                    with self._db() as db: db.execute("INSERT INTO run_events(run_id,created_at,event_json) VALUES(?,?,?)",(run_id,_now(),marker))
                    self._truncated_runs.add(run_id)
                return
            with self._db() as db:
                db.execute("INSERT INTO run_events(run_id,created_at,event_json) VALUES(?,?,?)", (run_id, _now(), encoded))
            self._event_bytes[run_id]=used+len(encoded)

    def finish(self, run_id: str, status: str, result: dict[str, Any] | None, error: dict[str, Any] | None = None) -> None:
        with self._db() as db:
            db.execute("UPDATE runs SET status=?,ended_at=?,result_json=?,error_json=? WHERE run_id=?",
                       (status, _now(), _bounded_json(result, 1_000_000) if result is not None else None,
                        _bounded_json(error) if error is not None else None, run_id))

    def audit(self, action: str, details: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute("INSERT INTO audit_events(created_at,action,details_json) VALUES(?,?,?)", (_now(), action, _bounded_json(details)))
            db.execute("DELETE FROM audit_events WHERE sequence IN (SELECT sequence FROM audit_events ORDER BY sequence DESC LIMIT -1 OFFSET ?)",(MAX_AUDIT_EVENTS,))

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._db() as db:
            rows = db.execute("SELECT run_id,project_path,project_name,workflow_name,workflow_sha256,status,started_at,ended_at,error_json,recovery_note FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        keys = ("runId", "projectPath", "projectName", "workflow", "workflowSha256", "status", "startedAt", "endedAt", "error", "recoveryNote")
        return [dict(zip(keys, row[:9] + (row[9],))) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT run_id,project_path,project_name,workflow_name,workflow_sha256,status,started_at,ended_at,result_json,error_json,recovery_note FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if not row:
                return None
            event_rows = db.execute("SELECT created_at,event_json FROM run_events WHERE run_id=? ORDER BY sequence", (run_id,)).fetchall()
            events = [{**json.loads(raw), "recordedAt": created_at} for created_at, raw in event_rows]
        keys = ("runId", "projectPath", "projectName", "workflow", "workflowSha256", "status", "startedAt", "endedAt")
        record = dict(zip(keys, row[:8]))
        record.update(result=json.loads(row[8]) if row[8] else None, error=json.loads(row[9]) if row[9] else None,
                      recoveryNote=row[10], events=events)
        return record

    def list_audit(self, limit: int = 200) -> list[dict[str, Any]]:
        limit=max(1,min(int(limit),1000))
        with self._db() as db:
            rows=db.execute("SELECT created_at,action,details_json FROM audit_events ORDER BY sequence DESC LIMIT ?",(limit,)).fetchall()
        return [{"createdAt":row[0],"action":row[1],"details":json.loads(row[2])} for row in rows]

