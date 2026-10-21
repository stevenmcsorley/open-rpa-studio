"""Infer a bounded, value-free mapping outline from an observed JSON response.

This is a convenience for authoring, not a contract: it samples at most a small
number of object rows and never returns response values to the UI or audit log.
"""
from __future__ import annotations

import json
import re
from typing import Any

MAX_BODY_BYTES = 2_000_000
MAX_DEPTH = 8
MAX_CANDIDATES = 20
MAX_FIELDS = 50
SAMPLE_ROWS = 20
SENSITIVE = re.compile(r"(?:password|passwd|secret|token|authorization|cookie|credential|api[_-]?key)", re.I)


def _pointer(parts: tuple[str, ...]) -> str:
    return "".join("/" + part.replace("~", "~0").replace("/", "~1") for part in parts)


def _field_name(path: tuple[str, ...]) -> str:
    leaf = re.sub(r"[^A-Za-z0-9_]+", "_", path[-1]).strip("_") or "field"
    return leaf[:80]


def _kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "object" if isinstance(value, dict) else "array"


def discover_response(body: str) -> dict[str, Any]:
    """Return candidate object-array locations and scalar field paths only."""
    if not isinstance(body, str) or len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("API response is not text or exceeds the 2 MB discovery limit")
    try:
        document = json.loads(body)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("API response is not valid JSON") from exc

    candidates: list[dict[str, Any]] = []
    visited = 0

    def visit(value: Any, parts: tuple[str, ...], depth: int) -> None:
        nonlocal visited
        visited += 1
        if visited > 5_000 or depth > MAX_DEPTH or len(candidates) >= MAX_CANDIDATES:
            return
        location = _pointer(parts)
        if len(location) > 2_048:
            return
        if isinstance(value, list):
            rows = [row for row in value[:SAMPLE_ROWS] if isinstance(row, dict)]
            if rows:
                types: dict[tuple[str, ...], set[str]] = {}

                def collect(row: Any, prefix: tuple[str, ...], level: int) -> None:
                    if level > MAX_DEPTH or not isinstance(row, dict):
                        return
                    for raw_name, child in list(row.items())[:MAX_FIELDS]:
                        if not isinstance(raw_name, str) or SENSITIVE.search(raw_name):
                            continue
                        child_path = prefix + (raw_name,)
                        if isinstance(child, dict):
                            collect(child, child_path, level + 1)
                        elif not isinstance(child, list):
                            types.setdefault(child_path, set()).add(_kind(child))

                for row in rows:
                    collect(row, (), 0)
                fields = []
                names: set[str] = set()
                for field_path, observed_types in sorted(types.items()):
                    field_pointer = _pointer(field_path)
                    if len(fields) >= MAX_FIELDS:
                        break
                    if len(field_pointer) > 2_048:
                        continue
                    name = _field_name(field_path)
                    if not name[0].isalpha() and name[0] != "_":
                        name = "field_" + name
                    if name.casefold() in names:
                        name = "_".join(_field_name((part,)) for part in field_path[-2:])[:80]
                        if not name[0].isalpha() and name[0] != "_":
                            name = "field_" + name
                    base = name
                    suffix = 2
                    while name.casefold() in names:
                        name = f"{base[:76]}_{suffix}"
                        suffix += 1
                    names.add(name.casefold())
                    fields.append({"name": name, "path": field_pointer,
                                   "type": next(iter(observed_types)) if len(observed_types) == 1 else "mixed"})
                candidates.append({"itemsPointer": location, "stablePointer": not any(part.isdigit() for part in parts),
                                   "observedRows": len(value), "sampledRows": len(rows), "fields": fields,
                                   "fieldsTruncated": len(types) > len(fields)})
            for index, child in enumerate(value[:SAMPLE_ROWS]):
                if isinstance(child, (dict, list)):
                    visit(child, parts + (str(index),), depth + 1)
            return
        if isinstance(value, dict):
            for key, child in list(value.items())[:MAX_FIELDS]:
                if isinstance(key, str) and isinstance(child, (dict, list)):
                    visit(child, parts + (key,), depth + 1)

    visit(document, (), 0)
    # Numeric indexes are useful evidence but unstable as a JSON Pointer for an
    # array nested inside another array; leave those candidates visible while
    # excluding them from automatic field mapping in the UI.
    return {"candidates": candidates}
