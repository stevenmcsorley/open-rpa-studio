"""Durable, local job queue for unattended Open RPA executions.

Jobs are claimed exactly once. A process restart marks claimed jobs interrupted;
it never replays them because external side effects may already have happened.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_JOBS = 500
MAX_INPUT_BYTES = 100_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class JobQueue:
    """SQLite WAL queue with durable state transitions and bounded payloads."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables:
                db.executescript("""
                    CREATE TABLE schema_version(version INTEGER NOT NULL);
                    CREATE TABLE jobs(
                        job_id TEXT PRIMARY KEY,
                        idempotency_key TEXT UNIQUE,
                        project_path TEXT NOT NULL,
                        project_name TEXT NOT NULL,
                        workflow_name TEXT NOT NULL,
                        snapshot_sha256 TEXT NOT NULL,
                        inputs_json TEXT NOT NULL,
                        available_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        submitted_at TEXT NOT NULL,
                        started_at TEXT,
                        ended_at TEXT,
                        run_id TEXT,
                        error_json TEXT,
                        cancel_requested INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE INDEX idx_jobs_due ON jobs(status, available_at, submitted_at);
                    CREATE INDEX idx_jobs_project ON jobs(project_path, submitted_at DESC);
                """)
                db.execute("INSERT INTO schema_version(version) VALUES(?)", (SCHEMA_VERSION,))
            elif "schema_version" not in tables:
                raise RuntimeError("Job queue database has no schema version; left unchanged for manual recovery")
            else:
                version_row = db.execute("SELECT version FROM schema_version").fetchone()
                version = int(version_row[0]) if version_row else 0
                if version != SCHEMA_VERSION:
                    raise RuntimeError(f"Unsupported job queue schema version: {version}")
            db.execute("UPDATE jobs SET status='interrupted', ended_at=?, error_json=? WHERE status='running'",
                       (_now(), _json({"code": "worker-interrupted", "message": "The worker stopped during execution. External side effects are unknown; the job was not replayed."})))

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    def enqueue(self, *, project_path: str, project_name: str, workflow: str,
                snapshot_sha256: str, inputs: dict[str, Any], available_at: str,
                idempotency_key: str | None = None) -> dict[str, Any]:
        encoded = _json(inputs)
        if len(encoded.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("Job inputs exceed 100 KB")
        if idempotency_key is not None and (not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 200):
            raise ValueError("idempotencyKey must contain 1–200 non-whitespace characters")
        if idempotency_key is not None:
            with self._db() as db:
                prior = db.execute("SELECT * FROM jobs WHERE project_path=? AND idempotency_key=?", (project_path, idempotency_key)).fetchone()
                if prior:
                    return {**self._record(prior), "alreadyExisted": True}
        with self._db() as db:
            count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','scheduled','running')").fetchone()[0]
            if count >= MAX_JOBS:
                raise ValueError(f"The active job queue is full ({MAX_JOBS} jobs)")
            job_id = str(uuid.uuid4())
            submitted = _now()
            status = "queued" if available_at <= submitted else "scheduled"
            db.execute("INSERT INTO jobs(job_id,idempotency_key,project_path,project_name,workflow_name,snapshot_sha256,inputs_json,available_at,status,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (job_id, idempotency_key, project_path, project_name, workflow, snapshot_sha256, encoded, available_at, status, submitted))
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            return self._record(row)

    @staticmethod
    def _record(row: sqlite3.Row) -> dict[str, Any]:
        return {"jobId": row["job_id"], "projectPath": row["project_path"], "idempotencyKey": row["idempotency_key"],
                "projectName": row["project_name"], "workflow": row["workflow_name"],
                "snapshotSha256": row["snapshot_sha256"], "inputs": json.loads(row["inputs_json"]),
                "availableAt": row["available_at"], "status": row["status"],
                "submittedAt": row["submitted_at"], "startedAt": row["started_at"],
                "endedAt": row["ended_at"], "runId": row["run_id"],
                "error": json.loads(row["error_json"]) if row["error_json"] else None,
                "cancelRequested": bool(row["cancel_requested"])}

    def claim_due(self, project_path: str) -> dict[str, Any] | None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            now = _now()
            db.execute("UPDATE jobs SET status='queued' WHERE status='scheduled' AND available_at<=?", (now,))
            row = db.execute("SELECT * FROM jobs WHERE project_path=? AND status='queued' AND available_at<=? ORDER BY available_at,submitted_at LIMIT 1", (project_path, now)).fetchone()
            if row is None:
                db.commit()
                return None
            db.execute("UPDATE jobs SET status='running',started_at=?,cancel_requested=0 WHERE job_id=? AND status='queued'", (now, row["job_id"]))
            claimed = db.execute("SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)).fetchone()
            db.commit()
            return self._record(claimed)

    def finish(self, job_id: str, status: str, *, run_id: str | None = None, error: dict[str, Any] | None = None) -> None:
        if status not in {"succeeded", "failed", "cancelled", "workflow_changed", "interrupted"}:
            raise ValueError("Invalid terminal job status")
        with self._db() as db:
            db.execute("UPDATE jobs SET status=?,ended_at=?,run_id=?,error_json=? WHERE job_id=? AND status='running'",
                       (status, _now(), run_id, _json(error) if error is not None else None, job_id))

    def cancel(self, project_path: str, job_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE project_path=? AND job_id=?", (project_path, job_id)).fetchone()
            if row is None:
                db.commit()
                return None
            if row["status"] in {"queued", "scheduled"}:
                db.execute("UPDATE jobs SET status='cancelled',ended_at=? WHERE job_id=?", (_now(), job_id))
            elif row["status"] == "running":
                db.execute("UPDATE jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
            result = self._record(db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone())
            db.commit()
            return result

    def get(self, project_path: str, job_id: str) -> dict[str, Any] | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE project_path=? AND job_id=?", (project_path, job_id)).fetchone()
            return self._record(row) if row else None

    def list(self, project_path: str, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self._db() as db:
            rows = db.execute("SELECT * FROM jobs WHERE project_path=? ORDER BY submitted_at DESC LIMIT ?", (project_path, limit)).fetchall()
            return [self._record(row) for row in rows]


def read_jobs(path: Path, project_path: str, limit: int = 100) -> list[dict[str, Any]]:
    """Read queue state without startup recovery or any write access."""
    if not path.is_file():
        return []
    uri = path.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=0.5)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT * FROM jobs WHERE project_path=? ORDER BY submitted_at DESC LIMIT ?",
                          (project_path, max(1, min(int(limit), 200)))).fetchall()
        result = [JobQueue._record(row) for row in rows]
        for item in result:
            item.pop("inputs", None)
            item.pop("idempotencyKey", None)
            item.pop("projectPath", None)
        return result
    finally:
        db.close()


def request_job_cancel(path: Path, project_path: str, job_id: str) -> dict[str, Any] | None:
    """Request cancellation without running JobQueue startup recovery."""
    if not path.is_file():
        return None
    db = sqlite3.connect(path, timeout=2, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM jobs WHERE project_path=? AND job_id=?", (project_path, job_id)).fetchone()
        if row is None:
            db.commit()
            return None
        if row["status"] in {"queued", "scheduled"}:
            db.execute("UPDATE jobs SET status='cancelled',ended_at=? WHERE job_id=?", (_now(), job_id))
        elif row["status"] == "running":
            db.execute("UPDATE jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
        row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        record = JobQueue._record(row)
        db.commit()
        record.pop("inputs", None)
        record.pop("idempotencyKey", None)
        return record
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
