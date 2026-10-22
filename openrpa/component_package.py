"""Portable, declarative reusable-workflow components.

Components contain only ordinary Open RPA workflows. They do not install Python,
native code, or third-party dependencies and execute through the normal workflow
validator and permission model.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .model import WorkflowError, load_project, validate_workflow, validate_workflow_bindings

FORMAT = "org.openrpa.component"
VERSION = 1
MAX_COMPONENT_FILES = 200
MAX_COMPONENT_BYTES = 25_000_000
MAX_WORKFLOW_BYTES = 10_000_000
MAX_MANIFEST_BYTES = 1_000_000


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _workflow_calls(value: Any) -> set[str]:
    calls: set[str] = set()
    if isinstance(value, dict):
        if value.get("type") == "invoke_workflow" and isinstance(value.get("workflow"), str):
            calls.add(value["workflow"])
        for child in value.values():
            calls.update(_workflow_calls(child))
    elif isinstance(value, list):
        for child in value:
            calls.update(_workflow_calls(child))
    return calls


def _rewrite_calls(value: Any, names: dict[str, str]) -> None:
    if isinstance(value, dict):
        if value.get("type") == "invoke_workflow" and value.get("workflow") in names:
            value["workflow"] = names[value["workflow"]]
        for child in value.values():
            _rewrite_calls(child, names)
    elif isinstance(value, list):
        for child in value:
            _rewrite_calls(child, names)


def _safe_segment(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    return clean[:64] or "component"


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".openrpa-component-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def pack_component(project_path: str | Path, workflow_name: str, destination: str | Path) -> dict[str, Any]:
    project, root = load_project(project_path)
    if workflow_name not in project["workflows"]:
        raise WorkflowError(f"Workflow does not exist: {workflow_name}", code="component-workflow")

    loaded: dict[str, tuple[dict[str, Any], bytes]] = {}
    pending = [workflow_name]
    while pending:
        name = pending.pop()
        if name in loaded:
            continue
        relative = project["workflows"].get(name)
        if relative is None:
            raise WorkflowError(f"Component references an unavailable workflow: {name}", code="component-dependency")
        raw = (root / relative).read_bytes()
        if len(raw) > MAX_WORKFLOW_BYTES:
            raise WorkflowError(f"Workflow exceeds component size limit: {name}", code="component-size-limit")
        workflow = json.loads(raw.decode("utf-8"))
        loaded[name] = (workflow, raw)
        pending.extend(sorted(_workflow_calls(workflow) - loaded.keys(), reverse=True))
        if len(loaded) > MAX_COMPONENT_FILES:
            raise WorkflowError("Component contains too many workflows", code="component-size-limit")

    # Validate the dependency closure independently of unrelated project workflows.
    names = set(loaded)
    for name, (workflow, _) in loaded.items():
        problems = validate_workflow(workflow, names)
        if problems:
            first = problems[0]
            raise WorkflowError(f"{name}: {first['message']}", first.get("activityId"), first["code"])
    binding_problems = validate_workflow_bindings({name: workflow for name, (workflow, _) in loaded.items()})
    if binding_problems:
        first = binding_problems[0]
        raise WorkflowError(f"{first.get('workflow', 'Component')}: {first['message']}", first.get("activityId"), first["code"])

    ordered = [workflow_name] + sorted(names - {workflow_name})
    files = []
    payloads: list[tuple[str, bytes]] = []
    for index, name in enumerate(ordered):
        raw = json.dumps(loaded[name][0], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        path = f"workflows/{index:03d}.workflow.json"
        files.append({"name": name, "path": path, "size": len(raw), "sha256": _sha256_bytes(raw)})
        payloads.append((path, raw))
    manifest = {
        "format": FORMAT,
        "formatVersion": VERSION,
        "name": workflow_name,
        "entryWorkflow": workflow_name,
        "workflows": files,
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    total = len(manifest_bytes) + sum(len(raw) for _, raw in payloads)
    if total > MAX_COMPONENT_BYTES:
        raise WorkflowError("Component exceeds package size limit", code="component-size-limit")

    target = Path(destination).expanduser().resolve()
    if target.is_relative_to(root):
        raise WorkflowError("Component package output must be outside the project folder", code="component-destination")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".openrpa-component-", suffix=".tmp", dir=target.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path, raw in payloads:
                info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, raw)
            info = zipfile.ZipInfo("component-manifest.json", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, manifest_bytes)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"path": str(target), "workflowCount": len(files), "entryWorkflow": workflow_name, "sha256": _sha256_bytes(target.read_bytes())}


def install_component(package_path: str | Path, project_path: str | Path, namespace: str) -> dict[str, Any]:
    project, root = load_project(project_path)
    namespace = namespace.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,47}", namespace):
        raise WorkflowError("Component namespace must be 1–48 letters, numbers, spaces, dots, underscores, or hyphens", code="component-namespace")
    source = Path(package_path).expanduser().resolve()
    if not source.is_file():
        raise WorkflowError("Component package does not exist", code="component-not-found")
    if not zipfile.is_zipfile(source):
        raise WorkflowError("Component package is not a valid ZIP archive", code="component-archive")

    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_COMPONENT_FILES + 1:
            raise WorkflowError("Component contains too many files", code="component-size-limit")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise WorkflowError("Component contains duplicate archive paths", code="component-manifest")
        if sum(info.file_size for info in infos) > MAX_COMPONENT_BYTES:
            raise WorkflowError("Component exceeds package size limit", code="component-size-limit")
        manifest_info = next((info for info in infos if info.filename == "component-manifest.json"), None)
        if manifest_info is None or manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise WorkflowError("Component manifest is missing or too large", code="component-manifest")
        try:
            manifest = json.loads(archive.read(manifest_info))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkflowError("Component manifest is not valid JSON", code="component-manifest") from exc
        if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or manifest.get("formatVersion") != VERSION:
            raise WorkflowError("Unsupported component package format", code="component-version")
        rows = manifest.get("workflows")
        if not isinstance(rows, list) or not rows or len(rows) > MAX_COMPONENT_FILES:
            raise WorkflowError("Component workflow manifest is invalid", code="component-manifest")
        workflow_names: set[str] = set()
        payloads: dict[str, bytes] = {}
        declared_paths: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
                raise WorkflowError("Component workflow manifest is invalid", code="component-manifest")
            name, relative = row["name"], row.get("path")
            if name in workflow_names:
                raise WorkflowError("Component contains duplicate workflow names", code="component-manifest")
            workflow_names.add(name)
            path = PurePosixPath(relative) if isinstance(relative, str) else PurePosixPath("..")
            if "\\" in str(relative) or path.is_absolute() or ".." in path.parts or not str(relative).startswith("workflows/") or not str(relative).endswith(".workflow.json"):
                raise WorkflowError(f"Unsafe component path: {relative}", code="component-path")
            if str(relative) in declared_paths:
                raise WorkflowError("Component manifest contains duplicate paths", code="component-manifest")
            declared_paths.add(str(relative))
            info = next((entry for entry in infos if entry.filename == relative), None)
            if info is None or info.is_dir() or info.file_size > MAX_WORKFLOW_BYTES or info.file_size != row.get("size"):
                raise WorkflowError(f"Component workflow file is missing or invalid: {name}", code="component-manifest")
            if info.compress_size and info.file_size / info.compress_size > 200:
                raise WorkflowError("Component compression ratio is excessive", code="component-size-limit")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise WorkflowError("Symlinks are not allowed in components", code="component-path")
            raw = archive.read(info)
            if _sha256_bytes(raw) != row.get("sha256"):
                raise WorkflowError(f"Component integrity check failed: {name}", code="component-integrity")
            try:
                workflow = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise WorkflowError(f"Component workflow is not valid UTF-8 JSON: {name}", code="component-workflow") from exc
            if not isinstance(workflow, dict) or workflow.get("name") != name:
                raise WorkflowError(f"Component workflow name mismatch: {name}", code="component-workflow")
            payloads[name] = raw
        actual = {name for name in names if name != "component-manifest.json"}
        if actual != declared_paths:
            raise WorkflowError("Component file list does not match its manifest", code="component-manifest")
        entry = manifest.get("entryWorkflow")
        if entry not in workflow_names:
            raise WorkflowError("Component entry workflow is missing", code="component-manifest")
        workflows = {name: json.loads(raw.decode("utf-8")) for name, raw in payloads.items()}
        for name, workflow in workflows.items():
            problems = validate_workflow(workflow, workflow_names)
            if problems:
                first = problems[0]
                raise WorkflowError(f"{name}: {first['message']}", first.get("activityId"), first["code"])

    new_names = {name: f"{namespace} / {name}" for name in workflows}
    collisions = set(new_names.values()) & set(project["workflows"])
    if collisions:
        raise WorkflowError(f"Component workflow already installed: {sorted(collisions)[0]}", code="component-conflict")
    combined_names = set(project["workflows"]) | set(new_names.values())
    installed: dict[str, dict[str, Any]] = {}
    for old_name, workflow in workflows.items():
        imported = json.loads(json.dumps(workflow))
        imported["name"] = new_names[old_name]
        _rewrite_calls(imported, new_names)
        problems = validate_workflow(imported, combined_names)
        if problems:
            first = problems[0]
            raise WorkflowError(f"{new_names[old_name]}: {first['message']}", first.get("activityId"), first["code"])
        installed[new_names[old_name]] = imported
    binding_problems = validate_workflow_bindings(installed)
    if binding_problems:
        first = binding_problems[0]
        raise WorkflowError(f"{first.get('workflow', 'Component')}: {first['message']}", first.get("activityId"), first["code"])

    component_dir = root / "workflows" / "components" / f"{_safe_segment(namespace)}-{_sha256_bytes(source.read_bytes())[:8]}"
    if component_dir.exists():
        raise WorkflowError("Component destination already exists; choose a different namespace", code="component-conflict")
    relative_paths = {name: f"workflows/components/{component_dir.name}/{index:03d}.workflow.json" for index, name in enumerate(installed)}
    updated = dict(project)
    updated_workflows = dict(project["workflows"])
    updated_workflows.update(relative_paths)
    updated["workflows"] = updated_workflows

    # Write workflow files first and atomically publish the manifest last. On an error,
    # remove only the new component directory; the existing project remains intact.
    try:
        for name, workflow in installed.items():
            _atomic_json(root / relative_paths[name], workflow)
        _atomic_json(root / "project.json", updated)
    except Exception:
        shutil.rmtree(component_dir, ignore_errors=True)
        raise
    return {
        "path": str(root),
        "namespace": namespace,
        "entryWorkflow": new_names[entry],
        "workflows": list(installed),
        "sha256": _sha256_bytes(source.read_bytes()),
    }
