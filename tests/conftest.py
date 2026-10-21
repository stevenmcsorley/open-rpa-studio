from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_active_studio_project_pointer(monkeypatch, tmp_path):
    """Never let tests read or overwrite the developer's installed Studio state."""
    monkeypatch.setenv(
        "OPENRPA_ACTIVE_PROJECT_FILE",
        str(tmp_path / ".test-app-state" / "active-project.json"),
    )
