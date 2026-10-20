"""Verify nested workflow diagnostics through the installed persistent bridge."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path


def main() -> None:
    if len(sys.argv)!=3:
        raise SystemExit("usage: installed_error_callpath_acceptance.py BRIDGE_EXE ACCEPTANCE_ROOT")
    executable=Path(sys.argv[1]).resolve()
    root=Path(sys.argv[2]).resolve()
    if root.exists(): raise SystemExit(f"Refusing existing acceptance root: {root}")
    root.mkdir(parents=True)
    env=os.environ.copy();env["OPENRPA_DATA_DIR"]=str(root/"bridge-data")
    process=subprocess.Popen([str(executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding="utf-8",bufsize=1,env=env)
    messages:queue.Queue[dict]=queue.Queue()
    seen:list[dict]=[]
    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try: messages.put(json.loads(line))
            except json.JSONDecodeError: messages.put({"unparsed":line})
    reader=threading.Thread(target=read_output,daemon=True);reader.start()

    def send(request_id:int,method:str,params:dict) -> dict:
        assert process.stdin is not None
        process.stdin.write(json.dumps({"id":request_id,"method":method,"params":params})+"\n")
        process.stdin.flush()
        while True:
            try: row=messages.get(timeout=30)
            except queue.Empty:
                raise AssertionError({"message":f"Timed out waiting for {method}","processReturnCode":process.poll(),"messages":seen[-12:],"stderr":process.stderr.read() if process.poll() is not None and process.stderr else ""})
            seen.append(row)
            if row.get("id")==request_id:
                if "error" in row: raise AssertionError(row["error"])
                return row["result"]

    try:
        created=send(1,"project.create",{"path":str(root/"project"),"name":"Error path acceptance"})
        project=created["project"]
        project["workflows"].update({"Child":"workflows/child.workflow.json","Grandchild":"workflows/grandchild.workflow.json"})
        workflows={
            "Main":{"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"call-child","type":"invoke_workflow","workflow":"Child"}]},
            "Child":{"format":"openrpa.workflow","formatVersion":1,"name":"Child","variables":[],"arguments":[],"activities":[{"id":"call-grandchild","type":"invoke_workflow","workflow":"Grandchild"}]},
            "Grandchild":{"format":"openrpa.workflow","formatVersion":1,"name":"Grandchild","variables":[],"arguments":[],"activities":[{"id":"read-missing","type":"file_read_text","path":"missing.txt","result":"text"}]},
        }
        send(2,"project.save",{"root":created["root"],"project":project,"workflows":workflows})
        result=send(3,"workflow.run",{"project":project,"root":created["root"],"workflow":"Main"})
        assert result["status"]=="failed"
        assert result["error"]["workflow"]=="Grandchild"
        assert result["error"]["activityId"]=="read-missing"
        assert len(result["error"]["workflowStack"])==2
        assert "Call path:" in result["error"]["message"]
        history=send(4,"run.history",{"limit":5})["runs"]
        recorded=next(item for item in history if item["runId"]==result["runId"])
        assert json.loads(recorded["error"])["workflowStack"]==result["error"]["workflowStack"]
        print("PASS: installed bridge returned and durably recorded the failing workflow/activity and two-frame call path")
    finally:
        if process.stdin is not None: process.stdin.close()
        try: process.wait(timeout=30)
        except subprocess.TimeoutExpired: process.kill();process.wait()
        reader.join(timeout=2)


if __name__=="__main__":
    main()
