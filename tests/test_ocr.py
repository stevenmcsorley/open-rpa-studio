from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image

from openrpa import engine
from openrpa.engine import RunOptions, run_project
from openrpa.model import validate_workflow


def _project(root: Path, **activity_overrides):
    (root/"tiny.png").write_bytes(b"placeholder")
    project={"format":"openrpa.project","formatVersion":1,"name":"OCR","main":"Main","workflows":{"Main":"main.json"}}
    activity={"id":"ocr","type":"image_ocr","path":"tiny.png","language":"eng","pageSegmentationMode":3,"timeoutSeconds":10,"result":"recognized",**activity_overrides}
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"OCR","variables":[],"arguments":[],"activities":[activity]}
    (root/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    return project,workflow


def _valid_png(path: Path):
    image=Image.new("RGB",(120,50),"white")
    image.save(path)


def test_image_ocr_validates_runtime_parameters_and_safe_languages():
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"OCR","variables":[],"arguments":[],"activities":[{"id":"ocr","type":"image_ocr","path":"scan.png","language":"eng+osd","pageSegmentationMode":13,"timeoutSeconds":300}]}
    assert validate_workflow(workflow)==[]
    invalid={**workflow,"activities":[{**workflow["activities"][0],"language":"../../secret","pageSegmentationMode":14,"timeoutSeconds":301}]}
    assert {item["code"] for item in validate_workflow(invalid)}=={"ocr-language","ocr-psm","ocr-timeout"}


def test_image_ocr_executes_local_process_and_audits_without_exposing_text(tmp_path: Path,monkeypatch):
    project,_=_project(tmp_path);_valid_png(tmp_path/"tiny.png");events=[];audits=[];monkeypatch.setenv("OPENAI_API_KEY","private-test-secret")
    class CompletedProcess:
        returncode=0
        def __init__(self,*_args,**kwargs):
            assert "OPENAI_API_KEY" not in kwargs["env"]
            kwargs["stdout"].write("HELLO LOCAL OCR\n".encode())
        def poll(self):return self.returncode
        def wait(self,*_args,**_kwargs):return self.returncode
    monkeypatch.setattr(engine.shutil,"which",lambda _name:"tesseract")
    monkeypatch.setattr(engine.subprocess,"Popen",CompletedProcess)
    result=run_project(project,tmp_path,options=RunOptions(event=events.append,audit=lambda action,details:audits.append((action,details))))
    assert result.status=="succeeded",result.error
    assert result.variables["recognized"]=="HELLO LOCAL OCR\n"
    assert any(event.get("event")=="image-ocr-completed" and event["outputBytes"]==16 for event in events)
    assert [action for action,_ in audits if action.startswith("image.ocr.")]==["image.ocr.attempt","image.ocr.completed"]
    assert "HELLO LOCAL OCR" not in json.dumps(audits)


def test_image_ocr_fails_clearly_without_tesseract(tmp_path: Path,monkeypatch):
    project,_=_project(tmp_path);_valid_png(tmp_path/"tiny.png")
    monkeypatch.setattr(engine.shutil,"which",lambda _name:None)
    result=run_project(project,tmp_path)
    assert result.status=="failed" and result.error["code"]=="ocr-runtime"
    assert "install Tesseract" in result.error["message"]


def test_image_ocr_terminates_process_when_cancelled(tmp_path: Path,monkeypatch):
    project,_=_project(tmp_path);_valid_png(tmp_path/"tiny.png");processes=[];checks=0
    class RunningProcess:
        returncode=None
        terminated=False
        def __init__(self,*_args,**_kwargs):processes.append(self)
        def poll(self):return self.returncode
        def terminate(self):self.terminated=True;self.returncode=1
        def wait(self,*_args,**_kwargs):return self.returncode
    def cancel():
        nonlocal checks
        checks+=1
        return checks>=2
    monkeypatch.setattr(engine.shutil,"which",lambda _name:"tesseract")
    monkeypatch.setattr(engine.subprocess,"Popen",RunningProcess)
    result=run_project(project,tmp_path,options=RunOptions(cancel=cancel))
    assert result.status=="cancelled"
    assert len(processes)==1 and processes[0].terminated


def test_image_ocr_enforces_output_byte_quota(tmp_path: Path,monkeypatch):
    project,_=_project(tmp_path);_valid_png(tmp_path/"tiny.png");project["limits"]={"maxFileBytes":1024}
    class LargeOutputProcess:
        returncode=0
        def __init__(self,*_args,**kwargs):kwargs["stdout"].write(b"x"*1025)
        def poll(self):return None
        def terminate(self):self.returncode=1
        def wait(self,*_args,**_kwargs):return self.returncode
    monkeypatch.setattr(engine.shutil,"which",lambda _name:"tesseract")
    monkeypatch.setattr(engine.subprocess,"Popen",LargeOutputProcess)
    result=run_project(project,tmp_path)
    assert result.status=="failed" and result.error["code"]=="file-size-limit"


def test_image_ocr_enforces_pixel_quota_before_starting_tesseract(tmp_path: Path,monkeypatch):
    project,_=_project(tmp_path)
    class OversizedImage:
        format="PNG";size=(6000,6000)
        def __enter__(self):return self
        def __exit__(self,*_args):return None
        def verify(self):raise AssertionError("oversized image must be rejected before decoding")
    monkeypatch.setattr(Image,"open",lambda _path:OversizedImage())
    monkeypatch.setattr(engine.shutil,"which",lambda _name:"tesseract")
    result=run_project(project,tmp_path)
    assert result.status=="failed" and result.error["code"]=="ocr-pixel-limit"


def test_image_ocr_stops_process_at_configured_timeout(tmp_path: Path,monkeypatch):
    project,_=_project(tmp_path,timeoutSeconds=1);_valid_png(tmp_path/"tiny.png");processes=[];clock=0
    class SlowProcess:
        returncode=None
        def __init__(self,*_args,**_kwargs):processes.append(self)
        def poll(self):return self.returncode
        def terminate(self):self.returncode=1
        def wait(self,*_args,**_kwargs):return self.returncode
    def monotonic():
        nonlocal clock
        clock+=1
        return clock
    monkeypatch.setattr(engine.shutil,"which",lambda _name:"tesseract")
    monkeypatch.setattr(engine.subprocess,"Popen",SlowProcess)
    monkeypatch.setattr(engine.time,"monotonic",monotonic)
    result=run_project(project,tmp_path)
    assert result.status=="failed" and result.error["code"]=="ocr-timeout"
    assert len(processes)==1 and processes[0].returncode==1
