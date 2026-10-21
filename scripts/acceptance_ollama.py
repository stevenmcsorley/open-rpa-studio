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

    results: list[dict[str, Any]] = []
    old_data_dir = os.environ.get("OPENRPA_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="openrpa-ollama-acceptance-") as temporary:
        root = Path(temporary)
        os.environ["OPENRPA_DATA_DIR"] = str(root / "application-data")
        from openrpa import bridge

        original_send = bridge.send
        replies: list[dict[str, Any]] = []
        bridge.send = replies.append
        try:
            installed = bridge.ai_providers.models("ollama")
            if args.model not in installed:
                print(f"Ollama model {args.model!r} is unavailable. Installed models: {', '.join(installed) or '(none)'}", file=sys.stderr)
                return 2
            for index, execution_model in enumerate(("sequence", "flowchart", "state_machine"), start=1):
                started = time.perf_counter()
                bridge.handle({
                    "id": index,
                    "method": "ai.draft",
                    "params": {
                        "provider": "ollama",
                        "model": args.model,
                        "prompt": "Create a workflow that writes exactly one log entry containing the text hello.",
                        "executionModel": execution_model,
                        "workflows": ["Main"],
                    },
                })
                response = replies.pop()
                if "error" in response:
                    raise RuntimeError(f"{execution_model} bridge request failed: {response['error'].get('type', 'error')}")
                draft_result = response["result"]
                usage=draft_result.get("usage")
                if not isinstance(usage,dict) or not all(isinstance(usage.get(key),int) and usage[key]>=0 for key in ("inputTokens","outputTokens","totalTokens")):
                    raise RuntimeError(f"{execution_model} draft did not return valid Ollama-reported token usage")
                workflow = draft_result["workflow"]
                problems = validate_workflow(workflow, {"Main"})
                if not draft_result.get("valid") or problems:
                    code = problems[0]["code"] if problems else "bridge-validation-failed"
                    raise RuntimeError(f"{execution_model} draft failed local validation: {code}")
                activities = _activities_for(workflow, execution_model)
                if len(activities) != 1 or activities[0].get("type") != "log":
                    raise RuntimeError(f"{execution_model} draft was not a single log activity; execution was skipped")

                run_root = root / f"execution-{execution_model}"
                relative = "workflows/main.workflow.json"
                path = run_root / relative
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(workflow, ensure_ascii=False), encoding="utf-8")
                project = {
                    "format": "openrpa.project",
                    "formatVersion": 1,
                    "name": "Local Ollama acceptance",
                    "main": "Main",
                    "workflows": {"Main": relative},
                }
                result = run_project(project, run_root, "Main")
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
                    "usage": usage,
                    "compatibilityFallbackUsed": any("rejected JSON Schema mode" in warning for warning in draft_result.get("warnings", [])),
                    "warnings": draft_result.get("warnings", []),
                    "elapsedSeconds": round(time.perf_counter() - started, 3),
                })
        finally:
            bridge.send = original_send
            if old_data_dir is None:
                os.environ.pop("OPENRPA_DATA_DIR", None)
            else:
                os.environ["OPENRPA_DATA_DIR"] = old_data_dir

    print(json.dumps({"status": "passed", "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
