"""Frozen console entry point for Studio IPC and the local CLI/MCP server."""
import sys


if __name__ == "__main__":
    if len(sys.argv) > 1:
        from openrpa.cli import main
        raise SystemExit(main())
    from openrpa.bridge import main
    main()
