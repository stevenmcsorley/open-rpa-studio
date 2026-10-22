from __future__ import annotations

import time
from pathlib import Path

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
        {"selectorKind":"role","selector":"button:Save changes","role":"button","name":"Save changes","tag":"button","inputType":"","placeholder":"","matchCount":1,"actions":["click","hover","read_text"]},
        {"selectorKind":"role","selector":"textbox:Work email","role":"textbox","name":"Work email","tag":"input","inputType":"email","placeholder":"name@example.org","matchCount":1,"actions":["fill"]},
        {"selectorKind":"role","selector":"link:Continue","role":"link","name":"Continue","tag":"a","inputType":"","placeholder":"","matchCount":2,"actions":["click","hover","read_text"]},
        {"selectorKind":"placeholder","selector":"Search orders","role":"textbox","name":"","tag":"input","inputType":"search","placeholder":"Search orders","matchCount":1,"actions":["fill"]},
    ]


def test_browser_inspector_offers_select_many_for_accessible_aria_listbox():
    controls=build_control_descriptors([{"role":"listbox","name":"Topics","tag":"div","ariaMultiselectable":True,"matchCount":1}])
    assert controls[0]["actions"][0]=="select_many"
    assert controls[0]["ariaMultiselectable"] is True


def test_browser_inspector_caps_candidates_to_three_hundred():
    controls=build_control_descriptors([{"role":"button","name":f"Button {i}","tag":"button"} for i in range(500)])
    assert len(controls)==300


def test_live_browser_multiple_select_is_discovered_verified_and_value_free():
    playwright=pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<label for="categories">Categories</label><select id="categories" multiple><option value="books">Books</option><option value="music">Music</option><option value="synths">Synths</option></select><label for="single">Country</label><select id="single"><option value="gb">UK</option><option value="us">US</option></select><div role="listbox" aria-label="Topics" aria-multiselectable="true"><div role="option" aria-selected="false">Research</div><div role="option" aria-selected="false">Engineering</div></div><script>document.querySelectorAll('[role=option]').forEach(option=>option.addEventListener('click',()=>option.setAttribute('aria-selected',option.getAttribute('aria-selected')==='true'?'false':'true')))</script>''')
        inspector=BrowserInspector();inspector.page=page
        controls={item["name"]:item for item in inspector.controls()["controls"]}
        assert "select_many" in controls["Categories"]["actions"] and controls["Categories"]["multiple"] is True
        assert "select_many" in controls["Topics"]["actions"] and controls["Topics"]["ariaMultiselectable"] is True
        assert "select_many" not in controls["Country"]["actions"]
        result=inspector.act("select_many",selector_kind="role",selector="listbox:Categories",values=["books","synths"])
        assert result["selectedCount"]==2
        assert page.locator("#categories option:checked").evaluate_all("items => items.map(item => item.value)")==["books","synths"]
        topics=inspector.act("select_many",selector_kind="role",selector="listbox:Topics",values=["Research","Engineering"])
        assert topics["selectedCount"]==2
        assert page.get_by_role("option").evaluate_all("items => items.filter(item=>item.getAttribute('aria-selected')==='true').map(item=>item.innerText)")==["Research","Engineering"]
        assert "books" not in str(result) and "synths" not in str(result)
        with pytest.raises(RuntimeError,match="accessible ARIA listbox"):
            inspector.act("select_many",selector_kind="label",selector="Country",values=["us"])
        with pytest.raises(ValueError,match="unique"):
            inspector.act("select_many",selector_kind="label",selector="Categories",values=["books","books"])
        browser.close()


def test_browser_screenshot_enforces_visible_viewport_and_payload_limits():
    from types import SimpleNamespace
    inspector=BrowserInspector()
    inspector.page=SimpleNamespace(is_closed=lambda:False,screenshot=lambda **_kwargs:b"\xff\xd8\xff"+b"x"*700_000)
    with pytest.raises(RuntimeError,match="700,000-byte"):
        inspector.screenshot()
    inspector.page=SimpleNamespace(is_closed=lambda:True)
    with pytest.raises(RuntimeError,match="Open a page"):
        inspector.screenshot()


def test_browser_select_many_activity_executes_and_validates_returned_values():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    from openrpa.model import validate_workflow
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('<label for="categories">Categories</label><select id="categories" multiple><option value="books">Books</option><option value="music">Music</option><option value="synths">Synths</option></select><label for="country">Country</label><select id="country"><option value="gb">UK</option></select>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions();engine._run_started=time.monotonic();engine._max_run_seconds=300
        activity={"id":"select","type":"browser_select_many","selectorKind":"label","selector":"Categories","values":["{{ requested }}","synths"],"result":"chosen"}
        values={"requested":"books"};logs=[]
        engine._browser_activity(activity,values,logs)
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Select many","variables":[],"arguments":[],"activities":[{"id":"select","type":"browser_select_many","selectorKind":"label","selector":"Categories","values":["books","synths"],"result":"chosen"}]}
        assert validate_workflow(workflow)==[]
        assert values["chosen"]==["books","synths"]
        assert page.locator("#categories option:checked").evaluate_all("items => items.map(item => item.value)")==["books","synths"]
        assert logs[-1]=={"event":"browser-select-many-complete","activityId":"select","selectedCount":2}
        with pytest.raises(Exception,match="accessible ARIA listbox"):
            engine._browser_activity({**activity,"selector":"Country","selectorKind":"label","values":["gb"]}, {"requested":"books"})
        browser.close()


def test_browser_select_many_activity_supports_custom_aria_listbox_and_replaces_selection():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<div role="listbox" aria-label="Topics" aria-multiselectable="true">
          <div role="option" aria-selected="true">Books</div>
          <div role="option" aria-selected="false">Music</div>
          <div role="option" aria-selected="false" aria-label="Synths">Synth collection</div>
        </div><script>
          document.querySelectorAll('[role=option]').forEach(option=>option.addEventListener('click',()=>option.setAttribute('aria-selected',option.getAttribute('aria-selected')==='true'?'false':'true')));
        </script>''')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions();engine._run_started=time.monotonic();engine._max_run_seconds=300
        activity={"id":"select-aria","type":"browser_select_many","selectorKind":"role","selector":"listbox:Topics","values":["Music","Synths"],"result":"chosen"}
        values={};logs=[]
        engine._browser_activity(activity,values,logs)
        selected=page.get_by_role("option").evaluate_all("items => items.filter(item=>item.getAttribute('aria-selected')==='true').map(item=>item.getAttribute('aria-label')||item.innerText)")
        assert set(selected)=={"Music","Synths"}
        assert set(values["chosen"])=={"Music","Synths"}
        assert logs[-1]=={"event":"browser-select-many-complete","activityId":"select-aria","selectedCount":2}
        browser.close()


