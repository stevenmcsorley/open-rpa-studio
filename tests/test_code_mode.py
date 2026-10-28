import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import pytest
from openrpa import code_mode

pytestmark = pytest.mark.skipif(sys.platform != "linux" or importlib.util.find_spec("quickjs") is None, reason="Optional Linux Code Mode runtime is not installed")

SPECS=[{'name':'echo','description':'Return text for a test','inputSchema':{'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}}, {'name':'deny','description':'Denied operation','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}]
def invoke(name,args):
    if name=='deny':raise PermissionError('Permission required')
    return {'text':args['text']}
def run(code,**kwargs):return code_mode.execute(SPECS,{'code':code,**kwargs},invoke)

def test_discovery_without_running():
    assert [s['name'] for s in code_mode.tool_specs()]==['search','execute']
    assert code_mode.search(SPECS,{'query':'echo'})['matches'][0]['inputSchema']==SPECS[0]['inputSchema']
    assert 'inputSchema' not in code_mode.search(SPECS,{'query':''})['matches'][0]
    assert code_mode.search(SPECS,{'query':'zzzzzz'})['total']==0

@pytest.mark.parametrize('args',[{}, {'code':'x','timeout_ms':True}, {'code':'x','max_calls':101}, {'code':'x','unknown':True}])
def test_invalid_arguments(args):
    with pytest.raises(ValueError):code_mode.execute(SPECS,args,invoke)

def test_composition_and_projection():
    r=run("const a=await tools.echo({text:input.text});const b=await tools.call('echo',{text:a.text+'!'});return b.text;",input={'text':'hi'})
    assert r['ok'],r
    assert r['result']=='hi!' and r['api_calls']==2

def test_caught_error_and_native_permission():
    r=run("try{await tools.deny({});}catch(e){return e.message;}")
    assert r['ok'] and 'Permission required' in r['result']
    assert r['calls'][0]['status']=='failed'

def test_schema_validation_before_native_dispatch():
    called=[]
    r=code_mode.execute(SPECS,{'code':"return await tools.echo({text:23});"},lambda *a:called.append(a))
    assert not r['ok'] and not called

def test_allowlist_and_no_recursive_tools():
    assert not run("return await tools.call('deny',{});",allowed_tools=['echo'])['ok']
    assert not run("return await tools.call('execute',{});")['ok']

def test_calls_partial_failure_and_no_retry():
    r=run("await tools.echo({text:'committed'});await tools.deny({});await tools.echo({text:'never'});")
    assert not r['ok'] and r['api_calls']==2 and r['calls'][0]['status']=='complete'
    r=run("await tools.echo({text:'a'});await tools.echo({text:'b'});",max_calls=1)
    assert not r['ok'] and r['api_calls']==1

def test_output_limits_cpu_and_unresolved_promises():
    r=run("return 'x'.repeat(10000);",max_output_chars=100)
    assert r['ok'] and r['result']['truncated']
    assert not run('while(true){}')['ok']
    assert not run('return await new Promise(()=>{});')['ok']

def test_cancel_and_deadline():
    event=threading.Event();event.set()
    r=code_mode.execute(SPECS,{'code':'return 1;'},invoke,event)
    assert not r['ok'] and r['api_calls']==0
    def slow(name,args):
        import time
        time.sleep(.15)
        return {}
    r=code_mode.execute(SPECS,{'code':"await tools.echo({text:'x'});await tools.echo({text:'y'});",'timeout_ms':100},slow)
    assert not r['ok'] and r['api_calls']<=1

def test_js_has_no_ambient_host_access():
    r=run("return [typeof fetch,typeof process,typeof require,typeof std,typeof os];")
    assert r['ok'] and r['result']==['undefined']*5

def test_process_level_file_and_socket_denial():
    child=Path(code_mode.__file__).with_name('code_sandbox.py')
    p=subprocess.run([sys.executable,'-I',str(child)],input=json.dumps({'probe':True})+'\n',text=True,capture_output=True,timeout=10)
    value=json.loads(p.stdout)
    assert value['file_open']==-1 and value['file_errno']==errno.EPERM
    assert value['socket']==-1 and value['socket_errno']==errno.EPERM

def test_openrpa_compact_full_and_permission_gates(tmp_path,monkeypatch):
    from openrpa.mcp_server import ProjectMCPServer
    (tmp_path/'workflows').mkdir()
    (tmp_path/'project.json').write_text(json.dumps({'format':'openrpa.project','formatVersion':1,'name':'Test','main':'Main','workflows':{'Main':'workflows/main.workflow.json'}}))
    (tmp_path/'workflows/main.workflow.json').write_text(json.dumps({'format':'openrpa.workflow','formatVersion':1,'name':'Main','variables':[],'arguments':[],'activities':[]}))
    s=ProjectMCPServer(str(tmp_path),mcp_mode='code')
    monkeypatch.setattr(s,'_sync_active_project',lambda:None)
    def call(name,args):return s.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})['result']
    listing=s.handle({'jsonrpc':'2.0','id':1,'method':'tools/list'})['result']['tools']
    assert [x['name'] for x in listing]==['search','execute']
    r=call('execute',{'code':'return (await tools.openrpa_project_info({})).projectName;'})
    assert not r['isError'],r
    assert r['structuredContent']['result']=='Test'
    r=call('execute',{'code':"return await tools.call('openrpa_run_workflow',{name:'Main'});"})
    assert r['isError']
    assert not call('openrpa_project_info',{})['isError']

def test_openrpa_project_switch_stops_later_calls(tmp_path,monkeypatch):
    from openrpa.mcp_server import ProjectMCPServer
    (tmp_path/'workflows').mkdir()
    (tmp_path/'project.json').write_text(json.dumps({'format':'openrpa.project','formatVersion':1,'name':'Test','main':'Main','workflows':{'Main':'workflows/main.workflow.json'}}))
    (tmp_path/'workflows/main.workflow.json').write_text(json.dumps({'format':'openrpa.workflow','formatVersion':1,'name':'Main','variables':[],'arguments':[],'activities':[]}))
    s=ProjectMCPServer(str(tmp_path),mcp_mode='code')
    monkeypatch.setattr(s,'_sync_active_project',lambda:None)
    native=s._call_tool;seen=[]
    def invoke(name,args,event):
        result=native(name,args,event);seen.append(name);s.project_path+='-changed';return result
    monkeypatch.setattr(s,'_call_tool',invoke)
    result=s.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'execute','arguments':{'code':'await tools.openrpa_project_info({});return await tools.openrpa_list_workflows({});'}}})['result']
    assert result['isError'] and seen==['openrpa_project_info']
    assert 'active project changed' in result['structuredContent']['error']
