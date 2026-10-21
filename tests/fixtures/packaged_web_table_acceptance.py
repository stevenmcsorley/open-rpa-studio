"""Confirm the frozen bridge exposes and validates the bounded web-table activity."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

binary=Path(sys.argv[1]).resolve()
project={"format":"openrpa.project","formatVersion":1,"name":"Packaged web table acceptance","main":"Main","workflows":{"Main":"main.json"}}
workflow={"format":"openrpa.workflow","formatVersion":1,"name":"Main","variables":[],"arguments":[],"activities":[{"id":"table","type":"browser_table_read","selectorKind":"css","selector":"table#results","firstRowHeaders":True,"maxRows":25,"maxColumns":8,"maxOutputChars":50000,"result":"rows","timeoutSeconds":10}]}
requests=[{"id":1,"method":"activity.catalog","params":{}},{"id":2,"method":"workflow.validate","params":{"project":project,"workflow":workflow}}]
completed=subprocess.run([str(binary)],input="".join(json.dumps(item)+"\n" for item in requests),capture_output=True,text=True,timeout=45,check=False)
if completed.returncode:
    raise SystemExit(f"Frozen bridge exited {completed.returncode}: {completed.stderr[-1000:]}")
responses=[json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
if len(responses)!=2 or [item.get("id") for item in responses]!=[1,2]:
    raise SystemExit(f"Unexpected frozen bridge response: {completed.stdout[-1000:]}")
catalog=responses[0].get("result",[])
if not any(item.get("type")=="browser_table_read" for item in catalog):
    raise SystemExit("Frozen bridge activity catalog lacks browser_table_read")
validation=responses[1].get("result",{})
if validation.get("valid") is not True:
    raise SystemExit(f"Frozen bridge rejected the valid web-table activity: {validation!r}")
print("Frozen bridge exposes Read Web Table and validates its bounded configuration")