def test_live_browser_snapshot_and_actions_are_bounded_and_value_free():
    playwright=pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<title>Local browser QA</title><main style="min-height:4000px"><h1>Automation sandbox</h1><label for="customer">Customer</label><input id="customer"><label for="password">Password</label><input id="password" type="password"><label for="card">Card number</label><input id="card" name="card-number"><button type="button" onclick="document.body.dataset.saved='yes'">Save</button><p>Visible content for inspection.</p></main>''')
        inspector=BrowserInspector();inspector.page=page
        snapshot=inspector.snapshot(1000)
        assert snapshot["title"]=="Local browser QA"
        assert "Visible content for inspection." in snapshot["text"]
        assert snapshot["contentWarning"] and any(item["name"]=="Customer" for item in snapshot["controls"])
        screenshot=inspector.screenshot()
        assert screenshot.startswith(b"\xff\xd8\xff") and len(screenshot)<=700_000
        result=inspector.act("fill",selector_kind="role",selector="textbox:Customer",value="private example")
        assert result["action"]=="fill" and "private example" not in str(result)
        inspector.act("click",selector_kind="role",selector="button:Save")
        assert page.locator("body").get_attribute("data-saved")=="yes"
        page.evaluate("window.addEventListener('wheel', event => document.body.dataset.lastWheel=String(event.deltaY))")
        page.mouse.move(300,300)
        scrolled=inspector.act("scroll",direction="up",distance_px=200,delay_ms=0)
        page.wait_for_timeout(100)
        assert scrolled["direction"]=="up" and scrolled["distancePx"]==200
        assert page.locator("body").get_attribute("data-last-wheel")=="-200"
        with pytest.raises(RuntimeError,match="password"):
            inspector.act("fill",selector_kind="role",selector="textbox:Password",value="must not be sent")
        with pytest.raises(RuntimeError,match="payment-card"):
            inspector.act("fill",selector_kind="role",selector="textbox:Card number",value="must not be sent")
        page.set_content('<button>Duplicate</button><button>Duplicate</button>')
        with pytest.raises(RuntimeError,match="exactly one"):
            inspector.act("click",selector_kind="role",selector="button:Duplicate")
        inspector.close();browser.close()


def test_browser_inspector_rejects_local_and_credential_bearing_urls(monkeypatch):
    monkeypatch.setattr("openrpa.browser_inspector.assert_public_url",lambda url: (_ for _ in ()).throw(ValueError("blocked URL")) if "127.0.0.1" in url or "@" in url else None)
    inspector=BrowserInspector()
    with pytest.raises(ValueError,match="blocked URL"):
        inspector.open("http://127.0.0.1/admin")
    with pytest.raises(ValueError,match="blocked URL"):
        inspector.open("https://alice:secret@example.org/")


def test_browser_inspector_launches_the_requested_browser_visibly(monkeypatch):
    import playwright.sync_api
    launched=[]
    class Page:
        url="https://example.org/"
        def set_default_timeout(self,value):pass
        def set_default_navigation_timeout(self,value):pass
        def goto(self,*_args,**_kwargs):return type("Response",(),{"status":200})()
        def title(self):return "Example"
    class Context:
        def route(self,*_args):pass
        def new_page(self):return Page()
    class Browser:
        def new_context(self,**_kwargs):return Context()
        def close(self):pass
    class Firefox:
        def launch(self,**kwargs):launched.append(kwargs);return Browser()
    class Runtime:
        firefox=Firefox()
        def stop(self):pass
    monkeypatch.setattr(playwright.sync_api,"sync_playwright",lambda:type("Starter",(),{"start":lambda self:Runtime()})())
    inspector=BrowserInspector()
    assert inspector.open("https://example.org/","firefox")=={"url":"https://example.org/","title":"Example","status":200}
    assert launched==[{"headless":False}]
    inspector.close()


def test_bridge_requires_explicit_network_permission_and_audits_only_host(monkeypatch):
    import openrpa.bridge as bridge
    sent=[];audits=[]
    class Inspector:
        def open(self,url,*args):return {"url":url,"title":"Example","status":200}
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


def test_bridge_browser_runtime_probe_does_not_require_or_use_network_and_audits_selection(monkeypatch):
    import openrpa.bridge as bridge
    from openrpa import browser_runtime
    sent=[];audits=[]
    class History:
        def audit(self,action,details):audits.append((action,details))
    monkeypatch.setattr(bridge,"history",History())
    monkeypatch.setattr(bridge,"send",sent.append)
    monkeypatch.setattr(browser_runtime,"probe",lambda browser_type,channel,path:{"browserType":browser_type,"channel":channel,"version":"Test Browser","networkUsed":"false"})
    bridge.handle({"id":3,"method":"browser.inspect.probe","params":{"browserType":"chromium","channel":"msedge","executablePath":"C:\\private\\edge.exe"}})
    assert sent[-1]["result"]["version"]=="Test Browser"
    assert audits==[("browser.runtime_probe",{"browserType":"chromium","channel":"msedge","success":True,"networkUsed":False})]
    assert "private" not in str(audits)


def test_real_chromium_snapshot_selectors_drive_engine_browser_activities():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<form><label for="email">Work email</label><input id="email"><button type="button" onclick="document.body.dataset.clicked='yes'">Save changes</button><select aria-label="Country"><option value="gb">United Kingdom</option><option value="us">United States</option></select><input type="checkbox" aria-label="Accept terms"></form><p role="status">Ready</p>''')
        inspector=BrowserInspector();inspector.page=page
        snapshot=inspector.controls()
        by_name={control["name"]:control for control in snapshot["controls"]}
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions()
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


def test_browser_launch_accepts_installed_browser_channel(monkeypatch):
    import playwright.sync_api
    from openrpa.engine import RunOptions,WorkflowEngine
    launched=[]
    class Page:
        def set_default_timeout(self,value): pass
        def set_default_navigation_timeout(self,value): pass
        def route(self,*args): pass
        def on(self,*args): pass
    class Context:
        def new_page(self): return Page()
        def on(self,*_args): pass
    class Browser:
        def new_context(self): return Context()
    class Chromium:
        def launch(self,**kwargs): launched.append(kwargs);return Browser()
    class Runtime:
        chromium=Chromium()
        def stop(self): pass
    monkeypatch.setattr(playwright.sync_api,"sync_playwright",lambda: type("Starter",(),{"start":lambda self:Runtime()})())
    engine=object.__new__(WorkflowEngine);engine._browser_page=None;engine._browser_runtime=None;engine._browser=None;engine._browser_context=None
    engine._browser_activity({"id":"launch","type":"browser_launch","channel":"chrome","headless":True},{})
    assert launched==[{"headless":True,"channel":"chrome"}]


def test_browser_launch_uses_requested_firefox_engine_and_visible_default(monkeypatch):
    import playwright.sync_api
    from openrpa.activity_catalog import ACTIVITY_CATALOG
    from openrpa.engine import WorkflowEngine
    launched=[]
    class Page:
        def set_default_timeout(self,value):pass
        def set_default_navigation_timeout(self,value):pass
        def route(self,*args):pass
        def on(self,*args):pass
    class Context:
        def new_page(self):return Page()
        def on(self,*_args):pass
    class Browser:
        def new_context(self):return Context()
    class Firefox:
        def launch(self,**kwargs):launched.append(kwargs);return Browser()
    class Runtime:
        firefox=Firefox()
        def stop(self):pass
    monkeypatch.setattr(playwright.sync_api,"sync_playwright",lambda:type("Starter",(),{"start":lambda self:Runtime()})())
    engine=object.__new__(WorkflowEngine);engine._browser_page=None;engine._browser_runtime=None;engine._browser=None;engine._browser_context=None
    engine._browser_activity({"id":"launch","type":"browser_launch","browserType":"firefox"},{})
    default=next(item for item in ACTIVITY_CATALOG if item["type"]=="browser_launch")["defaults"]
    assert launched==[{"headless":False}]
    assert default["headless"] is False


def test_real_chromium_recorder_captures_editable_selectors_without_field_values():
    playwright=pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context()
        page=context.new_page()
        page.set_content('''<form><label for="customer">Customer name</label><input id="customer" data-testid="customer-entry" type="text"><label for="secret">Password</label><input id="secret" type="password"><label for="region">Region</label><select id="region"><option value="north">North</option><option value="south">South</option></select><button type="button">Save record</button></form>''')
        inspector=BrowserInspector();inspector.context=context;inspector.page=page
        inspector.start_recording()
        page.get_by_label("Customer name").fill("PRIVATE CUSTOMER VALUE")
        page.get_by_label("Customer name").press("Enter")
        page.get_by_label("Password").fill("NEVER CAPTURE THIS")
        page.get_by_label("Region").select_option("south")
        page.get_by_role("button",name="Save record").hover()
        page.get_by_role("button",name="Save record").click()
        result=inspector.stop_recording()
        encoded=str(result)
        assert result["recording"] is False
        assert [event["type"] for event in result["events"]]==["browser_press","browser_fill","browser_select","browser_hover","browser_click"]
        assert result["events"][0]["selector"]=="textbox:Customer name"
        assert result["events"][0]["key"]=="Enter"
        assert result["events"][2]["selector"]=="combobox:Region"
        assert result["events"][1]["selectorFallbacks"]==[{"selectorKind":"test_id","selector":"customer-entry","exact":True}]
        assert "PRIVATE CUSTOMER VALUE" not in encoded
        assert "NEVER CAPTURE THIS" not in encoded
        assert "Password" not in encoded
        browser.close()


