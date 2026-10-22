"""Credential storage helpers. Secret values are kept in an approved OS vault."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .app_paths import app_data_dir

SAFE_BACKEND_MARKERS = (
    "keyring.backends.Windows.WinVaultKeyring",
    "keyring.backends.macOS.Keyring",
    "keyring.backends.SecretService.Keyring",
)


def get_safe_keyring():
    try:
        import keyring
    except ImportError as exc:
        raise RuntimeError("Secure credentials require the optional keyring package and an OS credential vault") from exc
    backend=keyring.get_keyring()
    backend_name=f"{type(backend).__module__}.{type(backend).__name__}"
    if not any(backend_name.startswith(marker) for marker in SAFE_BACKEND_MARKERS):
        raise RuntimeError(f"Refusing credential access through non-approved keyring backend: {backend_name}")
    return keyring


def _index_path() -> Path:
    return app_data_dir() / "credentials-index.json"


def list_credentials() -> list[dict[str, str]]:
    """List credential labels and vault references only; never return secret values."""
    path = _index_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Credential index is unreadable; repair or back it up before editing credentials") from exc
    if not isinstance(payload, list) or len(payload) > 2000:
        raise RuntimeError("Credential index has an unsupported format")
    records = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        service, username, label = item.get("service"), item.get("username"), item.get("label")
        if all(isinstance(value, str) and 0 < len(value) <= 200 for value in (service, username, label)):
            records.append({"service": service, "username": username, "label": label})
    return sorted(records, key=lambda item: (item["label"].casefold(), item["service"], item["username"]))


def update_credential_index(service: str, username: str, label: str | None = None, *, remove: bool = False) -> None:
    """Maintain non-secret metadata for credentials managed through Studio."""
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    records = list_credentials()
    records = [item for item in records if (item["service"], item["username"]) != (service, username)]
    if not remove:
        value = (label or username).strip()
        if not value or len(value) > 200:
            raise ValueError("Credential label must contain 1–200 characters")
        records.append({"service": service, "username": username, "label": value})
    document = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fd, temporary = tempfile.mkstemp(prefix=".credentials-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
