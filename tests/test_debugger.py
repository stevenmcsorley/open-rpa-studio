import json
import importlib
import queue
import threading
import time

from openrpa.debugger import DebugController
from openrpa.engine import RunOptions, run_project


def _start(tmp_path, activities, debugger, cancel=lambda:False):
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":activities}
    project={"format":"openrpa.project","formatVersion":1,"name":"Debug test","main":"Main","workflows":{"Main":"main.json"}}
    (tmp_path/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    events=[]
    condition=threading.Condition()
    def on_event(event):
        with condition:
            events.append(event)
            condition.notify_all()
    output=[]
    thread=threading.Thread(target=lambda:output.append(run_project(project,tmp_path,options=RunOptions(debugger=debugger,event=on_event,cancel=cancel))))
    thread.start()
    return thread,output,events,condition


def _wait_for(events, condition, event_name, activity_id, timeout=3):
    deadline=time.monotonic()+timeout
    with condition:
        while not any(e.get("event")==event_name and e.get("activityId")==activity_id for e in events):
            remaining=deadline-time.monotonic()
            assert remaining>0, f"Timed out waiting for {event_name} at {activity_id}; events={events}"
            condition.wait(remaining)


def test_debug_run_starts_paused_and_steps_over_real_activities(tmp_path):
    debugger=DebugController()
    activities=[
        {"id":"one","type":"assign","target":"value","value":"1"},
        {"id":"two","type":"assign","target":"value","value":"2"},
        {"id":"done","type":"log","message":"finished {{value}}"},
    ]
    thread,output,events,condition=_start(tmp_path,activities,debugger)
    _wait_for(events,condition,"debug.paused","one")
    assert thread.is_alive()
    debugger.step_over()
    _wait_for(events,condition,"debug.paused","two")
    debugger.step_over()
    _wait_for(events,condition,"debug.paused","done")
    debugger.resume()
    thread.join(3)
    assert not thread.is_alive()
    assert output[0].status=="succeeded"
    assert output[0].variables["value"]=="2"
    assert [event["activityId"] for event in events if event.get("event")=="activity-completed"]==["one","two","done"]

def test_safe_watch_expressions_use_live_scope_redact_secrets_and_bound_large_results():
    import pytest
    debugger=DebugController()
    variables={"rows":[{"amount":10},{"amount":25}],"credentials":{"api":"private-watch-secret"},"large":["x"*16 for _ in range(1400)]}
    def redact(value):
        if isinstance(value,str): return value.replace("private-watch-secret","[REDACTED]")
        if isinstance(value,list): return [redact(item) for item in value]
        if isinstance(value,dict): return {key:redact(item) for key,item in value.items()}
        return value
    ready=threading.Event()
    def pause():
        debugger.before_activity("inspect",0,variables,lambda:False,lambda event:ready.set(),redact=redact)
    thread=threading.Thread(target=pause);thread.start()
    assert ready.wait(2)
    assert debugger.evaluate_watch("len(rows)")=={"status":"ok","type":"int","value":2}
    assert debugger.evaluate_watch("rows[1].amount")["value"]==25
    assert debugger.evaluate_watch("credentials.api")["value"]=="[REDACTED]"
    assert "private-watch-secret" not in str(debugger.evaluate_watch("credentials"))
    assert debugger.evaluate_watch("__import__('os')")["status"]=="error"
    large=debugger.evaluate_watch("large")
    assert large["status"]=="ok" and large["value"]["truncated"] is True
    debugger.resume();thread.join(2);assert not thread.is_alive()
    with pytest.raises(ValueError,match="only while paused"):
        debugger.evaluate_watch("len(rows)")

def test_watch_expression_is_length_bounded():
    import pytest
    debugger=DebugController()
    with pytest.raises(ValueError,match="1–2048"):
        debugger.evaluate_watch("x"*2049)

def test_step_into_pauses_inside_control_flow(tmp_path):
    debugger=DebugController()
    activities=[
        {"id":"branch","type":"if","condition":"True","then":[{"id":"nested","type":"assign","target":"value","value":"3"}],"else":[]},
        {"id":"after","type":"log","message":"after"},
    ]
    thread,output,events,condition=_start(tmp_path,activities,debugger)
    _wait_for(events,condition,"debug.paused","branch")
    debugger.step_into()
    _wait_for(events,condition,"debug.paused","nested")
    debugger.resume()
    thread.join(3)
    assert not thread.is_alive() and output[0].status=="succeeded"
    assert output[0].variables["value"]=="3"

def test_step_out_finishes_current_container_before_pausing_at_caller(tmp_path):
    debugger=DebugController()
    activities=[
        {"id":"branch","type":"if","condition":"True","then":[
            {"id":"nested-one","type":"assign","target":"value","value":"1"},
            {"id":"nested-two","type":"assign","target":"value","value":"2"},
        ],"else":[]},
        {"id":"after","type":"log","message":"after"},
    ]
    thread,output,events,condition=_start(tmp_path,activities,debugger)
    _wait_for(events,condition,"debug.paused","branch")
    debugger.step_into()
    _wait_for(events,condition,"debug.paused","nested-one")
    debugger.step_out()
    _wait_for(events,condition,"debug.paused","after")
    assert all(any(event.get("event")=="activity-completed" and event.get("activityId")==aid for event in events) for aid in ("nested-one","nested-two","branch"))
    assert not any(event.get("event")=="activity-started" and event.get("activityId")=="after" for event in events)
    debugger.resume()
    thread.join(3)
    assert not thread.is_alive() and output[0].status=="succeeded"
    assert output[0].variables["value"]=="2"


def test_breakpoint_pauses_only_at_matching_activity(tmp_path):
    debugger=DebugController({"two"},start_paused=False)
    activities=[
        {"id":"one","type":"assign","target":"value","value":"1"},
        {"id":"two","type":"assign","target":"value","value":"2"},
    ]
    thread,output,events,condition=_start(tmp_path,activities,debugger)
    _wait_for(events,condition,"debug.paused","two")
    assert any(e.get("event")=="activity-completed" and e.get("activityId")=="one" for e in events)
    debugger.resume()
    thread.join(3)
    assert not thread.is_alive() and output[0].status=="succeeded"

def test_flowchart_node_and_action_breakpoints_are_collected():
    from openrpa.bridge import _workflow_breakpoints
    workflow={"executionModel":"flowchart","activities":[],"flowchart":{"nodes":[
        {"id":"decision-node","kind":"decision","breakpoint":True,"condition":"True"},
        {"id":"action-node","kind":"action","breakpoint":True,"activity":{"id":"write-log","type":"if","condition":"True","then":[{"id":"nested-log","type":"log","breakpoint":True}],"else":[]}},
    ]}}
    assert _workflow_breakpoints(workflow)=={"decision-node","write-log","nested-log"}

def test_state_machine_breakpoints_include_states_and_nested_activities():
    from openrpa.bridge import _workflow_breakpoints
    workflow={"executionModel":"state_machine","activities":[],"stateMachine":{"states":[
        {"id":"review","breakpoint":True,"activities":[{"id":"process","type":"switch","expression":"route","cases":[{"value":"a","activities":[{"id":"branch-log","type":"log","breakpoint":True}]}],"default":[]}]},
        {"id":"finish","activities":[]}],"transitions":[]}}
    assert _workflow_breakpoints(workflow)=={"review","branch-log"}


def test_cancel_wakes_a_debugger_paused_at_boundary(tmp_path):
    debugger=DebugController()
    activities=[{"id":"never-run","type":"log","message":"should not execute"}]
    cancelled=threading.Event()
    thread,output,events,condition=_start(tmp_path,activities,debugger,cancelled.is_set)
    _wait_for(events,condition,"debug.paused","never-run")
    cancelled.set()
    debugger.wake_for_cancel()
    thread.join(3)
    assert not thread.is_alive() and output[0].status=="cancelled"
    assert not any(e.get("event")=="activity-started" for e in events)


def test_paused_live_variable_edit_is_typed_and_affects_next_activity(tmp_path):
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[{"name":"amount","type":"integer","value":2}],"arguments":[],"activities":[
        {"id":"copy","type":"assign","target":"result","value":"{{amount}}"}]}
    project={"format":"openrpa.project","formatVersion":1,"name":"Live edit","main":"Main","workflows":{"Main":"main.json"}}
    (tmp_path/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    debugger=DebugController();events=[];condition=threading.Condition();output=[]
    def on_event(event):
        with condition:events.append(event);condition.notify_all()
    thread=threading.Thread(target=lambda:output.append(run_project(project,tmp_path,options=RunOptions(debugger=debugger,event=on_event))))
    thread.start();_wait_for(events,condition,"debug.paused","copy")
    paused=next(event for event in events if event.get("event")=="debug.paused")
    assert paused["variables"]=={"amount":2}
    assert paused["editableVariables"]==["amount"]
    try:
        debugger.set_variable("amount","wrong")
        assert False,"declared variable type should be enforced"
    except ValueError as exc:
        assert "must remain type integer" in str(exc)
    debugger.set_variable("amount",9)
    debugger.resume();thread.join(3)
    assert not thread.is_alive() and output[0].status=="succeeded"
    assert output[0].variables["result"]==9


def test_debugger_rejects_edits_outside_pause_unknown_names_and_oversized_values():
    debugger=DebugController()
    try:
        debugger.set_variable("x",1)
        assert False,"must require pause"
    except ValueError as exc:
        assert "only while paused" in str(exc)
    variables={"x":1};events=[];condition=threading.Condition()
    def emit(event):
        with condition:events.append(event);condition.notify_all()
    thread=threading.Thread(target=lambda:debugger.before_activity("step",0,variables,lambda:False,emit))
    thread.start();_wait_for(events,condition,"debug.paused","step")
    for name,value,message in [("missing",2,"not present"),("x","z"*65537,"64 KiB")]:
        try:
            debugger.set_variable(name,value)
            assert False,"invalid debugger edit should fail"
        except ValueError as exc:
            assert message in str(exc)
    debugger.resume();thread.join(3)
    assert not thread.is_alive() and variables=={"x":1}


def test_debug_variable_snapshot_redacts_vault_secrets(tmp_path,monkeypatch):
    import openrpa.engine as engine
    monkeypatch.setattr(engine,"get_safe_keyring",lambda:type("Vault",(),{"get_password":lambda self,service,username:"never-display-this-secret"})())
    debugger=DebugController({"inspect"},start_paused=False)
    activities=[
        {"id":"credential","type":"credential_get","service":"test","username":"account","result":"apiKey"},
        {"id":"inspect","type":"log","message":"inspect"},
    ]
    thread,output,events,condition=_start(tmp_path,activities,debugger)
    _wait_for(events,condition,"debug.paused","inspect")
    snapshot=next(event["variables"] for event in events if event.get("event")=="debug.paused")
    assert snapshot["apiKey"]=="[REDACTED]"
    assert debugger.evaluate_watch("apiKey")["value"]=="[REDACTED]"
    assert "never-display-this-secret" not in json.dumps(events)
    debugger.resume()
    thread.join(3)
    assert not thread.is_alive() and output[0].status=="succeeded"


def test_native_bridge_exposes_debug_pause_step_and_resume(tmp_path,monkeypatch):
    monkeypatch.setenv("OPENRPA_DATA_DIR",str(tmp_path/"app-data"))
    bridge=importlib.import_module("openrpa.bridge")
    output:queue.Queue=queue.Queue()
    monkeypatch.setattr(bridge,"send",output.put)
    pending=[]
    def next_matching(predicate):
        for index,message in enumerate(pending):
            if predicate(message): return pending.pop(index)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            message=output.get(timeout=max(0.01,deadline-time.monotonic()))
            if predicate(message): return message
            pending.append(message)
        raise AssertionError("Timed out waiting for bridge message")
    root=tmp_path/"project"
    root.mkdir()
    workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[{"name":"items","type":"any","value":[{"total":12},{"total":34}]}],"arguments":[],"activities":[
        {"id":"first","type":"log","message":"first"},
        {"id":"second","type":"log","message":"second"},
    ]}
    project={"format":"openrpa.project","formatVersion":1,"name":"bridge debug","main":"Main","workflows":{"Main":"main.json"}}
    (root/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    bridge.handle({"id":1,"method":"workflow.run","params":{"project":project,"root":str(root),"workflow":"Main","debug":True}})
    pause=next_matching(lambda message:message.get("event")=="run.event" and message["data"].get("event")=="debug.paused")
    assert pause["event"]=="run.event" and pause["data"]["event"]=="debug.paused" and pause["data"]["activityId"]=="first"
    assert "variables" in pause["data"]
    bridge.handle({"id":8,"method":"debug.evaluate_watch","params":{"expression":"items[1].total"}})
    watched=next_matching(lambda message:message.get("id")==8)
    assert watched["result"]=={"status":"ok","type":"int","value":34}
    bridge.handle({"id":9,"method":"debug.evaluate_watch","params":{"expression":"__import__('os')"}})
    assert next_matching(lambda message:message.get("id")==9)["result"]["status"]=="error"
    bridge.handle({"id":2,"method":"debug.step_over","params":{}})
    assert next_matching(lambda message:message.get("id")==2)["id"]==2
    pause=next_matching(lambda message:message.get("event")=="run.event" and message["data"].get("event")=="debug.paused")
    assert pause["data"]["event"]=="debug.paused" and pause["data"]["activityId"]=="second"
    bridge.handle({"id":3,"method":"debug.step_out","params":{}})
    assert next_matching(lambda message:message.get("id")==3)["id"]==3
    finished=next_matching(lambda message:message.get("id")==1)
    assert finished["id"]==1 and finished["result"]["status"]=="succeeded"
    durable=bridge.history.get_run(finished["result"]["runId"])
    assert all("variables" not in event for event in durable["events"] if event.get("event")=="debug.paused")

    workflow["activities"]=[{"id":"never-start","type":"log","message":"must remain unexecuted"}]
    (root/"main.json").write_text(json.dumps(workflow),encoding="utf-8")
    bridge.handle({"id":4,"method":"workflow.run","params":{"project":project,"root":str(root),"workflow":"Main","debug":True}})
    pause=next_matching(lambda message:message.get("event")=="run.event" and message["data"].get("event")=="debug.paused")
    assert pause["data"]["activityId"]=="never-start"
    bridge.handle({"id":5,"method":"workflow.cancel","params":{}})
    next_matching(lambda message:message.get("id")==5)
    cancelled=next_matching(lambda message:message.get("id")==4)
    assert cancelled["result"]["status"]=="cancelled"
    assert cancelled["result"]["activities"]=={}