def test_browser_recording_event_accepts_supported_selector_kinds_and_filters_invalid_fallbacks():
    inspector=BrowserInspector();inspector._recording=True
    inspector._capture_recording_event(None,{"type":"browser_click","selectorKind":"css","selector":"#save","selectorFallbacks":[{"selectorKind":"label","selector":"Save"}]})
    inspector._capture_recording_event(None,{"type":"browser_click","selectorKind":"css","selector":"#bad","selectorFallbacks":[{"selectorKind":"xpath","selector":"//button"}]})
    assert inspector._recorded_events==[{"type":"browser_click","selectorKind":"css","selector":"#save","selectorFallbacks":[{"selectorKind":"label","selector":"Save","exact":True}]}]


def test_recorded_browser_selector_fallback_recovers_from_changed_accessible_name():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine,RunOptions
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context();page=context.new_page()
        page.set_content('<label for="customer">Customer name</label><input id="customer" data-testid="customer-entry">')
        inspector=BrowserInspector();inspector.context=context;inspector.page=page;inspector.start_recording()
        page.get_by_label("Customer name").fill("value is intentionally not recorded")
        page.get_by_label("Customer name").press("Tab")
        recorded=inspector.stop_recording()["events"]
        assert any(event["type"]=="browser_fill" for event in recorded),recorded
        fill=next(event for event in recorded if event["type"]=="browser_fill")
        assert "value" not in fill
        page.set_content('<label for="customer">Account holder</label><input id="customer" data-testid="customer-entry">')
        audits=[];logs=[]
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions(audit=lambda action,details:audits.append((action,details)))
        activity={**fill,"id":"recorded-fill","value":"reviewed input"}
        engine._browser_activity(activity,{},logs)
        assert page.get_by_test_id("customer-entry").input_value()=="reviewed input"
        assert audits==[("browser.selector_fallback",{"activityId":"recorded-fill","fallbackIndex":0})]
        assert logs==[{"event":"browser-selector-fallback","activityId":"recorded-fill","fallbackIndex":0}]
        assert "customer-entry" not in str(audits+logs)
        browser.close()


