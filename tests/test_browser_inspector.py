from __future__ import annotations

import pytest

from openrpa.browser_inspector import BrowserInspector, build_control_descriptors
from openrpa.model import validate_workflow


def test_browser_inspector_builds_accessible_editable_action_descriptors():
    controls=build_control_descriptors([
        {"role":"button","name":"Save changes","tag":"button","matchCount":1},
        {"role":"textbox","name":"Work email","placeholder":"name@example.org","tag":"input","inputType":"email","matchCount":1},
        {"role":"link","name":"Continue","tag":"a","matchCount":2},
        {"role":"textbox","name":"","placeholder":"Search orders","tag":"input","inputType":"search","matchCount":1},
        {"role":"button","name":"","tag":"button","matchCount":1},
    ])
    assert controls==[
        {"selectorKind":"role","selector":"button:Save changes","role":"button","name":"Save changes","tag":"button","inputType":"","placeholder":"","matchCount":1,"actions":["click","read_text"]},
        {"selectorKind":"role","selector":"textbox:Work email","role":"textbox","name":"Work email","tag":"input","inputType":"email","placeholder":"name@example.org","matchCount":1,"actions":["fill"]},
        {"selectorKind":"role","selector":"link:Continue","role":"link","name":"Continue","tag":"a","inputType":"","placeholder":"","matchCount":2,"actions":["click","read_text"]},
        {"selectorKind":"placeholder","selector":"Search orders","role":"textbox","name":"","tag":"input","inputType":"search","placeholder":"Search orders","matchCount":1,"actions":["fill"]},
    ]


def test_browser_inspector_caps_candidates_to_three_hundred():
    controls=build_control_descriptors([{"role":"button","name":f"Button {i}","tag":"button"} for i in range(500)])
    assert len(controls)==300


def test_browser_inspector_rejects_local_and_credential_bearing_urls(monkeypatch):
    monkeypatch.setattr("openrpa.browser_inspector.assert_public_url",lambda url: (_ for _ in ()).throw(ValueError("blocked URL")) if "127.0.0.1" in url or "@" in url else None)
    inspector=BrowserInspector()
    with pytest.raises(ValueError,match="blocked URL"):
        inspector.open("http://127.0.0.1/admin")
    with pytest.raises(ValueError,match="blocked URL"):
        inspector.open("https://alice:secret@example.org/")


def test_bridge_requires_explicit_network_permission_and_audits_only_host(monkeypatch):
    import openrpa.bridge as bridge
    sent=[];audits=[]
    class Inspector:
        def open(self,url):return {"url":url,"title":"Example","status":200}
    class History:
        def audit(self,action,details):audits.append((action,details))
    monkeypatch.setattr(bridge,"browser_inspector",Inspector())
    monkeypatch.setattr(bridge,"history",History())
    monkeypatch.setattr(bridge,"send",sent.append)
    bridge.handle({"id":1,"method":"browser.inspect.open","params":{"url":"https://example.org/path?token=private","allowNetwork":False}})
    assert "explicit network permission" in sent[-1]["error"]["message"]
    bridge.handle({"id":2,"method":"browser.inspect.open","params":{"url":"https://example.org/path?token=private","allowNetwork":True}})
    assert sent[-1]["result"]["status"]==200
    assert audits==[("browser.inspector_open",{"host":"example.org","networkPermission":True})]
    assert "private" not in str(audits)


