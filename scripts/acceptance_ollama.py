"""Run a real, local Ollama → validator → workflow-engine acceptance check."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from openrpa.ai_providers import draft, models
from openrpa.engine import run_project
from openrpa.model import validate_workflow


def _activities_for(workflow: dict[str, Any], execution_model: str) -> list[dict[str, Any]]:
    if execution_model == "sequence":
        return workflow.get("activities", [])
    if execution_model == "flowchart":
        return [node.get("activity") for node in workflow["flowchart"]["nodes"] if node.get("kind") == "action"]
    return [activity for state in workflow["stateMachine"]["states"] for activity in state.get("activities", [])]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.environ.get("OPENRPA_OLLAMA_TEST_MODEL", "qwen35-4b:latest"))
    args = parser.parse_args()

    installed = models("ollama")
    if args.model not in installed:
        print(f"Ollama model {args.model!r} is unavailable. Installed models: {', '.join(installed) or '(none)'}", file=sys.stderr)
        return 2

    activity_types = ["log"]
    results: list[dict[str, Any]] = []
    for execution_model in ("sequence", "flowchart", "state_machine"):
        started = time.perf_counter()
        warnings: list[str] = []
        payload = draft(
            "ollama", args.model,
            "Create a workflow that writes exactly one log entry containing the text hello.",
            activity_types,
            execution_model=execution_model,
            on_compatibility_fallback=warnings.append,
        )
        workflow: dict[str, Any] = {
            "format": "openrpa.workflow",
            "formatVersion": 1,
            "name": "Local Ollama acceptance",
            "variables": [],
            "arguments": [],
            "activities": payload.get("activities", []) if execution_model == "sequence" else [],
        }
        if execution_model != "sequence":
            key = "flowchart" if execution_model == "flowchart" else "stateMachine"
            workflow["executionModel"] = execution_model
            workflow[key] = payload.get(key)

        problems = validate_workflow(workflow, {"Main"})
        if problems:
            raise RuntimeError(f"{execution_model} draft failed local validation: {problems[0]['code']}")
        activities = _activities_for(workflow, execution_model)
        if len(activities) != 1 or activities[0].get("type") != "log":
            raise RuntimeError(f"{execution_model} draft was not a single log activity; execution was skipped")

        with tempfile.TemporaryDirectory(prefix="openrpa-ollama-acceptance-") as temporary:
            root = Path(temporary)
            relative = "workflows/main.workflow.json"
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(workflow, ensure_ascii=False), encoding="utf-8")
            project = {
                "format": "openrpa.project",
                "formatVersion": 1,
                "name": "Local Ollama acceptance",
                "main": "Main",
                "workflows": {"Main": relative},
            }
            result = run_project(project, root, "Main")

        log_events = [event for event in result.logs if event.get("event") == "log"]
        if result.status != "succeeded" or len(log_events) != 1 or "hello" not in str(log_events[0].get("message", "")).lower():
            raise RuntimeError(f"{execution_model} execution did not produce exactly one expected log entry")
        results.append({
            "provider": "ollama",
            "model": args.model,
            "structure": execution_model,
            "validated": True,
            "runStatus": result.status,
            "logEventCount": len(log_events),
            "compatibilityFallbackUsed": bool(warnings),
            "elapsedSeconds": round(time.perf_counter() - started, 3),
        })

    print(json.dumps({"status": "passed", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
