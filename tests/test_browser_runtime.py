from pathlib import Path

import pytest

from openrpa import browser_runtime


class _Runtime:
    def __init__(self, paths):
        for name, path in paths.items():
            setattr(self, name, type("BrowserType", (), {"executable_path": str(path)})())

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_status_distinguishes_managed_engines_from_installed_chrome_and_edge(tmp_path: Path):
    chromium = tmp_path / "playwright-chromium.exe"
    firefox = tmp_path / "playwright-firefox.exe"
    chrome = tmp_path / "chrome.exe"
    edge = tmp_path / "msedge.exe"
    for item in (chromium, firefox, chrome, edge):
        item.write_bytes(b"fixture")
    result = browser_runtime.status(
        lambda: _Runtime({"chromium": chromium, "firefox": firefox, "webkit": tmp_path / "missing-webkit"}),
        system="Windows", env={}, which=lambda name: {"chrome": str(chrome), "msedge": str(edge)}.get(name),
    )
    assert result["available"] is True
    assert result["engines"]["chromium"]["available"] is True
    assert result["engines"]["firefox"]["available"] is True
    assert result["engines"]["webkit"]["available"] is False
    assert result["channels"]["chrome"]["executable"] == str(chrome)
    assert result["channels"]["msedge"]["executable"] == str(edge)
    assert "checked when the activity runs" in result["detectionNote"]


def test_status_discovers_common_chromium_browsers_by_name(tmp_path: Path):
    brave = tmp_path / "brave.exe"
    vivaldi = tmp_path / "vivaldi.exe"
    brave.write_bytes(b"fixture")
    vivaldi.write_bytes(b"fixture")
    paths = {"brave-browser": str(brave), "vivaldi-stable": str(vivaldi)}
    result = browser_runtime.status(
        lambda: _Runtime({name: tmp_path / f"missing-{name}" for name in ("chromium", "firefox", "webkit")}),
        system="Linux", env={}, which=lambda name: paths.get(name),
    )
    assert result["channels"]["brave"] == {"available": True, "executable": str(brave), "source": "installed browser", "name": "Brave"}
    assert result["channels"]["vivaldi"]["available"] is True
    assert result["channels"]["opera"]["available"] is False
    assert result["engines"]["chromium"]["available"] is True


def test_status_discovers_windows_user_installs_of_brave_and_vivaldi(tmp_path: Path):
    local = tmp_path / "LocalAppData"
    brave = local / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"
    vivaldi = local / "Vivaldi" / "Application" / "vivaldi.exe"
    brave.parent.mkdir(parents=True)
    vivaldi.parent.mkdir(parents=True)
    brave.write_bytes(b"fixture")
    vivaldi.write_bytes(b"fixture")
    result = browser_runtime.status(
        lambda: _Runtime({name: tmp_path / f"missing-{name}" for name in ("chromium", "firefox", "webkit")}),
        system="Windows", env={"LOCALAPPDATA": str(local)}, which=lambda _name: None,
    )
    assert result["channels"]["brave"]["executable"] == str(brave)
    assert result["channels"]["vivaldi"]["executable"] == str(vivaldi)


def test_installed_chromium_channel_counts_as_browser_availability_without_playwright_managed_chromium(tmp_path: Path):
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"fixture")
    result = browser_runtime.status(
        lambda: _Runtime({"chromium": tmp_path / "missing-chromium", "firefox": tmp_path / "missing-firefox", "webkit": tmp_path / "missing-webkit"}),
        system="Windows", env={}, which=lambda name: str(chrome) if name == "chrome" else None,
    )
    assert result["available"] is True
    assert result["engines"]["chromium"]["available"] is True
    assert result["channels"]["chromium"]["available"] is False
    assert result["channels"]["chrome"]["available"] is True


def test_status_reports_no_browser_when_all_runtimes_are_missing(tmp_path: Path):
    result = browser_runtime.status(
        lambda: _Runtime({name: tmp_path / f"missing-{name}" for name in ("chromium", "firefox", "webkit")}),
        system="Linux", env={}, which=lambda _name: None,
    )
    assert result["available"] is False
    assert "No Playwright browser executable" in result["reason"]


def test_status_reports_missing_optional_playwright_package():
    def missing_runtime():
        raise ImportError("missing")
    result = browser_runtime.status(missing_runtime)
    assert result["available"] is False
    assert result["reason"] == "Optional Playwright package is not installed"


def test_probe_launches_requested_channel_headless_and_closes_without_network():
    seen = {}
    class Browser:
        version = "Chromium 132"
        def close(self):
            seen["closed"] = True
    class Launcher:
        def launch(self, **options):
            seen["options"] = options
            return Browser()
    class Runtime(_Runtime):
        chromium = Launcher()
    result = browser_runtime.probe("chromium", "chrome", playwright_factory=lambda: Runtime({}))
    assert result == {"browserType": "chromium", "channel": "chrome", "version": "Chromium 132", "headless": "true", "networkUsed": "false"}
    assert seen == {"options": {"headless": True, "timeout": 10_000, "channel": "chrome"}, "closed": True}


def test_probe_gives_actionable_install_guidance_for_missing_playwright_browser():
    class Launcher:
        def launch(self, **_options):
            raise RuntimeError("BrowserType.launch: Executable doesn't exist at /playwright/chromium")
    class Runtime(_Runtime):
        chromium = Launcher()
    with pytest.raises(RuntimeError, match="playwright install chromium"):
        browser_runtime.probe("chromium", "chromium", playwright_factory=lambda: Runtime({}))


def test_probe_rejects_browser_engine_channel_mismatch_before_runtime_start():
    def must_not_start():
        raise AssertionError("invalid options should be rejected before starting Playwright")
    with pytest.raises(ValueError, match="supported only with Chromium"):
        browser_runtime.probe("firefox", "chrome", playwright_factory=must_not_start)
