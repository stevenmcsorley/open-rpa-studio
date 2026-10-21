from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from openrpa.engine import RunOptions, WorkflowEngine, WorkflowError
from openrpa.model import validate_workflow


def test_browser_profile_schema_is_optional_and_bounded():
    def problems(profile_name):
        return validate_workflow({"format":"openrpa.workflow","formatVersion":1,"name":"Profile", "variables":[],"arguments":[],"activities":[
            {"id":"launch","type":"browser_launch","profileName":profile_name}
        ]})
    assert problems("")==[]
    assert problems("Work_Account-1")==[]
    assert any(item["code"]=="browser-profile-name" for item in problems("../outside"))
    assert any(item["code"]=="browser-profile-name" for item in problems("1bad"))
    assert any(item["code"]=="browser-profile-name" for item in problems("x"*41))


def _engine(root:Path,allow_desktop:bool):
    (root/"workflows").mkdir(exist_ok=True)
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","executionModel":"sequence","arguments":[],"variables":[],"activities":[]}
    (root/"workflows/main.workflow.json").write_text(json.dumps(workflow),encoding="utf-8")
    return WorkflowEngine({"format":"openrpa.project","formatVersion":1,"name":"Profile test","workflows":{"Main":"workflows/main.workflow.json"}},root,RunOptions(allow_desktop=allow_desktop))


def test_persistent_browser_profile_reuses_local_session_without_exporting_it(tmp_path:Path,monkeypatch):
    pytest.importorskip("playwright.sync_api")
    app_data=tmp_path/"app-data";monkeypatch.setenv("APPDATA",str(app_data))
    project=tmp_path/"project";project.mkdir()
    denied=_engine(project,False)
    with pytest.raises(WorkflowError,match="requires per-run desktop permission"):
        denied._browser_activity({"id":"launch","type":"browser_launch","headless":True,"profileName":"Work"},{})
    assert denied._browser_runtime is None
    assert not (app_data/"org.openrpa.studio"/"browser-profiles").exists()

    audit=[];events=[]
    first=_engine(project,True);first.options.audit=lambda action,details:audit.append((action,details));first.options.event=lambda event:events.append(event)
    first._browser_activity({"id":"launch","type":"browser_launch","headless":True,"profileName":"Work"},{},[])
    first._browser_context.add_cookies([{"name":"session","value":"authorized","domain":"example.com","path":"/","expires":int(time.time())+3600,"httpOnly":True,"secure":True}])
    profile_path=next((app_data/"org.openrpa.studio"/"browser-profiles").rglob("work"))
    assert profile_path.is_dir() and not profile_path.is_relative_to(project)
    first._close_browser()

    second=_engine(project,True)
    second._browser_activity({"id":"launch","type":"browser_launch","headless":True,"profileName":"Work"},{},[])
    try:
        cookies=second._browser_context.cookies("https://example.com")
        assert [(item["name"],item["value"]) for item in cookies]==[("session","authorized")]
    finally:second._close_browser()
    assert audit and audit[0][0]=="browser.profile_opened"
    assert set(audit[0][1])=={"activityId","profileId","browserType"}
    assert events and events[0]["event"]=="browser-profile-opened"
    assert "Work" not in json.dumps(audit+events) and "authorized" not in json.dumps(audit+events)