def test_browser_hover_and_press_execute_and_validate_against_real_dom():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<input aria-label="Search"><button aria-label="Menu" onmouseover="document.body.dataset.hovered='yes'">Menu</button>''')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set()
        engine._browser_activity({"id":"hover","type":"browser_hover","selectorKind":"role","selector":"button:Menu"},{})
        engine._browser_activity({"id":"press","type":"browser_press","selectorKind":"label","selector":"Search","key":"Enter"},{})
        assert page.locator("body").get_attribute("data-hovered")=="yes"
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Browser keyboard","variables":[],"arguments":[],"activities":[
            {"id":"hover","type":"browser_hover","selectorKind":"role","selector":"button:Menu"},
            {"id":"press","type":"browser_press","selectorKind":"label","selector":"Search","key":"Enter"}]}
        assert validate_workflow(workflow)==[]
        workflow["activities"][1]["key"]="type=secret"
        assert "browser-key" in {item["code"] for item in validate_workflow(workflow)}
        browser.close()


def test_browser_engine_tracks_named_tabs_and_captures_popups():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context()
        page=context.new_page()
        engine=object.__new__(WorkflowEngine)
        engine._browser_context=context;engine._browser=browser;engine._browser_page=page
        engine._browser_tabs={};engine._browser_unclaimed_popups=[];engine._browser_popup_counter=0
        engine._secret_values=set();engine.options=RunOptions();engine._run_started=time.monotonic();engine._max_run_seconds=60
        engine._register_browser_page(page,"main")
        context.on("page",engine._on_browser_popup)
        page.set_content('''<button onclick="window.open('about:blank','sign-in')">Open sign-in</button>''')
        engine._browser_activity({"id":"open-popup","type":"browser_click","selectorKind":"role","selector":"button:Open sign-in"},{})
        engine._browser_activity({"id":"capture","type":"browser_capture_popup","name":"sign_in","timeoutSeconds":1},{})
        assert engine._browser_page is engine._browser_tabs["sign_in"]
        engine._browser_page.set_content("<h1>Sign-in window</h1>")
        values={}
        engine._browser_activity({"id":"read-popup","type":"browser_text","selectorKind":"role","selector":"heading:Sign-in window","result":"popupText"},values)
        assert values["popupText"]=="Sign-in window"
        engine._browser_activity({"id":"details","type":"browser_new_tab","name":"details"},{})
        engine._browser_page.set_content("<h1>Product details</h1>")
        engine._browser_activity({"id":"main","type":"browser_switch_tab","name":"main"},{})
        assert engine._browser_page is page
        engine._browser_activity({"id":"close-details","type":"browser_close_tab","name":"details"},{})
        engine._browser_activity({"id":"close-popup","type":"browser_close_tab","name":"sign_in"},{})
        with pytest.raises(Exception,match="last browser tab"):
            engine._browser_activity({"id":"close-main","type":"browser_close_tab","name":"main"},{})
        browser.close()


def test_browser_response_wait_captures_recent_metadata_without_body_or_query():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine,WorkflowError
    from urllib.parse import urlsplit
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context();page=context.new_page();audits=[]
        engine=object.__new__(WorkflowEngine)
        engine._browser_context=context;engine._browser=browser;engine._browser_page=page
        engine._browser_tabs={};engine._browser_unclaimed_popups=[];engine._browser_popup_counter=0;engine._browser_responses={}
        engine._secret_values=set();engine.options=RunOptions(allow_network=True,audit=lambda action,details:audits.append((action,details)))
        engine._run_started=time.monotonic();engine._max_run_seconds=20
        engine._register_browser_page(page,"main")
        def fulfill(route):
            parts=urlsplit(route.request.url)
            if parts.path=="/api/orders":
                route.fulfill(status=201,content_type="application/json",body='{"private":"SECRET RESPONSE BODY"}')
            else:
                route.fulfill(status=200,content_type="text/html",body="<main>Response test</main>")
        page.route("**/*",fulfill)
        page.goto("https://example.com/")
        page.evaluate("fetch('/api/orders?token=private-query').then(response => response.text())")
        variables={};logs=[]
        engine._browser_activity({"id":"wait-api","type":"browser_wait_response","urlContains":"/api/orders","method":"GET","status":201,"timeoutSeconds":2,"result":"apiResult"},variables,logs)
        assert variables["apiResult"]=={"method":"GET","status":201,"contentType":"application/json"}
        assert "SECRET RESPONSE BODY" not in str(variables)
        assert "private-query" not in str(variables)
        assert "private-query" not in str(logs)
        assert audits==[("browser.response.observed",{"activityId":"wait-api","method":"GET","status":201,"contentType":"application/json"})]
        with pytest.raises(WorkflowError,match="network permission"):
            engine.options.allow_network=False
            engine._browser_activity({"id":"denied","type":"browser_wait_response","urlContains":"/api/orders"}, {}, [])
        browser.close()


def test_browser_response_wait_maps_only_explicit_bounded_json_fields():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    from urllib.parse import urlsplit
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context();page=context.new_page();audits=[]
        engine=object.__new__(WorkflowEngine)
        engine._browser_context=context;engine._browser=browser;engine._browser_page=page
        engine._browser_tabs={};engine._browser_unclaimed_popups=[];engine._browser_popup_counter=0;engine._browser_responses={}
        engine._secret_values=set();engine.options=RunOptions(allow_network=True,audit=lambda action,details:audits.append((action,details)))
        engine._run_started=time.monotonic();engine._max_run_seconds=20
        engine._register_browser_page(page,"main")
        body='{"data":{"items":[{"id":"O-1","title":"First","private":"HIDDEN BODY VALUE"},{"id":"O-2","title":"Second","private":"OTHER HIDDEN VALUE"}]}}'
        def fulfill(route):
            if urlsplit(route.request.url).path=="/api/orders":route.fulfill(status=200,content_type="application/json",body=body)
            else:route.fulfill(status=200,content_type="text/html",body="<main>Response mapping</main>")
        page.route("**/*",fulfill);page.goto("https://example.com/")
        page.evaluate("fetch('/api/orders?access_token=private').then(response => response.json())")
        mapping={"itemsPointer":"/data/items","result":"orders","maxItems":10,"fields":[{"name":"id","path":"/id"},{"name":"title","path":"/title"}]}
        variables={};logs=[]
        engine._browser_activity({"id":"wait-json","type":"browser_wait_response","urlContains":"/api/orders","method":"GET","status":200,"timeoutSeconds":2,"maxResponseBytes":10000,"result":"metadata","jsonMapping":mapping},variables,logs)
        assert variables["metadata"]=={"method":"GET","status":200,"contentType":"application/json"}
        assert variables["orders"]==[{"id":"O-1","title":"First"},{"id":"O-2","title":"Second"}]
        assert "HIDDEN BODY VALUE" not in str(variables) and "OTHER HIDDEN VALUE" not in str(variables)
        assert "private" not in str(variables) and "private" not in str(logs)
        assert logs[-1]["mappedItems"]==2 and logs[-1]["mappedFields"]==2
        assert audits==[("browser.response.observed",{"activityId":"wait-json","method":"GET","status":200,"contentType":"application/json"})]
        browser.close()


def test_browser_response_schema_discovery_returns_bounded_shape_without_values():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    from urllib.parse import urlsplit
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context();page=context.new_page()
        engine=object.__new__(WorkflowEngine)
        engine._browser_context=context;engine._browser=browser;engine._browser_page=page
        engine._browser_tabs={};engine._browser_unclaimed_popups=[];engine._browser_popup_counter=0;engine._browser_responses={}
        engine._secret_values=set();engine.options=RunOptions(allow_network=True)
        engine._run_started=time.monotonic();engine._max_run_seconds=20
        engine._register_browser_page(page,"main")
        body='{"data":{"items":[{"id":"PRIVATE-ORDER-1","label":"Hidden value one","active":true,"details":{"total":10}},{"id":"PRIVATE-ORDER-2","label":"Hidden value two","active":false,"details":{"total":20}}],"count":2}}'
        def fulfill(route):
            if urlsplit(route.request.url).path=="/api/orders":route.fulfill(status=200,content_type="application/json",body=body)
            else:route.fulfill(status=200,content_type="text/html",body="<main>Schema discovery</main>")
        page.route("**/*",fulfill);page.goto("https://example.com/")
        page.evaluate("fetch('/api/orders?access_token=private').then(response => response.json())")
        variables={};logs=[]
        engine._browser_activity({"id":"inspect-json","type":"browser_wait_response","urlContains":"/api/orders","method":"GET","status":200,"timeoutSeconds":2,"maxResponseBytes":10000,"result":"metadata","discoverJsonSchema":True,"schemaResult":"responseShape"},variables,logs)
        shape=variables["responseShape"]
        assert shape["objectArrayPointers"]==["/data/items"]
        assert shape["schema"]["properties"]["data"]["properties"]["items"]["items"]["properties"]["details"]["properties"]["total"]=={"type":"number"}
        assert shape["truncated"] is False
        assert "PRIVATE-ORDER-1" not in str(variables) and "Hidden value one" not in str(variables)
        assert "PRIVATE-ORDER-1" not in str(logs) and "private" not in str(logs)
        assert logs[-1]["schemaDiscovered"] is True and logs[-1]["schemaObjectArrays"]==1
        browser.close()


def test_json_shape_inspection_enforces_depth_property_and_node_caps():
    from openrpa.engine import _inspect_json_shape
    payload={f"field{index}":index for index in range(55)}
    payload["nested"]={"level1":{"level2":{"level3":{"level4":{"level5":{"leaf":"value"}}}}}}
    result=_inspect_json_shape(payload,max_depth=3,max_properties=10,max_nodes=8)
    assert result["truncated"] is True
    assert len(result["schema"]["properties"])==10
    assert all("value" not in str(result) for value in payload.values())


def test_json_shape_discovery_marks_sample_optional_fields_and_preserves_type_variants():
    from openrpa.engine import _inspect_json_shape
    result=_inspect_json_shape({"rows":[{"id":"A-1","amount":12,"metadata":{"active":True}},{"id":2,"metadata":{"active":False},"note":"optional"}]})
    items=result["schema"]["properties"]["rows"]["items"]
    assert items["presentInAllSamples"]==["id","metadata"]
    assert items["properties"]["id"]=={"type":"mixed","alternatives":[{"type":"number"},{"type":"string"}]}
    assert items["properties"]["note"]=={"type":"string"}
    assert result["objectArrayPointers"]==["/rows"]


def test_browser_json_mapping_fails_closed_before_reading_unbounded_or_compressed_bodies():
    from openrpa.engine import WorkflowEngine
    from openrpa.model import WorkflowError
    class FakeResponse:
        def __init__(self,headers):self.headers=headers;self.read=False
        def header_value(self,name):return self.headers.get(name)
        def body(self):self.read=True;return b'{"items":[]}'
    engine=object.__new__(WorkflowEngine);engine._check_cancel=lambda:None
    mapping={"itemsPointer":"/items","result":"items","maxItems":10,"fields":[{"name":"id","path":"/id"}]}
    activity={"id":"map","maxResponseBytes":100}
    base={"status":200,"contentType":"application/json"}
    unknown=FakeResponse({"content-type":"application/json"})
    with pytest.raises(WorkflowError,match="Content-Length"):
        engine._map_browser_json_response({**base,"_response":unknown,"_bodyUnavailable":"size-unknown"},mapping,activity)
    assert unknown.read is False
    oversized=FakeResponse({"content-length":"101","content-encoding":"identity"})
    with pytest.raises(WorkflowError,match="declares 101 bytes"):
        engine._map_browser_json_response({**base,"_response":oversized},mapping,activity)
    assert oversized.read is False
    compressed=FakeResponse({"content-length":"12","content-encoding":"gzip"})
    with pytest.raises(WorkflowError,match="uncompressed"):
        engine._map_browser_json_response({**base,"_response":compressed},mapping,{**activity,"maxResponseBytes":100})
    assert compressed.read is False


def test_browser_response_wait_schema_and_execution_plan_require_network_permission():
    from openrpa.model import validate_workflow
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Response","variables":[],"arguments":[]}
    valid={**base,"activities":[{"id":"response","type":"browser_wait_response","urlContains":"/api/orders","method":"GET","status":201,"result":"apiResult"}]}
    assert validate_workflow(valid)==[]
    mapping={"itemsPointer":"/data/items","result":"items","maxItems":100,"fields":[{"name":"id","path":"/id"}]}
    mapped={**base,"activities":[{"id":"response","type":"browser_wait_response","urlContains":"/api/orders","result":"metadata","jsonMapping":mapping,"maxResponseBytes":500000}]}
    assert validate_workflow(mapped)==[]
    for invalid in ({"urlContains":"/api/orders?token=secret"},{"urlContains":"/api/orders","method":"GTE"},{"urlContains":"/api/orders","status":99},{"urlContains":"/api/orders","result":"not valid"}):
        workflow={**base,"activities":[{"id":"response","type":"browser_wait_response",**invalid}]}
        assert validate_workflow(workflow)
    for change in ({"maxResponseBytes":2_000_001},{"jsonMapping":{"itemsPointer":"items","result":"items","fields":[{"name":"id","path":"/id"}]}},{"jsonMapping":{**mapping,"result":"metadata"}},{"jsonMapping":{**mapping,"fields":[{"name":"bad name","path":"/id"}]}}):
        workflow={**base,"activities":[{"id":"response","type":"browser_wait_response","urlContains":"/api/orders","result":"metadata",**change}]}
        assert validate_workflow(workflow)


def test_browser_tab_schema_requires_safe_unique_name_and_popup_timeout():
    def problems(activity):
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Tabs","variables":[],"arguments":[],"activities":[{"id":"launch","type":"browser_launch"},activity]}
        return {item["code"] for item in validate_workflow(workflow)}
    assert not problems({"id":"tab","type":"browser_new_tab","name":"sign_in","url":""})
    assert "browser-tab-name" in problems({"id":"tab","type":"browser_switch_tab","name":"../secret"})
    assert "browser-popup-timeout" in problems({"id":"popup","type":"browser_capture_popup","name":"popup","timeoutSeconds":0})


def test_browser_upload_reads_only_files_inside_approved_roots_and_enforces_size(tmp_path):
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine,WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<input type="file" multiple>')
        source=tmp_path/"input"/"report.txt";source.parent.mkdir();source.write_text("safe report",encoding="utf-8")
        audits=[]
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine.root=tmp_path;engine.options=RunOptions(audit=lambda action,details:audits.append((action,details)));engine._secret_values=set();engine._max_file_bytes=1024;engine._run_started=time.monotonic();engine._max_run_seconds=60
        engine._browser_activity({"id":"upload","type":"browser_upload","selectorKind":"css","selector":"input[type=file]","paths":["input/report.txt"]},{})
        assert page.locator("input").evaluate("el => Array.from(el.files, file => file.name)")==["report.txt"]
        assert audits==[("browser.upload",{"activityId":"upload","fileCount":1,"totalBytes":len(b"safe report")})]
        engine._max_file_bytes=2
        with pytest.raises(WorkflowError,match="size limit"):
            engine._browser_activity({"id":"upload-large","type":"browser_upload","selectorKind":"css","selector":"input[type=file]","paths":["input/report.txt"]},{})
        with pytest.raises(WorkflowError,match="escapes approved roots"):
            engine._browser_activity({"id":"upload-outside","type":"browser_upload","selectorKind":"css","selector":"input[type=file]","paths":["../secret.txt"]},{})
        browser.close()


def test_browser_download_saves_atomically_with_size_and_overwrite_limits(tmp_path):
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine,WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('<a href="data:text/plain;charset=utf-8,hello%20world" download="report.txt">Download report</a>')
        audits=[]
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine.root=tmp_path;engine.options=RunOptions(audit=lambda action,details:audits.append((action,details)));engine._secret_values=set();engine._max_file_bytes=1024;engine._run_started=time.monotonic();engine._max_run_seconds=60
        variables={}
        activity={"id":"download","type":"browser_download","selectorKind":"role","selector":"link:Download report","path":"downloads/report.txt","timeoutSeconds":5,"result":"saved"}
        engine._browser_activity(activity,variables)
        destination=tmp_path/"downloads"/"report.txt"
        assert destination.read_text(encoding="utf-8")=="hello world"
        assert Path(variables["saved"]["path"])==Path("downloads/report.txt")
        assert variables["saved"]["fileName"]=="report.txt" and variables["saved"]["bytes"]==11
        assert audits[0][0]=="browser.download" and Path(audits[0][1]["path"])==Path("downloads/report.txt") and audits[0][1]["bytes"]==11
        with pytest.raises(WorkflowError,match="already exists"):
            engine._browser_activity(activity,{})
        with pytest.raises(WorkflowError,match="size limit"):
            engine._max_file_bytes=5
            engine._browser_activity({**activity,"id":"large","path":"downloads/large.txt","overwrite":True},{})
        assert not (tmp_path/"downloads"/"large.txt").exists()
        browser.close()


def test_browser_file_activities_validate_mapping_limits_and_overwrite_flag():
    def problems(activity):
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Files","variables":[],"arguments":[],"activities":[activity]}
        return {item["code"] for item in validate_workflow(workflow)}
    assert not problems({"id":"upload","type":"browser_upload","selectorKind":"css","selector":"input[type=file]","paths":["input/report.pdf"]})
    assert "browser-upload-paths" in problems({"id":"upload","type":"browser_upload","selectorKind":"css","selector":"input[type=file]","paths":[]})
    assert not problems({"id":"download","type":"browser_download","selectorKind":"role","selector":"link:Download","path":"output/file.pdf"})
    assert "browser-download-overwrite" in problems({"id":"download","type":"browser_download","selectorKind":"role","selector":"link:Download","path":"output/file.pdf","overwrite":"false"})


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
        assert [(event["type"],event["selector"]) for event in result["events"]]==[
            ("browser_hover","link:Next page"),("browser_click","link:Next page"),
            ("browser_hover","button:Finish task"),("browser_click","button:Finish task")]
        browser.close()


def test_recorder_captures_paced_browser_scroll_as_an_editable_native_activity():
    playwright=pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        context=browser.new_context();page=context.new_page()
        page.set_content('<div style="height:5000px">Long page</div>')
        inspector=BrowserInspector();inspector.context=context;inspector.page=page
        inspector.start_recording()
        page.evaluate("""() => {
          document.dispatchEvent(new WheelEvent('wheel',{deltaY:450,bubbles:true}));
          document.dispatchEvent(new WheelEvent('wheel',{deltaY:350,bubbles:true}));
        }""")
        result=inspector.stop_recording()
        assert result["events"]==[{"type":"browser_scroll","direction":"down","distancePx":800,"delayMilliseconds":700}]
        activity={"id":"scroll","type":"browser_scroll",**{key:value for key,value in result["events"][0].items() if key!="type"},"result":"progress"}
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Recorded scroll","variables":[],"arguments":[],"activities":[activity]}
        assert validate_workflow(workflow)==[]
        browser.close()


def test_browser_workflow_validation_rejects_bad_or_ambiguous_configuration():
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Browser","variables":[],"arguments":[],"activities":[
        {"id":"fill","type":"browser_fill","selectorKind":"xpath","selector":"//input","value":"x","timeoutSeconds":121}]}
    codes={problem["code"] for problem in validate_workflow(workflow)}
    assert {"browser-selector-kind","browser-timeout"}<=codes
    workflow["activities"]=[{"id":"select","type":"browser_select","selectorKind":"role","selector":"combobox:Country","value":""}]
    assert any(problem["code"]=="browser-option-value" for problem in validate_workflow(workflow))


def test_browser_frame_selector_is_optional_bounded_and_css_text():
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Frames","variables":[],"arguments":[]}
    activity={"id":"read","type":"browser_text","selectorKind":"css","selector":"#status","frameSelector":"iframe#main"}
    assert validate_workflow({**base,"activities":[activity]})==[]
    for invalid in ([],"\x00iframe","x"*2049):
        codes={problem["code"] for problem in validate_workflow({**base,"activities":[{**activity,"frameSelector":invalid}]})}
        assert "browser-frame-selector" in codes


def test_browser_selector_fallback_validation_is_bounded_and_explicit():
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Fallback","variables":[],"arguments":[],"activities":[
        {"id":"click","type":"browser_click","selectorKind":"role","selector":"button:Old label","selectorFallbacks":[{"selectorKind":"role","selector":"button:New label"}] }]}
    assert validate_workflow(workflow)==[]
    activity=workflow["activities"][0]
    activity["selectorFallbacks"]=[{"selectorKind":"role","selector":"button:Old label"}]
    assert "browser-selector-fallback-duplicate" in {problem["code"] for problem in validate_workflow(workflow)}
    activity["selectorFallbacks"]=[{"selectorKind":"role","selector":"button:New label","unexpected":True}]
    assert "browser-selector-fallback" in {problem["code"] for problem in validate_workflow(workflow)}
    activity["selectorFallbacks"]=[{"selectorKind":"role","selector":f"button:{index}"} for index in range(11)]
    assert "browser-selector-fallbacks" in {problem["code"] for problem in validate_workflow(workflow)}
    activity["selectorKind"]={"malformed":True}
    activity["selectorFallbacks"]=[]
    assert "browser-selector-kind" in {problem["code"] for problem in validate_workflow(workflow)}


def test_browser_selector_healing_validation_is_opt_in_and_role_scoped():
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Recovery","variables":[],"arguments":[],"activities":[]}
    activity={"id":"click","type":"browser_click","selectorKind":"role","selector":"button:Submit Order","selectorHealing":"accessible_role"}
    assert validate_workflow({**base,"activities":[activity]})==[]
    for patch in (
        {"selectorHealing":[]},
        {"selectorHealing":"automatic"},
        {"selectorKind":"css","selector":"button.submit"},
        {"exact":False},
    ):
        assert "browser-selector-healing" in {item["code"] for item in validate_workflow({**base,"activities":[{**activity,**patch}]})} or "browser-selector-healing-scope" in {item["code"] for item in validate_workflow({**base,"activities":[{**activity,**patch}]})}


def test_real_chromium_selector_healing_uses_only_one_strong_same_role_match_and_audits_redacted():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine, RunOptions
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<button onclick="document.body.dataset.clicked=\'yes\'">Submit Orders</button><a>Submit Orders</a>')
        audits=[];logs=[]
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions(audit=lambda action,details:audits.append((action,details)))
        engine._browser_activity({"id":"submit","type":"browser_click","selectorKind":"role","selector":"button:Submit Order","selectorHealing":"accessible_role"},{},logs)
        assert page.locator("body").get_attribute("data-clicked")=="yes"
        assert audits==[("browser.selector_healed",{"activityId":"submit","role":"button","candidateIndex":0,"similarity":0.96})]
        assert logs==[{"event":"browser-selector-healed","activityId":"submit","role":"button","similarity":0.96}]
        assert "Submit Orders" not in str(audits+logs)
        browser.close()


def test_real_chromium_selector_healing_refuses_near_ties_without_clicking():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine, RunOptions, WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<button onclick="document.body.dataset.clicked=\'one\'">Submiit order</button><button onclick="document.body.dataset.clicked=\'two\'">Submit orderx</button>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions()
        with pytest.raises(WorkflowError) as failure:
            engine._browser_activity({"id":"submit","type":"browser_click","selectorKind":"role","selector":"button:Submit order","selectorHealing":"accessible_role"},{})
        assert failure.value.code=="browser-selector-heal-ambiguous"
        assert page.locator("body").get_attribute("data-clicked") is None
        browser.close()


def test_real_chromium_explicit_selector_fallback_succeeds_and_audits_without_selector_text():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine, RunOptions
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<button onclick="document.body.dataset.clicked=\'yes\'">Updated Save</button>')
        audits=[]
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions(audit=lambda action,details:audits.append((action,details)))
        logs=[]
        engine._browser_activity({"id":"save","type":"browser_click","selectorKind":"role","selector":"button:Old Save","selectorFallbacks":[{"selectorKind":"role","selector":"button:Updated Save"}]},{},logs)
        assert page.locator("body").get_attribute("data-clicked")=="yes"
        assert audits==[("browser.selector_fallback",{"activityId":"save","fallbackIndex":0})]
        assert logs==[{"event":"browser-selector-fallback","activityId":"save","fallbackIndex":0}]
        assert "Updated Save" not in str(audits+logs)
        browser.close()


def test_real_chromium_selector_fallback_fails_closed_on_ambiguous_alternative_and_preserves_hidden_assertions():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine, RunOptions, WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<button>Save</button><button>Save</button>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions()
        with pytest.raises(WorkflowError) as failure:
            engine._browser_activity({"id":"save","type":"browser_click","selectorKind":"role","selector":"button:Old Save","selectorFallbacks":[{"selectorKind":"role","selector":"button:Save"}]},{})
        assert failure.value.activity_id=="save" and failure.value.code=="selector-fallback-ambiguous"
        engine._browser_activity({"id":"hidden","type":"browser_assert","selectorKind":"role","selector":"button:Not Present","selectorFallbacks":[{"selectorKind":"role","selector":"button:Save"}],"assertion":"hidden"},{})
        engine._browser_activity({"id":"wait-hidden","type":"browser_wait","selectorKind":"role","selector":"button:Not Present","selectorFallbacks":[{"selectorKind":"role","selector":"button:Save"}],"state":"hidden"},{})
        browser.close()


def test_browser_wait_and_assert_activities_use_real_page_state_and_clear_errors():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine, WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<p id="status">Ready for review</p><button id="disabled" disabled>Submit</button><input id="terms" type="checkbox">''')
        page.evaluate("setTimeout(()=>{const item=document.createElement('div');item.id='delayed';item.textContent='Loaded';document.body.append(item)},75)")
        engine=object.__new__(WorkflowEngine);engine._browser_page=page
        engine._browser_activity({"id":"wait","type":"browser_wait","selectorKind":"css","selector":"#delayed","state":"visible","timeoutSeconds":2},{})
        engine._browser_activity({"id":"text","type":"browser_assert","selectorKind":"css","selector":"#status","assertion":"text","expectedText":"Ready","textMatch":"contains","timeoutSeconds":2},{})
        engine._browser_activity({"id":"disabled","type":"browser_assert","selectorKind":"css","selector":"#disabled","assertion":"disabled","timeoutSeconds":2},{})
        with pytest.raises(WorkflowError,match="Browser assertion failed") as failure:
            engine._browser_activity({"id":"bad-assert","type":"browser_assert","selectorKind":"css","selector":"#status","assertion":"text","expectedText":"Complete","textMatch":"contains","timeoutSeconds":2},{})
        assert failure.value.activity_id=="bad-assert"
        assert failure.value.code=="browser-assertion-failed"
        browser.close()


