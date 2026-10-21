"""Live Windows OCR-click acceptance against a disposable local Tk window.

Run with:
  uv run --locked --extra desktop --extra ocr python scripts/acceptance_windows_ocr_click.py
"""
from __future__ import annotations

import json
import os
import tempfile
import tkinter as tk
from pathlib import Path

from openrpa.engine import RunOptions, run_project


def main() -> int:
    title = "Open RPA OCR Acceptance Fixture"
    root = tk.Tk()
    root.title(title)
    root.geometry("700x280+80+80")
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    root.configure(background="#f3f5f8")
    tk.Label(root, text="Local desktop automation check", font=("Segoe UI", 18),
             background="#f3f5f8").pack(pady=(34, 20))
    state = {"clicked": False, "run": None, "error": None, "clickInsideButton": None,
             "buttonPress": 0, "buttonRelease": 0, "cursorAfterClick": None, "foregroundTitle": None}

    def clicked() -> None:
        state["clicked"] = True

    button = tk.Button(root, text="Click safe test", command=clicked,
                       font=("Segoe UI", 22, "bold"), padx=24, pady=18)
    button.pack()
    button.bind("<ButtonPress-1>", lambda _event: state.__setitem__("buttonPress", state["buttonPress"] + 1))
    button.bind("<ButtonRelease-1>", lambda _event: state.__setitem__("buttonRelease", state["buttonRelease"] + 1))
    root.update_idletasks()
    workflow = {
        "format": "openrpa.workflow", "formatVersion": 1, "name": "Live OCR acceptance",
        "executionModel": "sequence", "arguments": [], "variables": [],
        "activities": [{"id": "ocr-click", "type": "desktop_ocr_click", "windowTitle": title,
                        "processId": os.getpid(), "text": "Click safe test", "confidenceThreshold": 70,
                        "timeoutSeconds": 15, "result": "ocrMatch"}],
    }
    project = {"format": "openrpa.project", "formatVersion": 1, "name": "Temporary OCR acceptance",
               "main": "Live OCR acceptance", "workflows": {"Live OCR acceptance": "workflow.json"}}

    def execute() -> None:
        import pyautogui
        original_click = pyautogui.click
        def track_click(x=None, y=None, *args, **kwargs):
            if x is not None and y is not None:
                bx, by = button.winfo_rootx(), button.winfo_rooty()
                state["clickInsideButton"] = bx <= int(x) < bx + button.winfo_width() and by <= int(y) < by + button.winfo_height()
            result = original_click(x, y, *args, **kwargs)
            state["cursorAfterClick"] = pyautogui.position()
            try:
                import win32gui
                state["foregroundTitle"] = win32gui.GetWindowText(win32gui.GetForegroundWindow())
            except Exception:
                pass
            return result
        pyautogui.click = track_click
        try:
            with tempfile.TemporaryDirectory(prefix="openrpa-ocr-acceptance-") as temporary:
                root_dir = Path(temporary)
                (root_dir / "workflow.json").write_text(json.dumps(workflow), encoding="utf-8")
                state["run"] = run_project(project, root_dir, options=RunOptions(allow_desktop=True))
        except Exception as exc:
            state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            pyautogui.click = original_click
        root.after(1500, finish)

    def finish() -> None:
        run = state["run"]
        variables = run.variables if run else {}
        result = {
            "status": "passed" if run and run.status == "succeeded" and state["clicked"] else "failed",
            "runStatus": run.status if run else None,
            "activityResult": variables.get("ocrMatch"),
            "fixtureButtonClicked": state["clicked"],
            "buttonPressEvents": state["buttonPress"], "buttonReleaseEvents": state["buttonRelease"],
            "ocrClickInsideButton": state["clickInsideButton"],
            "foregroundTitle": state["foregroundTitle"],
            "cursorAfterClick": state["cursorAfterClick"],
            "error": state["error"] or (run.error if run and run.error else None),
            "coordinatesPersisted": False,
            "typedTextCaptured": False,
        }
        print(json.dumps(result, ensure_ascii=False, default=str))
        root.destroy()

    root.after(1200, execute)
    root.mainloop()
    return 0 if state["run"] and state["run"].status == "succeeded" and state["clicked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