def test_real_chromium_snapshot_selectors_drive_engine_browser_activities():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<form><label for="email">Work email</label><input id="email"><button type="button" onclick="document.body.dataset.clicked='yes'">Save changes</button><select aria-label="Country"><option value="gb">United Kingdom</option><option value="us">United States</option></select><input type="checkbox" aria-label="Accept terms"></form><p role="status">Ready</p>''')
        inspector=BrowserInspector();inspector.page=page
        snapshot=inspector.controls()
        by_name={control["name"]:control for control in snapshot["controls"]}
        engine=object.__new__(WorkflowEngine);engine._browser_page=page
        click=by_name["Save changes"]
        engine._browser_activity({"id":"click","type":"browser_click","selectorKind":click["selectorKind"],"selector":click["selector"]},{})
        email=by_name["Work email"]
        engine._browser_activity({"id":"fill","type":"browser_fill","selectorKind":email["selectorKind"],"selector":email["selector"],"value":"robot@example.org"},{})
        country=by_name["Country"]
        engine._browser_activity({"id":"select","type":"browser_select","selectorKind":country["selectorKind"],"selector":country["selector"],"value":"us"},{})
        checkbox=by_name["Accept terms"]
        engine._browser_activity({"id":"check","type":"browser_check","selectorKind":checkbox["selectorKind"],"selector":checkbox["selector"]},{})
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Inspected actions","variables":[],"arguments":[],"activities":[
            {"id":"click","type":"browser_click","selectorKind":click["selectorKind"],"selector":click["selector"]},
            {"id":"fill","type":"browser_fill","selectorKind":email["selectorKind"],"selector":email["selector"],"value":"robot@example.org"},
            {"id":"select","type":"browser_select","selectorKind":country["selectorKind"],"selector":country["selector"],"value":"us"},
            {"id":"check","type":"browser_check","selectorKind":checkbox["selectorKind"],"selector":checkbox["selector"]},]}
        assert validate_workflow(workflow)==[]
        assert page.locator("body").get_attribute("data-clicked")=="yes"
        assert page.locator("#email").input_value()=="robot@example.org"
        assert page.locator("select").input_value()=="us"
        assert page.get_by_role("checkbox",name="Accept terms").is_checked()
        browser.close()


def test_real_chromium_recorder_captures_editable_selectors_without_field_values():
    playwright=pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context()
        page=context.new_page()
        page.set_content('''<form><label for="customer">Customer name</label><input id="customer" type="text"><label for="secret">Password</label><input id="secret" type="password"><label for="region">Region</label><select id="region"><option value="north">North</option><option value="south">South</option></select><button type="button">Save record</button></form>''')
        inspector=BrowserInspector();inspector.context=context;inspector.page=page
        inspector.start_recording()
        page.get_by_label("Customer name").fill("PRIVATE CUSTOMER VALUE")
        page.get_by_label("Password").fill("NEVER CAPTURE THIS")
        page.get_by_label("Region").select_option("south")
        page.get_by_role("button",name="Save record").click()
        result=inspector.stop_recording()
        encoded=str(result)
        assert result["recording"] is False
        assert [event["type"] for event in result["events"]]==["browser_fill","browser_select","browser_click"]
        assert result["events"][0]["selector"]=="textbox:Customer name"
        assert result["events"][1]["selector"]=="combobox:Region"
        assert "PRIVATE CUSTOMER VALUE" not in encoded
        assert "NEVER CAPTURE THIS" not in encoded
        assert "Password" not in encoded
        browser.close()


def test_recorder_carries_selector_only_events_across_page_navigation():
    playwright=pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context()
        context.route("https://record.test/**",lambda route:route.fulfill(status=200,content_type="text/html",body='<a href="/finish">Next page</a>' if route.request.url.endswith("/start") else '<button>Finish task</button>'))
        page=context.new_page();page.goto("https://record.test/start")
        inspector=BrowserInspector();inspector.context=context;inspector.page=page;inspector.start_recording()
        page.get_by_role("link",name="Next page").click()
        page.get_by_role("button",name="Finish task").click()
        result=inspector.stop_recording()
        assert [event["selector"] for event in result["events"]]==["link:Next page","button:Finish task"]
        browser.close()


def test_browser_workflow_validation_rejects_bad_or_ambiguous_configuration():
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Browser","variables":[],"arguments":[],"activities":[
        {"id":"fill","type":"browser_fill","selectorKind":"xpath","selector":"//input","value":"x","timeoutSeconds":121}]}
    codes={problem["code"] for problem in validate_workflow(workflow)}
    assert {"browser-selector-kind","browser-timeout"}<=codes
    workflow["activities"]=[{"id":"select","type":"browser_select","selectorKind":"role","selector":"combobox:Country","value":""}]
    assert any(problem["code"]=="browser-option-value" for problem in validate_workflow(workflow))
