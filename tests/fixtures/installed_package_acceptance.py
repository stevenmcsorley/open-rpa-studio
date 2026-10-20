"""Exercise package import/export operations through a frozen installed bridge."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def request(executable: Path, data_dir: Path, method: str, params: dict, request_id: int) -> dict:
    env=os.environ.copy()
    env["OPENRPA_DATA_DIR"]=str(data_dir)
    process=subprocess.run([str(executable)],input=json.dumps({"id":request_id,"method":method,"params":params})+"\n",
        capture_output=True,text=True,env=env,timeout=30)
    rows=[json.loads(line) for line in process.stdout.splitlines() if line.strip()]
    if process.returncode or not rows or "error" in rows[0]:
        raise AssertionError({"exit":process.returncode,"stderr":process.stderr,"responses":rows})
    return rows[0]["result"]


def main() -> None:
    if len(sys.argv)!=3:
        raise SystemExit("usage: installed_package_acceptance.py BRIDGE_EXE ACCEPTANCE_ROOT")
    executable=Path(sys.argv[1]).resolve()
    root=Path(sys.argv[2]).resolve()
    if root.exists():
        raise SystemExit(f"Refusing existing acceptance root: {root}")
    data=root/"bridge-data";source=root/"source";archive=root/"automation.orpa";destination=root/"imported"
    created=request(executable,data,"project.create",{"path":str(source),"name":"Package acceptance"},1)
    exported=request(executable,data,"project.package.export",{"root":created["root"],"destination":str(archive)},2)
    assert exported["files"]==2 and len(exported["sha256"])==64
    imported=request(executable,data,"project.package.import",{"package":str(archive),"destination":str(destination)},3)
    assert imported["name"]=="Package acceptance" and imported["files"]==2
    assert imported["sha256"]==exported["sha256"]
    assert (destination/"project.json").is_file() and (destination/"workflows"/"main.workflow.json").is_file()
    print(f"PASS: installed bridge exported and verified/imported {imported['files']} project files; archive SHA-256 {exported['sha256']}")


if __name__=="__main__":
    main()
