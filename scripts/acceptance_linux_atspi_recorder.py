"""Live GTK/AT-SPI recorder check for Linux graphical sessions.

Run from a graphical Linux session with a user D-Bus session:
  dbus-run-session -- python3 scripts/acceptance_linux_atspi_recorder.py
"""
from __future__ import annotations

import json
import os
import sys
import ctypes
import ctypes.util
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from openrpa import linux_atspi
from openrpa.linux_atspi_recorder import LinuxATSPIDesktopRecorder


def main() -> int:
    # Use the Xwayland backend so the local XTest pointer injection below
    # targets the same display as the GTK fixture instead of WSLg Wayland.
    os.environ.setdefault("GDK_BACKEND","x11")
    try:
        import gi
        gi.require_version("Gtk","3.0")
        gi.require_version("Gdk","3.0")
        from gi.repository import Gdk, GLib, Gtk
    except Exception as exc:
        print(json.dumps({"status":"blocked","reason":f"GTK3 unavailable: {type(exc).__name__}: {exc}"}))
        return 2

    title="OpenRPA AT-SPI Recorder Acceptance"
    pid=os.getpid()
    recorder=LinuxATSPIDesktopRecorder()
    window=Gtk.Window(title=title)
    window.set_default_size(420,140)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin=18)
    label=Gtk.Label(label="Temporary local accessibility recorder check")
    button=Gtk.Button(label="Save fixture")
    box.pack_start(label,False,False,0)
    box.pack_start(button,False,False,0)
    window.add(box)
    state={"result":None,"error":None,"buttonClicked":0,"keyPressed":0}
    def on_button_clicked(_button):
        state["buttonClicked"]+=1
        label.set_text("Fixture button invoked")
    button.connect("clicked",on_button_clicked)
    def on_key_press(_window,_event):
        state["keyPressed"]+=1
        return False
    window.connect("key-press-event",on_key_press)

    def finish() -> bool:
        try:
            state["result"]=recorder.stop()
        except Exception as exc:
            state["error"]=f"stop failed: {type(exc).__name__}: {exc}"
        Gtk.main_quit()
        return GLib.SOURCE_REMOVE

    def invoke_button() -> bool:
        try:
            controls=linux_atspi.list_controls(title,pid)
            control=next((item for item in controls if item["name"]=="Save fixture"),None)
            if control is None or control["matchCount"]!=1:
                _,_,root=linux_atspi._window(title,pid)
                tree=[]
                for node in linux_atspi._walk(root):
                    if linux_atspi._interactive(linux_atspi._role(node)):
                        path=getattr(node,"path",None)
                        tree.append({"name":linux_atspi._name(node),"role":linux_atspi._role(node),"path":str(path)})
                raise RuntimeError(f"GTK fixture button was not uniquely accessible: controls={controls}; tree={tree}")
            translated=button.translate_coordinates(window,button.get_allocated_width()//2,button.get_allocated_height()//2)
            origin=window.get_window().get_origin()
            if len(translated)==3:
                ok,local_x,local_y=translated
            else:
                ok,local_x,local_y=True,*translated
            if len(origin)==3:
                origin_ok,origin_x,origin_y=origin
            else:
                origin_ok,origin_x,origin_y=True,*origin
            if not ok or not origin_ok:
                raise RuntimeError("Could not resolve the fixture button's screen position")
            display_name=ctypes.util.find_library("X11")
            xtst_name=ctypes.util.find_library("Xtst")
            if not display_name or not xtst_name:
                raise RuntimeError("X11 XTest is unavailable for a real local pointer acceptance")
            x11=ctypes.CDLL(display_name);xtst=ctypes.CDLL(xtst_name)
            x11.XOpenDisplay.restype=ctypes.c_void_p
            display=x11.XOpenDisplay(None)
            if not display:raise RuntimeError("Could not open the active X display")
            xtst.XTestFakeMotionEvent.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
            xtst.XTestFakeButtonEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
            x11.XFlush.argtypes=[ctypes.c_void_p]
            x11.XCloseDisplay.argtypes=[ctypes.c_void_p]
            x=origin_x+local_x;y=origin_y+local_y
            xtst.XTestFakeMotionEvent(display,-1,x,y,0)
            xtst.XTestFakeButtonEvent(display,1,1,0);x11.XFlush(display);time.sleep(.08)
            xtst.XTestFakeButtonEvent(display,1,0,0);x11.XFlush(display)
            time.sleep(.1)
            x11.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
            xtst.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
            return_keycode=x11.XKeysymToKeycode(display,0xff0d)
            xtst.XTestFakeKeyEvent(display,return_keycode,1,0);x11.XFlush(display);time.sleep(.05)
            xtst.XTestFakeKeyEvent(display,return_keycode,0,0);x11.XFlush(display)
            x11.XCloseDisplay(display)
            GLib.timeout_add(500,finish)
        except Exception as exc:
            state["error"]=f"AT-SPI invoke failed: {type(exc).__name__}: {exc}"
            GLib.timeout_add(0,finish)
        return GLib.SOURCE_REMOVE

    def start_recorder() -> bool:
        try:
            started=recorder.start(title,pid,record_keyboard=True)
            if not started.get("recording"):
                raise RuntimeError(f"recorder did not start: {started}")
            GLib.timeout_add(500,invoke_button)
        except Exception as exc:
            state["error"]=f"AT-SPI recorder failed to start: {type(exc).__name__}: {exc}"
            GLib.timeout_add(0,finish)
        return GLib.SOURCE_REMOVE

    window.show_all()
    GLib.timeout_add(800,start_recorder)
    Gtk.main()
    try:
        result=state["result"] or recorder.stop()
    finally:
        try:window.destroy()
        except Exception:pass
    expected={"type":"desktop_ui_invoke","windowTitle":title,"processId":pid,
              "name":"Save fixture","automationId":"","controlType":"Push Button","timeoutSeconds":10}
    expected_key={"type":"desktop_ui_press","windowTitle":title,"processId":pid,
                  "name":"Save fixture","automationId":"","controlType":"Push Button","key":"Enter"}
    passed=state["error"] is None and expected in result.get("events",[]) and expected_key in result.get("events",[])
    print(json.dumps({"status":"passed" if passed else "failed","error":state["error"],
                      "recordedEvents":result.get("events",[]),"eventCount":len(result.get("events",[])),
                      "ignoredEvents":result.get("ignoredClicks"),"ignoredKeys":result.get("ignoredKeys"),"fixtureButtonClicked":state["buttonClicked"],"fixtureKeyPressed":state["keyPressed"],
                      "typedTextCaptured":False},ensure_ascii=False))
    return 0 if passed else 1


if __name__=="__main__":
    raise SystemExit(main())
