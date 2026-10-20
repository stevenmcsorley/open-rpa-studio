"""Deterministic Open RPA project archive with path and integrity checks."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
import re
from pathlib import Path, PurePosixPath
from typing import Any
from .model import WorkflowError, load_project, validate_workflow

PACKAGE_FORMAT = "org.openrpa.package"
VERSION = 1
MAX_PACKAGE_FILES = 10000
MAX_PACKAGE_BYTES = 250_000_000
MAX_PACKAGE_FILE_BYTES = 100_000_000
MAX_MANIFEST_BYTES = 1_000_000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "target"}
SKIP_NAMES = {".env", ".env.local", "credentials.json"}
SKIP_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}

def _digest(path: Path) -> str:
    value=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): value.update(chunk)
    return value.hexdigest()

def pack_project(project_path: str|Path, destination: str|Path) -> dict[str,Any]:
    project,root=load_project(project_path)
    for key,relative in project["workflows"].items():
        wf=json.loads((root/relative).read_text(encoding="utf-8"))
        issues=validate_workflow(wf,set(project["workflows"]))
        if issues: raise WorkflowError(f"Cannot package invalid workflow {key}: {issues[0]['message']}",issues[0].get("activityId"),issues[0]["code"])
    target=Path(destination).expanduser().resolve()
    if target.is_relative_to(root): raise WorkflowError("Package output must be outside the project folder",code="package-destination")
    files=[]
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts): continue
        if path.is_symlink() or not path.is_file(): continue
        rel=path.relative_to(root).as_posix()
        if path.name.lower() in SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIXES: continue
        if "\\" in rel or "\x00" in rel or any(":" in part or part.endswith(("."," ")) for part in PurePosixPath(rel).parts):raise WorkflowError(f"Project contains a non-portable package path: {rel}",code="package-path")
        if path.stat().st_size>MAX_PACKAGE_FILE_BYTES:raise WorkflowError(f"Project file exceeds package limit: {rel}",code="package-size-limit")
        files.append((rel,path))
    if len(files)>MAX_PACKAGE_FILES or sum(path.stat().st_size for _,path in files)>MAX_PACKAGE_BYTES:raise WorkflowError("Project exceeds package file or size limit",code="package-size-limit")
    if "project.json" not in {r for r,_ in files}: raise WorkflowError("Project root has no project.json",code="project-format")
    manifest={"format":PACKAGE_FORMAT,"formatVersion":VERSION,"name":project.get("name","Open RPA project"),"files":[{"path":rel,"sha256":_digest(path),"size":path.stat().st_size} for rel,path in files]}
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,temp_name=tempfile.mkstemp(prefix=".openrpa-package-",suffix=".tmp",dir=target.parent);os.close(fd)
    try:
        with zipfile.ZipFile(temp_name,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for rel,path in files:
                info=zipfile.ZipInfo(rel,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16
                with path.open("rb") as source, archive.open(info,"w") as destination_stream:
                    shutil.copyfileobj(source,destination_stream,1024*1024)
            info=zipfile.ZipInfo("package-manifest.json",(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(stat.S_IFREG|0o644)<<16
            archive.writestr(info,json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n")
        os.replace(temp_name,target)
    finally:
        if os.path.exists(temp_name):os.unlink(temp_name)
    return {"path":str(target),"files":len(files),"sha256":_digest(target)}

def unpack_project(package_path: str|Path,destination: str|Path,max_uncompressed_bytes:int=1_000_000_000)->dict[str,Any]:
    source=Path(package_path).expanduser().resolve();target=Path(destination).expanduser().resolve()
    if not source.is_file():raise WorkflowError("Package does not exist",code="package-not-found")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):raise WorkflowError("Package destination must be a new or empty directory",code="package-destination")
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix=".openrpa-unpack-",dir=target.parent))
    try:
        with zipfile.ZipFile(source) as archive:
            infos=archive.infolist()
            if len(infos)>MAX_PACKAGE_FILES+1:raise WorkflowError("Package contains too many entries",code="package-size-limit")
            names=[i.filename for i in infos]
            if len(names)!=len(set(names)):raise WorkflowError("Package contains duplicate entry names",code="package-manifest")
            total=sum(i.file_size for i in infos)
            if total>min(max_uncompressed_bytes,MAX_PACKAGE_BYTES):raise WorkflowError("Package exceeds uncompressed size limit",code="package-size-limit")
            manifest_info=next((i for i in infos if i.filename=="package-manifest.json"),None)
            if manifest_info is None:raise WorkflowError("Package manifest is missing",code="package-manifest")
            if manifest_info.file_size>MAX_MANIFEST_BYTES:raise WorkflowError("Package manifest is too large",code="package-size-limit")
            manifest=json.loads(archive.read(manifest_info))
            if not isinstance(manifest,dict) or manifest.get("format")!=PACKAGE_FORMAT or manifest.get("formatVersion")!=VERSION:raise WorkflowError("Unsupported package format",code="package-version")
            rows=manifest.get("files")
            if not isinstance(rows,list) or len(rows)>MAX_PACKAGE_FILES:raise WorkflowError("Package file manifest is invalid",code="package-manifest")
            declared={}
            for row in rows:
                if not isinstance(row,dict) or not isinstance(row.get("path"),str):raise WorkflowError("Package file manifest is invalid",code="package-manifest")
                rel_name=row["path"]
                if rel_name in declared:raise WorkflowError("Package manifest contains duplicate paths",code="package-manifest")
                manifest_path=PurePosixPath(rel_name)
                if "\\" in rel_name or "\x00" in rel_name or manifest_path.is_absolute() or not manifest_path.parts or ".." in manifest_path.parts or any(":" in part for part in manifest_path.parts):raise WorkflowError(f"Unsafe package path: {rel_name}",code="package-path")
                if not isinstance(row.get("size"),int) or row["size"]<0 or row["size"]>MAX_PACKAGE_FILE_BYTES or not re.fullmatch(r"[0-9a-f]{64}",str(row.get("sha256",""))):raise WorkflowError("Package file metadata is invalid",code="package-manifest")
                declared[rel_name]=row
            actual={i.filename for i in infos if i.filename!="package-manifest.json"}
            if actual!=set(declared):raise WorkflowError("Package file list does not match manifest",code="package-manifest")
            for info in infos:
                if info.filename=="package-manifest.json":continue
                rel=PurePosixPath(info.filename)
                if "\\" in info.filename or "\x00" in info.filename or rel.is_absolute() or not rel.parts or ".." in rel.parts or any(":" in part for part in rel.parts) or any(part.endswith(("."," ")) for part in rel.parts):raise WorkflowError(f"Unsafe package path: {info.filename}",code="package-path")
                if info.is_dir() or info.file_size>MAX_PACKAGE_FILE_BYTES:raise WorkflowError(f"Unsupported package entry: {info.filename}",code="package-size-limit")
                if info.compress_size and info.file_size/info.compress_size>200:raise WorkflowError(f"Package compression ratio is excessive: {info.filename}",code="package-size-limit")
                mode=(info.external_attr>>16)&0o170000
                if mode==stat.S_IFLNK:raise WorkflowError(f"Symlinks are not allowed in packages: {info.filename}",code="package-path")
                record=declared[info.filename]
                if record["size"]!=info.file_size:raise WorkflowError(f"Package size metadata mismatch: {info.filename}",code="package-integrity")
                output=staging.joinpath(*rel.parts).resolve()
                try:output.relative_to(staging.resolve())
                except ValueError as exc:raise WorkflowError(f"Unsafe package path: {info.filename}",code="package-path") from exc
                output.parent.mkdir(parents=True,exist_ok=True)
                digest=hashlib.sha256();written=0
                with archive.open(info) as source_stream, output.open("wb") as destination_stream:
                    for chunk in iter(lambda:source_stream.read(1024*1024),b""):
                        written+=len(chunk)
                        if written>MAX_PACKAGE_FILE_BYTES:raise WorkflowError("Package entry exceeded size limit",code="package-size-limit")
                        digest.update(chunk);destination_stream.write(chunk)
                if written!=record["size"] or digest.hexdigest()!=record["sha256"]:raise WorkflowError(f"Package integrity check failed: {info.filename}",code="package-integrity")
        if not (staging/"project.json").is_file():raise WorkflowError("Packaged project.json is missing",code="package-project")
        load_project(staging/"project.json")
        if target.exists():target.rmdir()
        staging.replace(target)
        return {"path":str(target),"files":len(declared),"name":manifest.get("name")}
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise
