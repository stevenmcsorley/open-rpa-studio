# Local MCP integration

Open RPA Studio includes a local Model Context Protocol (MCP) server over stdio. It lets an MCP-compatible AI host inspect and validate a project and, when explicitly enabled, execute its saved workflows through the same Python workflow engine used by Studio. It does not turn an LLM provider API into an MCP client: the host application must support launching a local stdio MCP server.

The implementation supports MCP protocol versions `2025-11-25`, `2025-06-18`, `2025-03-26`, and `2024-11-05`, using the JSON-RPC initialize handshake and tools capability. See the [MCP protocol specification](https://modelcontextprotocol.io/specification/2025-11-25).

## Tools

| Tool | Purpose | Changes project? |
|---|---|---:|
| `openrpa_project_info` | Project name, workflow names and server permission flags | No |
| `openrpa_list_workflows` | Names, execution models and activity counts | No |
| `openrpa_read_workflow` | Read one workflow definition | No |
| `openrpa_update_workflow` | Replace a declared workflow after schema and binding validation, if explicitly enabled | Yes |
| `openrpa_validate_project` | Validate saved workflows and bindings | No |
| `openrpa_plan_workflow` | Summarize activity types and statically required permissions | No |
| `openrpa_list_run_history` | Read recent MCP run statuses from the local durable ledger | No |
| `openrpa_run_workflow` | Execute one workflow using the local engine | Runs only; visibility and permission opt-ins required |

The server binds to one project path supplied at process startup and never accepts an arbitrary path from a tool caller. Workflow replacement is off by default. When enabled, clients must send the SHA-256 returned by `openrpa_read_workflow`; the server checks it before and immediately before atomically replacing the declared workflow file. It validates the full workflow schema and cross-workflow bindings. Its static plan follows `invoke_workflow` references; runtime expressions may still change paths or destinations.

## Run from a Python development environment

Install the project using the repository's locked environment, then launch the server with the project folder:

```powershell
uv sync --locked
uv run openrpa mcp "C:\Users\you\Automation Projects\Invoice Review"
```

By default, tools are read-only: the run tool is not advertised. Add `--allow-run` to expose workflow execution. Add `--allow-network`, `--allow-desktop`, `--allow-credentials`, and `--allow-destructive` separately only when the project needs HTTP, desktop control, OS-vault credentials, or file move/delete activities:

```powershell
uv run openrpa mcp "C:\Users\you\Automation Projects\Invoice Review" --allow-run --allow-network
```

Add `--allow-edit` only when the AI client should be able to update saved workflows. Do not edit the same project simultaneously in Studio; an already-open editor can later save stale in-memory content over an MCP edit. Reopen the project in Studio after agent edits. Use one MCP server process per project.

The MCP client launches the process. Do not launch it in a separate terminal when configuring a stdio client. Diagnostics go to stderr; stdout is reserved for JSON-RPC messages.

## Installed Windows application

The Windows installer bundles the Studio engine, which also acts as the self-contained CLI when given command-line arguments:

```text
<installation directory>\engine\openrpa-bridge.exe
```

Use the following generic stdio server entry in an MCP host's configuration, replacing both paths. With only `mcp` in the arguments, the host can inspect and validate the project but cannot run it:

```json
{
  "mcpServers": {
    "open-rpa-studio": {
      "command": "C:\\Program Files\\Open RPA Studio\\engine\\openrpa-bridge.exe",
      "args": [
        "mcp",
        "C:\\Users\\you\\Automation Projects\\Invoice Review"
      ]
    }
  }
}
```

To permit workflow execution, append `--allow-run` to `args`. To permit validated workflow updates, append `--allow-edit`. Add the other flags only after reviewing the workflow and its affected systems. A project may contain private literals and data; `openrpa_read_workflow` sends the workflow definition to the MCP host, and workflow execution can read/write project files. Only connect trusted AI clients and review their data handling.

## Boundaries and permissions

- No TCP, HTTP, cloud or external service listener is created by this MCP server.
- Workflow execution is unavailable unless `--allow-run` is present at startup.
- Workflow replacement is unavailable unless `--allow-edit` is present at startup and must use an expected workflow SHA-256.
- HTTP activities require `--allow-network`; the workflow engine still applies its existing egress rules.
- Desktop activities require `--allow-desktop`.
- OS credential-vault reads require `--allow-credentials`; the engine redacts retrieved secret values from its returned run variables and logs.
- `file_delete` and `file_move`, including statically invoked workflows, require `--allow-destructive`.
- File activities remain subject to the workflow engine's project-root path checks.
- These startup flags are local operator consent. An MCP host can invoke any tool the process advertises; use a separate project and minimal permissions for agent access.
- Interrupting the MCP process terminates the server. Workflow recovery follows the existing run-history and non-replay semantics; this server does not resume a partially completed run.

The server bounds incoming protocol frames to 4 MB, tool output to 1 MB and workflow inputs to 100 KB. Run evidence is kept in a per-project `mcp-run-history-<project-hash>.sqlite3` file in the normal application data directory (or `OPENRPA_DATA_DIR` when configured); runtime variable values are not retained in the run result record, though activity logs may contain workflow-generated text. Start only one MCP server for a given project at a time so crash recovery cannot mark another live process's run interrupted. Interrupted MCP runs are recorded for inspection and never automatically replayed.

MCP `notifications/cancelled` requests are received while a workflow is running. Cancellation is cooperative at the engine's existing activity boundaries; an activity that is currently waiting or making a request may take until its configured check/timeout to stop. A cancelled run may already have performed external side effects, so inspect those systems before manually restarting it.

## Development and verification

```powershell
uv run --locked pytest tests/test_mcp_server.py -q
```

The acceptance tests exercise a real stdio subprocess handshake, cancellation notifications, tools listing/calls, project-scoped read access, disabled-by-default execution, nested destructive permission detection, durable run history and successful execution through the workflow engine. The Windows CI also runs the frozen console executable through initialization, default run denial and an opted-in engine run.
