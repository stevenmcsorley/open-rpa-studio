from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from openrpa import windows_uia
from openrpa.engine import RunOptions, run_project
from openrpa.model import validate_workflow


def _workflow():
    return {"format":"openrpa.workflow","formatVersion":1,"name":"OCR click","variables":[],"arguments":[],
            "activities":[{"id":"ocr-click","type":"desktop_ocr_click","windowTitle":"QA Window",
                           "processId":73,"text":"Continue safely","confidenceThreshold":80,
                           "timeoutSeconds":10,"result":"match"}]}


def _tsv(lines):
    output=io.StringIO()
    fields=["level","page_num","block_num","par_num","line_num","word_num","left","top","width","height","conf","text"]
    writer=csv.DictWriter(output,fieldnames=fields,delimiter="\t",lineterminator="\n")
    writer.writeheader()
    for line_num,words in enumerate(lines,1):
        for word_num,(text,left,confidence) in enumerate(words,1):
            writer.writerow({"level":5,"page_num":1,"block_num":1,"par_num":1,"line_num":line_num,
                             "word_num":word_num,"left":left,"top":20,"width":30,"height":12,
                             "conf":confidence,"text":text})
    return output.getvalue().encode()


def test_desktop_ocr_click_validates_scoping_and_limits():
    workflow=_workflow()
    assert validate_workflow(workflow)==[]
    activity=workflow["activities"][0]
    for field,value in (("windowTitle",""),("text",""),("confidenceThreshold",101),("timeoutSeconds",61),("processId",0)):
        invalid={**workflow,"activities":[{**activity,field:value}]}
        assert validate_workflow(invalid)


def test_ocr_click_matches_unique_line_and_clicks_only_inside_target(monkeypatch):
    class Window:
        element_info=SimpleNamespace(process_id=73)
        def set_focus(self): pass
        def rectangle(self): return SimpleNamespace(left=100,top=200,width=lambda:300,height=lambda:150)
    class Image:
        def save(self,buffer,format): buffer.write(b"png-bytes")
    clicks=[]
    fake_pyautogui=SimpleNamespace(screenshot=lambda **_kwargs:Image(),click=lambda x,y:clicks.append((x,y)))
    class Process:
        returncode=0
        def __init__(self,*_args,**_kwargs): pass
        def communicate(self,*_args,**_kwargs): return _tsv([[('Continue',20,94),('safely',55,92)]]),b""
    monkeypatch.setattr(windows_uia.sys,"platform","win32")
    monkeypatch.setattr(windows_uia,"_focus_ocr_window",lambda _window:None)
    monkeypatch.setattr(windows_uia,"_window",lambda *_args:Window())
    monkeypatch.setattr(windows_uia.shutil,"which",lambda _name:"tesseract.exe")
    monkeypatch.setitem(sys.modules,"pyautogui",fake_pyautogui)
    monkeypatch.setattr(windows_uia.subprocess,"Popen",Process)
    result=windows_uia.ocr_click("QA Window","Continue safely",80,10,73)
    assert result=={"matchCount":1,"confidence":93.0}
    assert clicks==[(152,226)]


def test_ocr_click_fails_closed_for_ambiguous_or_low_confidence(monkeypatch):
    class Window:
        element_info=SimpleNamespace(process_id=73)
        def set_focus(self): pass
        def rectangle(self): return SimpleNamespace(left=0,top=0,width=lambda:300,height=lambda:150)
    class Image:
        def save(self,buffer,format): buffer.write(b"png")
    clicks=[]
    monkeypatch.setattr(windows_uia.sys,"platform","win32")
    monkeypatch.setattr(windows_uia,"_focus_ocr_window",lambda _window:None)
    monkeypatch.setattr(windows_uia,"_window",lambda *_args:Window())
    monkeypatch.setattr(windows_uia.shutil,"which",lambda _name:"tesseract.exe")
    monkeypatch.setitem(sys.modules,"pyautogui",SimpleNamespace(screenshot=lambda **_kwargs:Image(),click=lambda *args:clicks.append(args)))

    class Process:
        returncode=0
        lines=[]
        def __init__(self,*_args,**_kwargs): pass
        def communicate(self,*_args,**_kwargs): return _tsv(self.lines),b""
    monkeypatch.setattr(windows_uia.subprocess,"Popen",Process)
    Process.lines=[[('Continue',10,90),('safely',45,90)],[('Continue',10,90),('safely',45,90)]]
    try:
        windows_uia.ocr_click("QA Window","Continue safely",80,10,73)
        assert False,"ambiguous OCR match should fail"
    except windows_uia.UIAutomationError as exc:
        assert "ambiguous" in str(exc)
    Process.lines=[[('Continue',10,40),('safely',45,45)]]
    try:
        windows_uia.ocr_click("QA Window","Continue safely",80,10,73)
        assert False,"low confidence OCR match should fail"
    except windows_uia.UIAutomationError as exc:
        assert "confidence threshold" in str(exc)
    assert clicks==[]