def test_browser_table_read_extracts_bounded_records_from_a_real_table():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine, WorkflowError, RunOptions
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<table id="orders"><thead><tr><th>Order</th><th>Status</th><th>Status</th></tr></thead><tbody><tr><td> A-1 </td><td>Ready</td><td>Paid</td></tr><tr><td>A-2</td><td>Queued</td><td>Unpaid</td></tr></tbody></table><div id="not-table">text</div>''')
        events=[]
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine.options=RunOptions();engine._secret_values=set()
        values={}
        activity={"id":"read","type":"browser_table_read","selectorKind":"css","selector":"#orders","result":"orders","timeoutSeconds":2}
        engine._browser_activity(activity,values,events)
        assert values["orders"]==[{"Order":"A-1","Status":"Ready","Status_2":"Paid"},{"Order":"A-2","Status":"Queued","Status_2":"Unpaid"}]
        assert events==[{"event":"browser-table-read","activityId":"read","rows":2,"columns":3}]
        with pytest.raises(WorkflowError,match="limit is 1") as too_many:
            engine._browser_activity({**activity,"id":"limit","maxRows":1},{})
        assert too_many.value.code=="browser-table-limit"
        with pytest.raises(WorkflowError,match="HTML table") as wrong_element:
            engine._browser_activity({**activity,"id":"div","selector":"#not-table"},{})
        assert wrong_element.value.code=="browser-table-limit"
        browser.close()


def test_accessibility_snapshot_returns_bounded_roles_names_and_states():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine,WorkflowError,RunOptions
    from openrpa.model import validate_workflow
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('<main><h1>Order console</h1><button aria-pressed="true">Refresh records</button><input aria-label="Order reference" value="A-42"></main>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine.options=RunOptions();engine._secret_values=set()
        events=[];values={}
        activity={"id":"snapshot","type":"browser_accessibility_snapshot","result":"tree","maxOutputChars":50000,"timeoutSeconds":2}
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[activity]}
        assert validate_workflow(workflow)==[]
        assert any(problem["code"]=="browser-accessibility-limit" for problem in validate_workflow({**workflow,"activities":[{**activity,"maxOutputChars":200001}]}))
        engine._browser_activity(activity,values,events)
        assert 'heading "Order console"' in values["tree"]
        assert 'button "Refresh records" [pressed]' in values["tree"]
        assert 'textbox "Order reference"' in values["tree"]
        assert events==[{"event":"browser-accessibility-snapshot","activityId":"snapshot","characters":len(values["tree"])}]
        with pytest.raises(WorkflowError,match="limit is 5") as limited:
            engine._browser_activity({**activity,"id":"small","maxOutputChars":5},{})
        assert limited.value.code=="browser-accessibility-limit"
        browser.close()


def test_real_chromium_browser_activities_scope_to_one_iframe():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine,RunOptions,WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<iframe id="app"></iframe><iframe id="other"></iframe>')
        page.locator("#app").evaluate("""frame=>frame.srcdoc=`<base href="https://frame.example/catalog/"><button id="go" onclick="document.body.dataset.clicked='yes'">Run inside frame</button>
          <article class="book"><h2> First Book </h2><a href="books/one">Details</a></article>
          <article class="book"><h2>Second Book</h2><a href="books/two">Details</a></article>
          <table id="prices"><tr><th>Item</th><th>Price</th></tr><tr><td>Book</td><td>£10</td></tr></table>`""")
        page.wait_for_function("document.querySelector('#app').contentDocument?.readyState==='complete'")
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions()
        engine._browser_activity({"id":"click","type":"browser_click","frameSelector":"iframe#app","selectorKind":"role","selector":"button:Run inside frame"},{})
        assert page.locator("#app").evaluate("frame=>frame.contentDocument.body.dataset.clicked")=="yes"
        variables={}
        engine._browser_activity({"id":"extract","type":"browser_extract_records","frameSelector":"iframe#app","selectorKind":"css","selector":"article.book","fields":[
          {"name":"title","selector":"h2","source":"text","required":True},
          {"name":"url","selector":"a","source":"attribute","attribute":"href","required":True}],"result":"books"},variables)
        assert variables["books"]==[{"title":"First Book","url":"https://frame.example/catalog/books/one"},{"title":"Second Book","url":"https://frame.example/catalog/books/two"}]
        engine._browser_activity({"id":"table","type":"browser_table_read","frameSelector":"iframe#app","selectorKind":"css","selector":"#prices","result":"prices"},variables)
        assert variables["prices"]==[{"Item":"Book","Price":"£10"}]
        with pytest.raises(WorkflowError,match="exactly one iframe"):
            engine._browser_activity({"id":"ambiguous","type":"browser_text","frameSelector":"iframe","selectorKind":"css","selector":"h2"},variables)
        browser.close()


def test_browser_table_read_validation_enforces_css_and_bounded_output():
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Browser table","variables":[],"arguments":[],"activities":[
        {"id":"read","type":"browser_table_read","selectorKind":"role","selector":"table:Orders","maxRows":100000,"result":"bad-name"}]}
    codes={problem["code"] for problem in validate_workflow(workflow)}
    assert {"browser-table-selector","browser-table-limit","browser-table-result"}<=codes


def test_browser_wait_and_assert_validation_is_strict():
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Browser checks","variables":[],"arguments":[],"activities":[
        {"id":"wait","type":"browser_wait","selectorKind":"css","selector":"#main","state":"almost-visible","timeoutSeconds":15},
        {"id":"assert","type":"browser_assert","selectorKind":"css","selector":"#main","assertion":"contains","timeoutSeconds":15}]}
    codes={problem["code"] for problem in validate_workflow(workflow)}
    assert {"browser-wait-state","browser-assertion"}<=codes


def test_browser_extract_records_returns_normalized_card_fields_and_absolute_links():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page()
        page.set_content('''<base href="https://books.example/catalog/"><article class="book"><h3><a href="book-one">  The   First Book </a></h3><p class="price">£12.50</p><p class="availability">In stock</p><p class="rating star-rating Three">Rated</p></article><article class="book"><h3><a href="/book-two">Second Book</a></h3><p class="price">£8.00</p><p class="availability">Out of stock</p><p class="rating star-rating Five">Rated</p></article>''')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions()
        activity={"id":"extract","type":"browser_extract_records","selectorKind":"css","selector":"article.book","fields":[
            {"name":"title","selector":"h3 a","source":"text","required":True},
            {"name":"price","selector":".price","source":"text","required":True},
            {"name":"availability","selector":".availability","source":"text","required":True},
            {"name":"url","selector":"h3 a","source":"attribute","attribute":"href","required":True},
            {"name":"rating","selector":".rating","source":"attribute","attribute":"class","tokenIndex":2,"required":True}],"maxRecords":10,"maxOutputChars":10000,"result":"books","timeoutSeconds":2}
        assert validate_workflow({"format":"openrpa.workflow","formatVersion":1,"name":"Book cards","variables":[],"arguments":[],"activities":[activity]})==[]
        values={};logs=[];engine._browser_activity(activity,values,logs)
        assert values["books"]==[
            {"title":"The First Book","price":"£12.50","availability":"In stock","url":"https://books.example/catalog/book-one","rating":"Three"},
            {"title":"Second Book","price":"£8.00","availability":"Out of stock","url":"https://books.example/book-two","rating":"Five"}]
        assert logs[-1]["event"]=="browser-records-extracted" and logs[-1]["records"]==2
        browser.close()


def test_browser_extract_records_appends_paginated_results_with_aggregate_bounds():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    from openrpa.model import WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<article class="book"><h2>Page One</h2></article>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions()
        activity={"id":"extract","type":"browser_extract_records","selectorKind":"css","selector":"article.book","fields":[{"name":"title","selector":"h2","source":"text","required":True}],"append":True,"maxRecords":10,"maxTotalRecords":2,"maxTotalOutputChars":100,"result":"books","timeoutSeconds":2}
        assert validate_workflow({"format":"openrpa.workflow","formatVersion":1,"name":"Pages","variables":[],"arguments":[],"activities":[activity]})==[]
        values={};logs=[]
        engine._browser_activity(activity,values,logs)
        page.set_content('<article class="book"><h2>Page Two</h2></article>')
        engine._browser_activity(activity,values,logs)
        assert values["books"]==[{"title":"Page One"},{"title":"Page Two"}]
        assert logs[-1]["records"]==1 and logs[-1]["totalRecords"]==2 and logs[-1]["appended"] is True
        page.set_content('<article class="book"><h2>Page Three</h2></article>')
        with pytest.raises(WorkflowError,match="aggregate record or text limit"):
            engine._browser_activity(activity,values,logs)
        assert "books" not in values
        activity["maxTotalRecords"]=5;values["books"]=[{"title":"Previously collected"}]
        page.set_content('<article class="book"><h2>Current page starts</h2></article><article class="book"><span>Missing title</span></article>')
        with pytest.raises(WorkflowError,match="item 2 is missing required field 'title'"):
            engine._browser_activity(activity,values,logs)
        assert "books" not in values
        browser.close()


def test_browser_extract_records_deduplicates_incremental_scroll_overlap_by_selected_fields():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    from openrpa.model import WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<article class="item"><span class="sku" data-sku="A"></span><h2>Alpha</h2></article><article class="item"><span class="sku" data-sku="B"></span><h2>Beta</h2></article><article class="item"><span class="sku" data-sku=""></span><h2>Unknown first</h2></article>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions()
        activity={"id":"collect","type":"browser_extract_records","selectorKind":"css","selector":"article.item","fields":[{"name":"sku","selector":".sku","source":"attribute","attribute":"data-sku"},{"name":"title","selector":"h2","source":"text","required":True}],"append":True,"deduplicateBy":["sku"],"maxRecords":10,"maxTotalRecords":5,"maxTotalOutputChars":5000,"result":"items","timeoutSeconds":2}
        assert validate_workflow({"format":"openrpa.workflow","formatVersion":1,"name":"Scroll feed","variables":[],"arguments":[],"activities":[activity]})==[]
        values={};logs=[]
        engine._browser_activity(activity,values,logs)
        page.set_content('<article class="item"><span class="sku" data-sku="B"></span><h2>Beta duplicate</h2></article><article class="item"><span class="sku" data-sku="C"></span><h2>Gamma</h2></article><article class="item"><span class="sku" data-sku=""></span><h2>Unknown second</h2></article>')
        engine._browser_activity(activity,values,logs)
        assert values["items"]==[{"sku":"A","title":"Alpha"},{"sku":"B","title":"Beta"},{"sku":"","title":"Unknown first"},{"sku":"C","title":"Gamma"},{"sku":"","title":"Unknown second"}]
        assert logs[-1]["duplicatesSkipped"]==1 and logs[-1]["totalRecords"]==5
        # Once at capacity, an overlapping viewport containing only known keys remains valid.
        page.set_content('<article class="item"><span class="sku" data-sku="A"></span><h2>Alpha</h2></article>')
        engine._browser_activity(activity,values,logs)
        assert len(values["items"])==5 and logs[-1]["duplicatesSkipped"]==1
        # A genuinely new product still fails atomically when the configured total is exceeded.
        page.set_content('<article class="item"><span class="sku" data-sku="D"></span><h2>Delta</h2></article>')
        with pytest.raises(WorkflowError,match="aggregate record or text limit"):
            engine._browser_activity(activity,values,logs)
        assert "items" not in values
        browser.close()


def test_browser_record_deduplication_requires_valid_mapped_fields_and_append_mode():
    base={"format":"openrpa.workflow","formatVersion":1,"name":"Feed","variables":[],"arguments":[]}
    fields=[{"name":"sku","selector":"[data-sku]","source":"attribute","attribute":"data-sku"}]
    def problems(**changes):
        activity={"id":"extract","type":"browser_extract_records","selectorKind":"css","selector":"article.item","fields":fields,**changes}
        return {item["code"] for item in validate_workflow({**base,"activities":[activity]})}
    assert not problems(append=True,deduplicateBy=["sku"])
    assert "browser-extract-deduplicate" in problems(append=True,deduplicateBy=["missing"])
    assert "browser-extract-deduplicate" in problems(append=True,deduplicateBy=["sku","sku"])
    assert "browser-extract-deduplicate" in problems(deduplicateBy=["sku"])
    assert "browser-extract-deduplicate" in problems(append=True,deduplicateBy="sku")


def test_browser_extract_records_fails_clearly_for_missing_required_field():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<article class="item"><span>Present</span></article>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set()
        from openrpa.model import WorkflowError
        with pytest.raises(WorkflowError,match="item 1 is missing required field 'price'"):
            engine._browser_activity({"id":"extract","type":"browser_extract_records","selectorKind":"css","selector":".item","fields":[{"name":"price","selector":".price","source":"text","required":True}],"result":"records"},{})
        browser.close()


def test_browser_scroll_emits_progress_and_stops_at_page_bottom():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    import time
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page(viewport={"width":800,"height":600});page.set_content('<main>'+''.join(f'<section style="height:240px">Listing {i}</section>' for i in range(12))+'</main>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions();engine._run_started=time.monotonic();engine._max_run_seconds=60
        variables={};logs=[]
        engine._browser_activity({"id":"scroll","type":"browser_scroll","direction":"down","distancePx":500,"delayMilliseconds":5,"toBottom":True,"maxSteps":30,"result":"progress"},variables,logs)
        assert variables["progress"]["reachedBottom"] is True
        assert variables["progress"]["scrollsCompleted"]<30
        assert len(logs)>=2 and all(event["event"]=="browser-scroll-progress" for event in logs)
        assert all("scrollY" in event and "progressPercent" in event for event in logs)
        browser.close()


def test_browser_scroll_targets_unique_inner_container_and_reports_container_progress():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import RunOptions,WorkflowEngine
    import time
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page(viewport={"width":800,"height":600})
        page.set_content('<style>body{height:600px}#feed{height:220px;width:500px;overflow:auto}#feed article{height:180px}</style><div id="feed">'+''.join(f'<article>Product {i}</article>' for i in range(12))+'</div>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set();engine.options=RunOptions();engine._run_started=time.monotonic();engine._max_run_seconds=60
        variables={};logs=[]
        engine._browser_activity({"id":"scroll-feed","type":"browser_scroll","containerSelector":"#feed","direction":"down","distancePx":180,"delayMilliseconds":5,"toBottom":True,"maxSteps":30,"result":"progress"},variables,logs)
        result=variables["progress"]
        assert result["target"]=="container"
        assert result["scrollTop"]>0 and result["reachedBottom"] is True
        assert result["scrollY"]<result["scrollTop"]
        assert result["progressPercent"]==100
        assert len(logs)>=2 and all(event["target"]=="container" for event in logs)
        browser.close()


def test_browser_scroll_rejects_missing_or_ambiguous_container_at_runtime():
    playwright=pytest.importorskip("playwright.sync_api")
    from openrpa.engine import WorkflowEngine
    from openrpa.model import WorkflowError
    with playwright.sync_playwright() as runtime:
        try:browser=runtime.chromium.launch(headless=True)
        except Exception as exc:pytest.skip(f"Chromium runtime is unavailable: {exc}")
        page=browser.new_page();page.set_content('<div class="feed"></div><div class="feed"></div>')
        engine=object.__new__(WorkflowEngine);engine._browser_page=page;engine._secret_values=set()
        with pytest.raises(WorkflowError,match="must match exactly one element; found 2"):
            engine._browser_activity({"id":"scroll","type":"browser_scroll","containerSelector":".feed"},{})
        with pytest.raises(WorkflowError,match="Could not resolve scroll container selector"):
            engine._browser_activity({"id":"scroll","type":"browser_scroll","containerSelector":"["},{})
        browser.close()


def test_browser_launch_and_scroll_schema_accepts_supported_options_and_rejects_bad_types():
    def problems(activity):
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Browser","variables":[],"arguments":[],"activities":[activity]}
        return validate_workflow(workflow)
    assert problems({"id":"launch","type":"browser_launch","browserType":"firefox","headless":False})==[]
    assert problems({"id":"launch","type":"browser_launch","browserType":"webkit","headless":False})==[]
    assert problems({"id":"launch","type":"browser_launch","browserType":"chromium","channel":"custom","executablePath":"C:\\Apps\\Brave\\brave.exe","headless":False})==[]
    assert any(item["code"]=="browser-engine" for item in problems({"id":"launch","type":"browser_launch","browserType":[]}))
    assert any(item["code"]=="browser-scroll-direction" for item in problems({"id":"scroll","type":"browser_scroll","direction":[]}))
    assert problems({"id":"scroll","type":"browser_scroll","containerSelector":"#results"})==[]
    assert any(item["code"]=="browser-scroll-container" for item in problems({"id":"scroll","type":"browser_scroll","containerSelector":" "}))
    assert any(item["code"]=="browser-scroll-container" for item in problems({"id":"scroll","type":"browser_scroll","containerSelector":3}))


def test_browser_extract_records_append_configuration_is_bounded_and_typed():
    def problems(activity):
        workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Browser records","variables":[],"arguments":[],"activities":[activity]}
        return validate_workflow(workflow)
    base={"id":"extract","type":"browser_extract_records","selectorKind":"css","selector":"article.item","fields":[{"name":"title","selector":"h2","source":"text"}],"append":True,"maxTotalRecords":1500,"maxTotalOutputChars":500000}
    assert problems(base)==[]
    bad=problems({**base,"append":"yes","maxTotalRecords":50001,"maxTotalOutputChars":0})
    assert {item["code"] for item in bad}>={"browser-extract-append","browser-extract-total-limit"}
