"""Local AI endpoint profiles; credentials remain in the OS vault."""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .ai_providers import PROVIDERS, _endpoint

FORMAT = "openrpa.ai-connections"
VERSION = 1
MAX_PROFILES = 100
MAX_FILE_BYTES = 1_000_000


def _normalize(value: Any, *, require_id: bool = False) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("AI connection profile must be an object")
    allowed = {"id", "name", "provider", "baseUrl", "model", "credentialService", "credentialUsername"}
    if set(value) - allowed:
        raise ValueError("AI connection profile contains unsupported fields")
    profile_id = value.get("id")
    if require_id:
        try:
            profile_id = str(uuid.UUID(str(profile_id)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("AI connection profile has an invalid id") from exc
    elif profile_id:
        try:
            profile_id = str(uuid.UUID(str(profile_id)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("AI connection profile has an invalid id") from exc
    else:
        profile_id = str(uuid.uuid4())
    name = value.get("name")
    provider = value.get("provider")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise ValueError("AI connection name must contain 1–100 characters")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ValueError("Choose a supported AI provider")
    spec = PROVIDERS[provider]
    base_url = value.get("baseUrl") or spec["defaultBaseUrl"]
    if not isinstance(base_url, str) or len(base_url) > 2048:
        raise ValueError("AI provider base URL must be at most 2,048 characters")
    route = "/api/tags" if provider == "ollama" else ("/v1/models" if provider == "claude" else "/models")
    _endpoint(provider, base_url, route)
    model = value.get("model", "")
    if not isinstance(model, str) or len(model) > 200:
        raise ValueError("AI model name must be at most 200 characters")
    service = value.get("credentialService", "")
    username = value.get("credentialUsername", "")
    if not isinstance(service, str) or not isinstance(username, str) or len(service) > 200 or len(username) > 200:
        raise ValueError("Credential vault references must be at most 200 characters")
    if spec["requiresCredential"] and (not service.strip() or not username.strip()):
        raise ValueError("Remote provider profiles require OS vault service and username references")
    return {"id": profile_id, "name": name.strip(), "provider": provider, "baseUrl": base_url.rstrip("/"),
            "model": model.strip(), "credentialService": service.strip(), "credentialUsername": username.strip()}


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("AI connection profile file exceeds its size limit")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("AI connection profile file is unreadable or malformed") from exc
    if not isinstance(document, dict) or set(document) != {"format", "formatVersion", "profiles"} or document.get("format") != FORMAT or document.get("formatVersion") != VERSION or not isinstance(document.get("profiles"), list):
        raise ValueError("Unsupported AI connection profile file format")
    rows = document["profiles"]
    if len(rows) > MAX_PROFILES:
        raise ValueError("AI connection profile file exceeds the profile limit")
    profiles = [_normalize(row, require_id=True) for row in rows]
    if len({row["id"] for row in profiles}) != len(profiles):
        raise ValueError("AI connection profile ids must be unique")
    if len({row["name"].casefold() for row in profiles}) != len(profiles):
        raise ValueError("AI connection profile names must be unique")
    return profiles


def list_profiles(path: Path) -> list[dict[str, str]]:
    return _read(path)


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    if len(rows) > MAX_PROFILES:
        raise ValueError(f"You can save at most {MAX_PROFILES} AI connection profiles")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ai-connections-", suffix=".tmp", dir=path.parent)
    try:
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump({"format": FORMAT, "formatVersion": VERSION, "profiles": rows}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_profile(path: Path, value: Any) -> dict[str, str]:
    profile = _normalize(value)
    profiles = _read(path)
    for existing in profiles:
        if existing["id"] != profile["id"] and existing["name"].casefold() == profile["name"].casefold():
            raise ValueError("An AI connection with this name already exists")
    matching = next((index for index, item in enumerate(profiles) if item["id"] == profile["id"]), None)
    if matching is None:
        profiles.append(profile)
    else:
        profiles[matching] = profile
    _write(path, profiles)
    return profile


def delete_profile(path: Path, profile_id: str) -> None:
    try:
        normalized_id = str(uuid.UUID(profile_id))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("AI connection profile id is invalid") from exc
    profiles = _read(path)
    remaining = [item for item in profiles if item["id"] != normalized_id]
    if len(remaining) == len(profiles):
        raise ValueError("AI connection profile was not found")
    _write(path, remaining)