def test_ocr_click_fails_closed_if_window_moves_after_capture(monkeypatch):
    class Window:
        element_info=SimpleNamespace(process_id=73)
        calls=0
        def set_focus(self): pass
        def rectangle(self):
            self.calls+=1
            left=0 if self.calls==1 else 5
            return SimpleNamespace(left=left,top=0,width=lambda:300,height=lambda:150)
    window=Window()
    class Image:
        def save(self,buffer,format): buffer.write(b"png")
    clicks=[]
    class Process:
        returncode=0
        def __init__(self,*_args,**_kwargs): pass
        def communicate(self,*_args,**_kwargs): return _tsv([[('Continue',10,90),('safely',45,90)]]),b""
    monkeypatch.setattr(windows_uia.sys,"platform","win32")
    monkeypatch.setattr(windows_uia,"_focus_ocr_window",lambda _window:None)
    monkeypatch.setattr(windows_uia,"_window",lambda *_args:window)
    monkeypatch.setattr(windows_uia.shutil,"which",lambda _name:"tesseract.exe")
    monkeypatch.setitem(sys.modules,"pyautogui",SimpleNamespace(screenshot=lambda **_kwargs:Image(),click=lambda *args:clicks.append(args)))
    monkeypatch.setattr(windows_uia.subprocess,"Popen",Process)
    try:
        windows_uia.ocr_click("QA Window","Continue safely",80,10,73)
        assert False,"moving window should fail"
    except windows_uia.UIAutomationError as exc:
        assert "moved or resized" in str(exc)
    assert clicks==[]


def test_ocr_click_terminates_tesseract_when_cancelled(monkeypatch):
    class Window:
        element_info=SimpleNamespace(process_id=73)
        def set_focus(self): pass
        def rectangle(self): return SimpleNamespace(left=0,top=0,width=lambda:300,height=lambda:150)
    class Image:
        def save(self,buffer,format): buffer.write(b"png")
    class Process:
        returncode=None
        terminated=False
        def __init__(self,*_args,**_kwargs): pass
        def communicate(self,*_args,**_kwargs): raise windows_uia.subprocess.TimeoutExpired("tesseract",0.25)
        def terminate(self): self.terminated=True
        def wait(self,timeout=None): self.returncode=0
        def kill(self): self.returncode=-9
    process=None
    def create_process(*args,**kwargs):
        nonlocal process
        process=Process(*args,**kwargs)
        return process
    monkeypatch.setattr(windows_uia.sys,"platform","win32")
    monkeypatch.setattr(windows_uia,"_focus_ocr_window",lambda _window:None)
    monkeypatch.setattr(windows_uia,"_window",lambda *_args:Window())
    monkeypatch.setattr(windows_uia.shutil,"which",lambda _name:"tesseract.exe")
    monkeypatch.setitem(sys.modules,"pyautogui",SimpleNamespace(screenshot=lambda **_kwargs:Image(),click=lambda *_args:None))
    monkeypatch.setattr(windows_uia.subprocess,"Popen",create_process)
    checks=iter((False,True))
    try:
        windows_uia.ocr_click("QA Window","Continue safely",80,10,73,lambda:next(checks))
        assert False,"cancelled OCR should stop"
    except windows_uia.UIAutomationError as exc:
        assert "cancelled" in str(exc)
    assert process is not None and process.terminated


def test_ocr_focus_restores_and_verifies_the_exact_window(monkeypatch):
    import win32con
    import win32gui
    foreground={"handle":0,"restored":False}
    monkeypatch.setattr(win32gui,"IsWindow",lambda handle:handle==73)
    monkeypatch.setattr(win32gui,"IsIconic",lambda _handle:True)
    monkeypatch.setattr(win32gui,"ShowWindow",lambda handle,command:foreground.update(restored=(handle==73 and command==win32con.SW_RESTORE)))
    monkeypatch.setattr(win32gui,"GetForegroundWindow",lambda:foreground["handle"])
    monkeypatch.setattr(win32gui,"SetForegroundWindow",lambda handle:foreground.update(handle=handle))
    class Window:
        handle=73
        def set_focus(self):pass
    windows_uia._focus_ocr_window(Window())
    assert foreground=={"handle":73,"restored":True}


def test_ocr_focus_fails_closed_when_windows_denies_activation(monkeypatch):
    import win32gui
    foreground={"now":0.0}
    class Window:
        handle=73
        def set_focus(self):pass
    monkeypatch.setattr(win32gui,"IsWindow",lambda _handle:True)
    monkeypatch.setattr(win32gui,"IsIconic",lambda _handle:False)
    monkeypatch.setattr(win32gui,"GetForegroundWindow",lambda:0)
    monkeypatch.setattr(win32gui,"SetForegroundWindow",lambda _handle:False)
    monkeypatch.setattr(windows_uia.time,"monotonic",lambda:foreground["now"])
    monkeypatch.setattr(windows_uia.time,"sleep",lambda duration:foreground.update(now=foreground["now"]+duration))
    try:
        windows_uia._focus_ocr_window(Window())
        assert False,"OCR must refuse a click when the window is not foreground"
    except windows_uia.UIAutomationError as exc:
        assert "refusing to click" in str(exc)


def test_desktop_ocr_click_requires_per_run_desktop_permission(tmp_path: Path):
    workflow=_workflow()
    project={"format":"openrpa.project","formatVersion":1,"name":"OCR click","main":"Main","workflows":{"Main":"main.json"}}
    (tmp_path/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    denied=run_project(project,tmp_path,options=RunOptions(allow_desktop=False))
    assert denied.status=="failed"
    assert denied.error and denied.error.get("code")=="desktop-permission-denied"
