"""Point the Tauri bundle at the current platform's frozen MCP bridge."""
from __future__ import annotations

import json
import sys
import platform
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit("usage: configure_unix_bundle.py VERSION")
    version = sys.argv[1]
    root = Path(__file__).resolve().parents[1]
    config_path = root / "src-tauri" / "tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    bridge = root / "src-tauri" / "resources" / f"openrpa-bridge-{version}"
    if not bridge.is_file():
        raise SystemExit(f"native bridge does not exist: {bridge}")
    config.setdefault("bundle", {})["resources"] = {
        "../openrpa/": "engine/openrpa/",
        str(bridge.relative_to(root / "src-tauri")).replace("\\", "/"): f"engine/{bridge.name}",
    }
    config["bundle"]["icon"] = ["icons/icon.icns"] if platform.system() == "Darwin" else ["icons/128x128.png"]
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    # `generate_context!` also reads this conventional filename while
    # embedding the app icon, even when the bundle target has its own icon list.
    icons_dir = root / "src-tauri" / "icons"
    (icons_dir / "icon.png").write_bytes((icons_dir / "128x128.png").read_bytes())


if __name__ == "__main__":
    main()
