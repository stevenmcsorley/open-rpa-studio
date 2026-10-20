#!/usr/bin/env python3
"""Generate a CycloneDX inventory from the checked-in Python/Node/Rust locks."""
from __future__ import annotations

import argparse
import base64
import json
import re
import tomllib
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def component(kind: str,name: str,version: str,purl: str,license_value: str|None=None,hashes: list[dict]|None=None,url: str|None=None) -> dict:
    row={"type":"library","name":name,"version":version,"purl":purl,"bom-ref":purl}
    if license_value:
        row["licenses"]=[{"expression":license_value}]
    else:
        row["properties"]=[{"name":"openrpa:licenseReview","value":"Not present in the dependency lockfile; verify upstream metadata before redistribution."}]
    if hashes: row["hashes"]=hashes
    if url: row["externalReferences"]=[{"type":"distribution","url":url}]
    row["properties"]=[*(row.get("properties",[])),{"name":"openrpa:ecosystem","value":kind}]
    return row


def build() -> dict:
    components=[]
    python_lock=tomllib.loads((ROOT/"uv.lock").read_text(encoding="utf-8"))
    for package in python_lock.get("package",[]):
        name=package["name"];version=package["version"]
        artifacts=[]
        sdist=package.get("sdist")
        if sdist and sdist.get("hash"):
            match=re.fullmatch(r"sha256:(.+)",sdist["hash"])
            if match: artifacts.append({"alg":"SHA-256","content":match.group(1)})
        if not artifacts:
            for wheel in package.get("wheels",[]):
                match=re.fullmatch(r"sha256:(.+)",wheel.get("hash",""))
                if match: artifacts.append({"alg":"SHA-256","content":match.group(1)})
        components.append(component("python",name,version,f"pkg:pypi/{name}@{version}",hashes=artifacts[:1]))

    npm=json.loads((ROOT/"package-lock.json").read_text(encoding="utf-8"))
    for path,package in npm.get("packages",{}).items():
        name=package.get("name")
        version=package.get("version")
        if not name or not version or path=="": continue
        sri=package.get("integrity","")
        hashes=[]
        match=re.fullmatch(r"sha512-(.+)",sri)
        if match:
            try: hashes=[{"alg":"SHA-512","content":base64.b64decode(match.group(1)).hex()}]
            except Exception: pass
        license_value=package.get("license")
        components.append(component("npm",name,version,f"pkg:npm/{name}@{version}",license_value,hashes,package.get("resolved")))

    rust=tomllib.loads((ROOT/"src-tauri"/"Cargo.lock").read_text(encoding="utf-8"))
    for package in rust.get("package",[]):
        name=package["name"];version=package["version"]
        if name=="open-rpa-studio" and not package.get("source"): continue
        checksum=package.get("checksum")
        hashes=[{"alg":"SHA-256","content":checksum}] if checksum else []
        components.append(component("cargo",name,version,f"pkg:cargo/{name}@{version}",hashes=hashes,url=package.get("source")))

    components=sorted(components,key=lambda row:(row.get("purl", "")))
    component_identity="\n".join(f"{row.get('purl','')}@{row.get('version','')}" for row in components)
    serial=uuid.uuid5(uuid.NAMESPACE_URL,"open-rpa-studio-sbom:"+component_identity)
    return {"bomFormat":"CycloneDX","specVersion":"1.5","serialNumber":f"urn:uuid:{serial}","version":1,
            "metadata":{"component":{"type":"application","name":"Open RPA Studio","version":"0.1.0","purl":"pkg:generic/open-rpa-studio@0.1.0"},
                        "properties":[{"name":"openrpa:lockfiles","value":"uv.lock, package-lock.json, src-tauri/Cargo.lock"}]},
            "components":components}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="sbom.cdx.json")
    args=parser.parse_args()
    destination=Path(args.output)
    if not destination.is_absolute(): destination=ROOT/destination
    destination.write_text(json.dumps(build(),indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Wrote {destination} with {len(build()['components'])} locked dependency components")
