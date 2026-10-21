"""Non-invasive detection of Playwright engines and common installed browsers."""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any, Callable


def _existing(candidates: list[str | Path]) -> str | None:
    for candidate in candidates:
        try:
            path = Path(candidate).expanduser()
            if path.is_file():
                return str(path)
        except (OSError, TypeError, ValueError):
            continue
    return None


_INSTALLED_BROWSERS: dict[str, dict[str, Any]] = {
    "chrome": {"name": "Google Chrome", "commands": ("chrome", "google-chrome", "google-chrome-stable"),
               "windows": (Path("Google") / "Chrome" / "Application" / "chrome.exe",),
               "mac": (Path("Google Chrome.app") / "Contents" / "MacOS" / "Google Chrome",),
               "linux": ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/opt/google/chrome/chrome")},
    "msedge": {"name": "Microsoft Edge", "commands": ("msedge", "microsoft-edge", "microsoft-edge-stable"),
               "windows": (Path("Microsoft") / "Edge" / "Application" / "msedge.exe",),
               "mac": (Path("Microsoft Edge.app") / "Contents" / "MacOS" / "Microsoft Edge",),
               "linux": ("/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable", "/opt/microsoft/msedge/msedge")},
    "brave": {"name": "Brave", "commands": ("brave", "brave-browser"),
              "windows": (Path("BraveSoftware") / "Brave-Browser" / "Application" / "brave.exe",),
              "mac": (Path("Brave Browser.app") / "Contents" / "MacOS" / "Brave Browser",),
              "linux": ("/usr/bin/brave", "/usr/bin/brave-browser", "/opt/brave.com/brave/brave")},
    "vivaldi": {"name": "Vivaldi", "commands": ("vivaldi", "vivaldi-stable"),
                "windows": (Path("Vivaldi") / "Application" / "vivaldi.exe", Path("Vivaldi")),
                "mac": (Path("Vivaldi.app") / "Contents" / "MacOS" / "Vivaldi",),
                "linux": ("/usr/bin/vivaldi", "/usr/bin/vivaldi-stable", "/opt/vivaldi/vivaldi")},
    "opera": {"name": "Opera", "commands": ("opera", "opera-stable"),
              "windows": (Path("Programs") / "Opera" / "launcher.exe", Path("Opera") / "launcher.exe"),
              "mac": (Path("Opera.app") / "Contents" / "MacOS" / "Opera",),
              "linux": ("/usr/bin/opera", "/usr/bin/opera-stable", "/usr/lib/x86_64-linux-gnu/opera/opera")},
    "opera_gx": {"name": "Opera GX", "commands": ("opera-gx", "opera-gx-stable"),
                 "windows": (Path("Programs") / "Opera GX" / "launcher.exe", Path("Opera GX") / "launcher.exe"),
                 "mac": (Path("Opera GX.app") / "Contents" / "MacOS" / "Opera GX",),
                 "linux": ("/usr/bin/opera-gx", "/usr/bin/opera-gx-stable")},
}


def _installed_channel(channel: str, system: str, env: dict[str, str], which: Callable[[str], str | None]) -> str | None:
    spec = _INSTALLED_BROWSERS.get(channel)
    if spec is None:
        return None
    commands = spec["commands"]
    found = [path for command in commands if (path := which(command))]
    candidates: list[str | Path] = list(found)
    if system == "Windows":
        for root_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            root = env.get(root_name)
            if root:
                for relative in spec["windows"]:
                    candidates.append(Path(root) / relative)
    elif system == "Darwin":
        for app in spec["mac"]:
            candidates.extend((Path("/Applications") / app,
                               Path(env.get("HOME", "")) / "Applications" / app))
    elif system == "Linux":
        candidates.extend(spec["linux"])
    return _existing(candidates)


def status(playwright_factory: Callable[[], Any] | None = None, *,
           system: str | None = None, env: dict[str, str] | None = None,
           which: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Report detectable runtimes without starting browsers or visiting a site.

    Detection means an executable is present, not that every OS dependency or
    target-site behavior has been verified. Launch failures remain explicit at
    the activity that selects that runtime.
    """
    system = system or platform.system()
    env = dict(os.environ) if env is None else env
    which = shutil.which if which is None else which
    try:
        if playwright_factory is None:
            from playwright.sync_api import sync_playwright
            playwright_factory = sync_playwright
        with playwright_factory() as runtime:
            managed: dict[str, str | None] = {}
            for name in ("chromium", "firefox", "webkit"):
                try:
                    managed[name] = _existing([getattr(runtime, name).executable_path])
                except Exception:
                    managed[name] = None
    except ImportError:
        return {"available": False, "reason": "Optional Playwright package is not installed",
                "engines": {}, "channels": {}}
    except Exception as exc:
        return {"available": False, "reason": f"Playwright runtime probe failed: {type(exc).__name__}: {exc}",
                "engines": {}, "channels": {}}

    channels = {
        "chromium": {"available": managed["chromium"] is not None,
                      "executable": managed["chromium"], "source": "Playwright-managed" if managed["chromium"] else None},
    }
    for channel, spec in _INSTALLED_BROWSERS.items():
        executable = _installed_channel(channel, system, env, which)
        channels[channel] = {"available": executable is not None, "executable": executable,
                             "source": "installed browser" if executable else None,
                             "name": spec["name"]}
    chromium_paths = [channels[name]["executable"] for name in channels if channels[name]["executable"]]
    engines = {
        "chromium": {"available": bool(chromium_paths), "executables": chromium_paths},
        "firefox": {"available": managed["firefox"] is not None, "executable": managed["firefox"]},
        "webkit": {"available": managed["webkit"] is not None, "executable": managed["webkit"]},
    }
    available = any(engine["available"] for engine in engines.values())
    return {"available": available,
            "reason": None if available else "No Playwright browser executable or supported installed Chromium channel was detected",
            "engines": engines, "channels": channels,
            "detectionNote": "Executable presence only; browser launch compatibility is checked when the activity runs."}


def probe(browser_type: str = "chromium", channel: str = "chromium", executable_path: str = "",
          playwright_factory: Callable[[], Any] | None = None) -> dict[str, str]:
    """Launch and close the selected runtime locally; do not navigate or use network."""
    if browser_type not in {"chromium", "firefox", "webkit"}:
        raise ValueError("Choose Chromium, Firefox, or WebKit")
    if channel not in {"chromium", "chrome", "msedge", "custom"}:
        raise ValueError("Choose Playwright Chromium, Chrome, Edge, or a custom Chromium browser")
    if browser_type != "chromium" and (channel != "chromium" or executable_path):
        raise ValueError("Chrome/Edge channels and custom executable paths are supported only with Chromium")
    options: dict[str, Any] = {"headless": True, "timeout": 10_000}
    if browser_type == "chromium":
        if channel == "custom":
            if not isinstance(executable_path, str) or not executable_path.strip() or len(executable_path) > 4096 or "\x00" in executable_path:
                raise ValueError("Custom Chromium needs an absolute executable path of at most 4,096 characters")
            try:
                target = Path(executable_path).expanduser().resolve(strict=True)
            except (OSError, ValueError) as exc:
                raise ValueError("Custom Chromium executable does not exist") from exc
            if not target.is_absolute() or not target.is_file():
                raise ValueError("Custom Chromium executable path is not a file")
            options["executable_path"] = str(target)
        elif channel != "chromium":
            options["channel"] = channel
        elif executable_path:
            raise ValueError("Set the Chromium channel to custom when configuring an executable path")
    try:
        if playwright_factory is None:
            from playwright.sync_api import sync_playwright
            playwright_factory = sync_playwright
        with playwright_factory() as runtime:
            launcher = getattr(runtime, browser_type, None)
            if launcher is None:
                raise RuntimeError(f"Playwright browser engine '{browser_type}' is unavailable")
            browser = launcher.launch(**options)
            try:
                version = str(getattr(browser, "version", ""))[:120]
            finally:
                browser.close()
        return {"browserType": browser_type, "channel": channel, "version": version,
                "headless": "true", "networkUsed": "false"}
    except ImportError as exc:
        raise RuntimeError("Browser check requires the optional Playwright package. See docs/AUTOMATION_ADAPTERS.md") from exc
    except Exception as exc:
        detail = str(exc)
        if "Executable doesn't exist" in detail or "executable doesn't exist" in detail.lower():
            if browser_type in {"firefox", "webkit"}:
                raise RuntimeError(f"Playwright {browser_type.title()} is not installed. Install it with 'playwright install {browser_type}'.") from exc
            if channel == "chromium":
                raise RuntimeError("Playwright Chromium is not installed. Install it with 'playwright install chromium', or select installed Google Chrome or Microsoft Edge.") from exc
            raise RuntimeError(f"The selected Chromium browser ('{channel}') was not found. Select an installed browser or verify the executable path.") from exc
        raise RuntimeError(f"Could not launch the selected {browser_type.title()} browser ('{channel}'): {type(exc).__name__}: {detail[:1000]}") from exc
