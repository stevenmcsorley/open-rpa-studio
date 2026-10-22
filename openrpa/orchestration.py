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

from .scheduling import next_cron_time, parse_cron, validate_timezone

SCHEMA_VERSION = 2
MAX_JOBS = 500
MAX_INPUT_BYTES = 100_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class JobQueue:
    """SQLite WAL queue with durable state transitions and bounded payloads."""

    def __init__(self, path: Path, *, recover: bool = True):
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
                    CREATE TABLE schedules(
                        schedule_id TEXT PRIMARY KEY,
                        project_path TEXT NOT NULL,
                        schedule_name TEXT NOT NULL,
                        workflow_name TEXT NOT NULL,
                        snapshot_sha256 TEXT NOT NULL,
                        inputs_json TEXT NOT NULL,
                        cron TEXT NOT NULL,
                        timezone TEXT NOT NULL,
                        next_run TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        last_triggered_at TEXT,
                        last_job_id TEXT,
                        last_error_json TEXT
                    );
                    CREATE INDEX idx_schedules_due ON schedules(project_path, enabled, next_run);
                """)
                db.execute("INSERT INTO schema_version(version) VALUES(?)", (SCHEMA_VERSION,))
            elif "schema_version" not in tables:
                raise RuntimeError("Job queue database has no schema version; left unchanged for manual recovery")
            else:
                version_row = db.execute("SELECT version FROM schema_version").fetchone()
                version = int(version_row[0]) if version_row else 0
                if version == 1:
                    db.executescript("""
                        CREATE TABLE schedules(
                            schedule_id TEXT PRIMARY KEY,
                            project_path TEXT NOT NULL,
                            schedule_name TEXT NOT NULL,
                            workflow_name TEXT NOT NULL,
                            snapshot_sha256 TEXT NOT NULL,
                            inputs_json TEXT NOT NULL,
                            cron TEXT NOT NULL,
                            timezone TEXT NOT NULL,
                            next_run TEXT NOT NULL,
                            enabled INTEGER NOT NULL DEFAULT 1,
                            created_at TEXT NOT NULL,
                            last_triggered_at TEXT,
                            last_job_id TEXT,
                            last_error_json TEXT
                        );
                        CREATE INDEX idx_schedules_due ON schedules(project_path, enabled, next_run);
                    """)
                    db.execute("UPDATE schema_version SET version=?", (SCHEMA_VERSION,))
                    version = SCHEMA_VERSION
                if version != SCHEMA_VERSION:
                    raise RuntimeError(f"Unsupported job queue schema version: {version}")
            if recover:
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

    @staticmethod
    def _schedule_record(row: sqlite3.Row) -> dict[str, Any]:
        return {"scheduleId": row["schedule_id"], "name": row["schedule_name"], "workflow": row["workflow_name"],
                "cron": row["cron"], "timezone": row["timezone"], "nextRun": row["next_run"],
                "enabled": bool(row["enabled"]), "createdAt": row["created_at"],
                "lastTriggeredAt": row["last_triggered_at"], "lastJobId": row["last_job_id"],
                "lastError": json.loads(row["last_error_json"]) if row["last_error_json"] else None}

    def create_schedule(self, *, project_path: str, name: str, workflow: str, snapshot_sha256: str,
                        inputs: dict[str, Any], cron: str, timezone_name: str) -> dict[str, Any]:
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("Schedule name must contain 1–100 characters")
        if not isinstance(inputs, dict) or len(_json(inputs).encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("Schedule inputs must be an object no larger than 100 KB")
        if not isinstance(snapshot_sha256, str) or len(snapshot_sha256) != 64:
            raise ValueError("A workflow snapshot SHA-256 is required")
        parse_cron(cron)
        validate_timezone(timezone_name)
        next_run = next_cron_time(cron, timezone_name)
        schedule_id = str(uuid.uuid4())
        created = _now()
        with self._db() as db:
            count = db.execute("SELECT COUNT(*) FROM schedules WHERE project_path=?", (project_path,)).fetchone()[0]
            if count >= 100:
                raise ValueError("A project can have at most 100 recurring schedules")
            duplicate = db.execute("SELECT 1 FROM schedules WHERE project_path=? AND schedule_name=? COLLATE NOCASE", (project_path, name.strip())).fetchone()
            if duplicate:
                raise ValueError("A schedule with that name already exists in this project")
            db.execute("INSERT INTO schedules(schedule_id,project_path,schedule_name,workflow_name,snapshot_sha256,inputs_json,cron,timezone,next_run,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (schedule_id, project_path, name.strip(), workflow, snapshot_sha256, _json(inputs), cron, timezone_name, next_run, created))
            return self._schedule_record(db.execute("SELECT * FROM schedules WHERE schedule_id=?", (schedule_id,)).fetchone())

    def list_schedules(self, project_path: str) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM schedules WHERE project_path=? ORDER BY created_at DESC", (project_path,)).fetchall()
            return [self._schedule_record(row) for row in rows]

    def set_schedule_enabled(self, project_path: str, schedule_id: str, enabled: bool) -> dict[str, Any] | None:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        with self._db() as db:
            row = db.execute("SELECT * FROM schedules WHERE project_path=? AND schedule_id=?", (project_path, schedule_id)).fetchone()
            if row is None:
                return None
            next_run = next_cron_time(row["cron"], row["timezone"]) if enabled else row["next_run"]
            db.execute("UPDATE schedules SET enabled=?,next_run=?,last_error_json=CASE WHEN ? THEN NULL ELSE last_error_json END WHERE schedule_id=?",
                       (int(enabled), next_run, int(enabled), schedule_id))
            return self._schedule_record(db.execute("SELECT * FROM schedules WHERE schedule_id=?", (schedule_id,)).fetchone())

    def disable_schedule_for_error(self, project_path: str, schedule_id: str, error: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute("UPDATE schedules SET enabled=0,last_error_json=? WHERE project_path=? AND schedule_id=?",
                       (_json(error), project_path, schedule_id))

    def delete_schedule(self, project_path: str, schedule_id: str) -> bool:
        with self._db() as db:
            cursor = db.execute("DELETE FROM schedules WHERE project_path=? AND schedule_id=?", (project_path, schedule_id))
            return cursor.rowcount == 1

    def due_schedules(self, project_path: str, *, now: str | None = None) -> list[dict[str, Any]]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM schedules WHERE project_path=? AND enabled=1 AND next_run<=? ORDER BY next_run", (project_path, now or _now())).fetchall()
            return [{**self._schedule_record(row), "inputs": json.loads(row["inputs_json"]),
                     "snapshotSha256": row["snapshot_sha256"], "scheduledFor": row["next_run"]} for row in rows]

    def enqueue_schedule_occurrence(self, project_path: str, schedule_id: str, expected_slot: str,
                                    project_name: str, *, now: str | None = None) -> dict[str, Any] | None:
        current = now or _now()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM schedules WHERE project_path=? AND schedule_id=? AND enabled=1 AND next_run=? AND next_run<=?",
                             (project_path, schedule_id, expected_slot, current)).fetchone()
            if row is None:
                db.commit()
                return None
            active_count = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','scheduled','running')").fetchone()[0]
            next_run = next_cron_time(row["cron"], row["timezone"], after=datetime.fromisoformat(current))
            if active_count >= MAX_JOBS:
                db.execute("UPDATE schedules SET next_run=?,last_error_json=? WHERE schedule_id=?",
                           (next_run, _json({"code": "job-queue-full", "message": f"The active job queue is full ({MAX_JOBS} jobs); this scheduled occurrence was skipped."}), schedule_id))
                db.commit()
                return None
            job_id = str(uuid.uuid4())
            idempotency_key = f"schedule:{schedule_id}:{expected_slot}"
            db.execute("INSERT INTO jobs(job_id,idempotency_key,project_path,project_name,workflow_name,snapshot_sha256,inputs_json,available_at,status,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (job_id, idempotency_key, project_path, project_name, row["workflow_name"], row["snapshot_sha256"], row["inputs_json"], current, "queued", _now()))
            db.execute("UPDATE schedules SET next_run=?,last_triggered_at=?,last_job_id=?,last_error_json=NULL WHERE schedule_id=?",
                       (next_run, expected_slot, job_id, schedule_id))
            db.commit()
            job = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            return self._record(job)


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
