from __future__ import annotations
import argparse
import json
from pathlib import Path
from .engine import run_project
from .model import load_project, WorkflowError, validate_workflow


def main() -> int:
    parser = argparse.ArgumentParser(prog="openrpa", description="Validate or run a local Open RPA Studio project")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "run"):
        cmd = sub.add_parser(command)
        cmd.add_argument("project", help="Project directory or project.json")
        if command == "run":
            cmd.add_argument("--workflow")
            cmd.add_argument("--allow-network", action="store_true")
            cmd.add_argument("--allow-desktop", action="store_true")
            cmd.add_argument("--allow-destructive", action="store_true", help="Permit destructive file and API DELETE activities for this run")
    mcp = sub.add_parser("mcp", help="Expose one local project to an AI client over stdio MCP")
    mcp.add_argument("project", help="Project directory or project.json; fixed for this server process")
    mcp.add_argument("--allow-edit", action="store_true", help="Expose validated workflow replacement with an expected SHA-256")
    mcp.add_argument("--allow-run", action="store_true", help="Expose workflow execution to the MCP client")
    mcp.add_argument("--allow-network", action="store_true", help="Permit HTTP activities if execution is enabled")
    mcp.add_argument("--allow-desktop", action="store_true", help="Permit desktop activities if execution is enabled")
    mcp.add_argument("--allow-credentials", action="store_true", help="Permit reading OS-vault credentials if execution is enabled")
    mcp.add_argument("--allow-destructive", action="store_true", help="Permit file delete/move and API DELETE activities if execution is enabled")
    pack = sub.add_parser("pack", help="Create a deterministic .orpa project package")
    pack.add_argument("project")
    pack.add_argument("output")
    unpack = sub.add_parser("unpack", help="Verify and extract a .orpa project package")
    unpack.add_argument("package")
    unpack.add_argument("destination")
    credential = sub.add_parser("credential", help="Store a credential in the operating-system vault")
    credential.add_argument("service")
    credential.add_argument("username")
    args = parser.parse_args()
    try:
        if args.command == "mcp":
            from .mcp_server import ProjectMCPServer
            server = ProjectMCPServer(args.project, allow_run=args.allow_run,
                                      allow_edit=args.allow_edit,
                                      allow_network=args.allow_network, allow_desktop=args.allow_desktop,
                                      allow_credentials=args.allow_credentials,
                                      allow_destructive=args.allow_destructive)
            return server.serve()
        if args.command == "credential":
            from getpass import getpass
            from .credentials import get_safe_keyring
            try:
                vault=get_safe_keyring()
                secret=getpass("Secret (input hidden): ")
                confirm=getpass("Confirm secret: ")
                if not secret or secret!=confirm:
                    print("Secret was empty or the confirmation did not match.")
                    return 2
                vault.set_password(args.service,args.username,secret)
                print(f"Stored credential for {args.username!r} in the OS credential vault.")
                return 0
            except Exception as exc:
                print(f"Credential setup failed: {exc}")
                return 2
        if args.command == "pack":
            from .package import pack_project
            print(json.dumps(pack_project(args.project,args.output),indent=2))
            return 0
        if args.command == "unpack":
            from .package import unpack_project
            print(json.dumps(unpack_project(args.package,args.destination),indent=2))
            return 0
        project, root = load_project(args.project)
        if args.command == "validate":
            problems = []
            for key, rel in project["workflows"].items():
                workflow = json.loads((root / rel).read_text(encoding="utf-8"))
                problems.extend({"workflow": key, **p} for p in validate_workflow(workflow, set(project["workflows"])))
            print(json.dumps({"valid": not problems, "problems": problems}, indent=2))
            return 0 if not problems else 2
        from .engine import RunOptions
        result = run_project(project, root, args.workflow, options=RunOptions(allow_network=args.allow_network,allow_desktop=args.allow_desktop,allow_destructive=args.allow_destructive))
        print(json.dumps(result.__dict__, indent=2, ensure_ascii=False, default=str))
        return 0 if result.status == "succeeded" else 1
    except WorkflowError as exc:
        if args.command == "mcp":
            import sys
            print(f"Open RPA MCP startup failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"valid": False, "error": {"code": exc.code, "message": str(exc), "activityId": exc.activity_id}}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
