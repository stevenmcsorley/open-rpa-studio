"""Verify saved AI profiles through separate runs of an installed bridge."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def request(executable: Path, data_dir: Path, method: str, params: dict, request_id: int) -> dict:
    env=os.environ.copy()
    env["OPENRPA_DATA_DIR"]=str(data_dir)
    payload={"id":request_id,"method":method,"params":params}
    process=subprocess.run([str(executable)],input=json.dumps(payload)+"\n",capture_output=True,text=True,env=env,timeout=30)
    rows=[json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    if process.returncode or not rows or "error" in rows[0]:
        raise AssertionError({"exit":process.returncode,"stderr":process.stderr,"responses":rows})
    return rows[0]["result"]


def main() -> None:
    if len(sys.argv)!=3:
        raise SystemExit("usage: installed_ai_connections_acceptance.py BRIDGE_EXE DATA_DIRECTORY")
    executable=Path(sys.argv[1]).resolve()
    data_dir=Path(sys.argv[2]).resolve()
    if data_dir.exists() and any(data_dir.iterdir()):
        raise SystemExit(f"Refusing non-empty acceptance directory: {data_dir}")
    data_dir.mkdir(parents=True,exist_ok=True)
    profile={"name":"Acceptance profile","provider":"openai_compatible","baseUrl":"https://api.example/v1",
        "model":"test-model","credentialService":"openrpa-acceptance","credentialUsername":"test-key"}
    saved=request(executable,data_dir,"ai.connections.save",{"profile":profile},1)["profile"]
    listed=request(executable,data_dir,"ai.connections.list",{},2)["profiles"]
    assert listed==[saved],"Profile did not persist across separate bridge processes"
    assert request(executable,data_dir,"ai.connections.delete",{"profileId":saved["id"]},3)["deleted"] is True
    assert request(executable,data_dir,"ai.connections.list",{},4)["profiles"]==[]
    document=json.loads((data_dir/"ai-connections.json").read_text(encoding="utf-8"))
    assert "apiKey" not in str(document) and "secret" not in str(document).lower()
    print("PASS: installed bridge saved profile, persisted across process restart, listed and deleted it; no API-key field stored")


if __name__=="__main__":
    main()
