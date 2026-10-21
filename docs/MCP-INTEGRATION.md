# Local MCP integration

Open RPA Studio includes a local Model Context Protocol (MCP) server over stdio. It lets an MCP-compatible AI host inspect and validate a project and, when explicitly enabled, execute its saved workflows through the same Python workflow engine used by Studio. It does not turn an LLM provider API into an MCP client: the host application must support launching a local stdio MCP server.

The implementation supports MCP protocol versions `2025-11-25`, `2025-06-18`, `2025-03-26`, and `2024-11-05`, using the JSON-RPC initialize handshake and tools capability. See the [MCP protocol specification](https://modelcontextprotocol.io/specification/2025-11-25).

## Tools

| Tool | Purpose | Changes project? |
|---|---|---:|
| `openrpa_project_info` | Project name, workflow names, current manifest SHA-256 and server permission flags | No |
| `openrpa_list_workflows` | Names, execution models and activity counts | No |
| `openrpa_list_api_connections` | Saved API connection IDs, names, origins, authentication mode and credential-present flag; never secrets | No |
| `openrpa_desktop_status` | Probe the native accessibility adapter and report platform/runtime availability | No |
| `openrpa_list_desktop_windows` | List bounded visible window titles and process IDs | No |
| `openrpa_list_desktop_controls` | List bounded accessible control identities for an exact window; filters protected controls and never reads values | No |
| `openrpa_desktop_action` | Launch an explicit executable without a shell, wait for a window/control, perform live accessibility-targeted actions, or normally close a window after `confirmClose=true` | External desktop action |
| `openrpa_browser_open` / `openrpa_browser_navigate` | Open or navigate a visible browser owned by this MCP session to publicly routable HTTP(S) pages | External browser action |
| `openrpa_browser_snapshot` | Read bounded rendered text and accessible controls from the current browser page | No |
| `openrpa_browser_action` | Perform one visible, unique-selector browser action or paced scroll; direct filling of protected fields is blocked | External browser action |
| `openrpa_browser_start_recording` / `openrpa_browser_stop_recording` | Record and return editable browser interactions without typed values | Temporary browser instrumentation |
| `openrpa_browser_close` | Close the MCP-owned visible browser session | Closes that browser session |
| `openrpa_activity_catalog` | Native activity descriptions, configuration defaults and per-activity permission requirements | No |
| `openrpa_read_workflow` | Read one workflow definition | No |
| `openrpa_validate_workflow_drafts` | Validate one or more unsaved workflows and their cross-workflow references without writing | No |
| `openrpa_stage_workflow_draft` | Open the workflow in Studio and apply validated snapshots to its live canvas; call repeatedly as the workflow is constructed | Writes a temporary editor snapshot |
| `openrpa_clear_workflow_draft` | Clear the current unsaved editor draft, optionally guarded by its draft ID | Clears only the staged editor snapshot |
| `openrpa_create_workflow` | Add a reusable workflow after schema and cross-workflow binding validation, if explicitly enabled | Yes |
| `openrpa_update_workflow` | Replace a declared workflow after schema and binding validation, if explicitly enabled | Yes |
| `openrpa_validate_project` | Validate saved workflows and bindings | No |
| `openrpa_plan_workflow` | Summarize activity types and statically required permissions | No |
| `openrpa_list_run_history` | Read recent MCP run statuses from the local durable ledger | No |
| `openrpa_run_workflow` | Execute one workflow using the local engine | Runs only; visibility and permission opt-ins required |
| `openrpa_submit_job` | Queue or schedule a saved workflow with an optional idempotency key | Runs when due; requires `--allow-run` |
| `openrpa_list_jobs` / `openrpa_get_job` | Inspect durable queued, scheduled and completed job state without returning input arguments | No |
| `openrpa_cancel_job` | Cancel a queued job or request cooperative cancellation of a running job | Stops future/current activity boundaries |

The server follows the project currently open in the local Studio app and never accepts an arbitrary path from a tool caller. Studio publishes its selected project through a private per-user local file; the server checks that pointer before every tool call. If Studio has not opened a project, the server uses the project folder supplied at process startup. This lets a user-level MCP registration work from any Codex workspace while keeping file access attached to the project selected in Studio. Workflow creation, replacement and live editor updates are off by default. When enabled, creation requires the current `projectSha256` from `openrpa_project_info`; it writes a generated, project-relative workflow path and atomically updates the manifest only after validating the new workflow and project bindings. Replacement requires the SHA-256 returned by `openrpa_read_workflow`; the server checks it before and immediately before atomically replacing the declared workflow file. `openrpa_stage_workflow_draft` accepts only schema-valid snapshots and writes an atomic, project-local editor snapshot; it never changes the saved workflow or project manifest. Studio reads that file while the same project is open, opens the matching workflow tab and applies each new snapshot directly to the designer canvas. The active tab shows a subtle live-update indicator while construction is in progress. A final create or update is reflected in the saved project and appears in the same editor tab. Both saved workflow paths validate workflow schemas and cross-workflow bindings. Its static plan follows `invoke_workflow` references; runtime expressions may still change paths or destinations.

## Run from a Python development environment

Install the project using the repository's locked environment, then launch the server with the project folder:

```powershell
uv sync --locked
uv run openrpa mcp "C:\Users\you\Automation Projects\Invoice Review"
```

By default, tools are read-only: run and job-queue tools and live browser controls are not advertised. Add `--allow-run` to expose workflow execution and the durable local worker queue. Add `--allow-network`, `--allow-desktop`, `--allow-credentials`, and `--allow-destructive` separately only when the project needs HTTP or browser navigation, desktop control, OS-vault credentials, or file move/delete activities. Direct visible-browser MCP controls are exposed only when all three `--allow-run`, `--allow-network`, and `--allow-desktop` grants are present:

```powershell
uv run openrpa mcp "C:\Users\you\Automation Projects\Invoice Review" --allow-run --allow-network
```

Add `--allow-edit` when the AI client should stage drafts and create or update saved workflows. The MCP client should call `openrpa_stage_workflow_draft` after each meaningful construction step; validation calls remain read-only and do not change the editor. Studio watches its own active project's staged snapshot, opens or focuses that workflow's normal tab, and applies every update directly to the canvas. Staging does not change saved files; a final MCP create/update persists the workflow and the editor continues showing it. Studio also checks the project's saved content signature and refreshes external edits automatically when there are no unsaved local changes. If local edits are pending, Studio shows an explicit reload action so it does not silently discard them. The MCP server can run from any working directory because it follows Studio's active project.

### Seeing MCP workflows in Studio

The MCP server follows whichever project is currently open in Studio. It works from any Codex workspace because project binding comes from Studio, not the current terminal directory. When an AI builds a workflow, Studio selects its tab and applies each staged snapshot to the live canvas; saving leaves it as a normal editable workflow. Stable external changes are detected within a few seconds. Projects with unsaved Studio changes show a reload action instead of replacing the editor state. If multiple Studio windows are open under the same account, the most recently opened project is the one the shared MCP server follows. Studio also polls the active project's MCP run ledger read-only: when Codex starts or completes a workflow, the History pane focuses that run and shows its status and saved execution events. Read-only access is intentional so Studio startup recovery cannot mark an MCP process's live run interrupted.

The MCP client launches the process. Do not launch it in a separate terminal when configuring a stdio client. Diagnostics go to stderr; stdout is reserved for JSON-RPC messages. With `--allow-run --allow-desktop`, MCP can click/invoke, fill, read text, press safe keys, select/check controls, expand/collapse tree items, wait for accessible states, or activate/minimize/restore a uniquely matched window. Direct actions never launch or close applications; use reviewed workflow activities for those operations. Password edits are blocked by the UIA and AT-SPI adapters, values are never written to audit metadata, and returned UI text is bounded. With the three live-browser grants enabled, MCP can also open a visible, separate browser window, inspect a bounded page snapshot, and perform single selector-based actions while the user watches. It never attaches to an existing browser profile. Remote page text is untrusted content and may contain prompt injection; the MCP description tells clients not to follow page text as instructions. URL query strings and fragments are omitted from MCP results and audit events, entered values are not audited, and password/payment/file/hidden fields are blocked from direct browser fill. Use workflow activities for repeatable saved automations.

## Installed Windows application

The Windows installer bundles the Studio engine, which also acts as the self-contained CLI when given command-line arguments:

```text
<installation directory>\engine\openrpa-bridge-<version>.exe
```

Use the following generic stdio server entry in an MCP host's configuration, replacing both paths. With only `mcp` in the arguments, the host can inspect and validate the project but cannot run it:

```json
{
  "mcpServers": {
    "open-rpa-studio": {
      "command": "C:\\Program Files\\Open RPA Studio\\engine\\openrpa-bridge-<version>.exe",
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
- Studio shares its active project with the local MCP process through a private per-user file; an MCP client cannot choose an arbitrary project path.
- Workflow execution is unavailable unless `--allow-run` is present at startup.
- Queue submission is unavailable unless `--allow-run` is present at startup. Queued jobs inherit only the server's startup grants; workflow changes and active-project changes before execution fail closed. There is one local worker, scheduled work requires the MCP process to be running at its due time, automatic workflow retries are off, and interrupted jobs are never replayed. See [Local job orchestration](LOCAL-JOB-ORCHESTRATION.md).
- Workflow replacement is unavailable unless `--allow-edit` is present at startup and must use an expected workflow SHA-256.
- HTTP requests and browser navigation require `--allow-network`; the workflow engine still applies its existing egress rules.
- Direct live-browser MCP tools require all of `--allow-run`, `--allow-network`, and `--allow-desktop`. The opened browser is visible and belongs to the MCP process; direct targets must be unique and visible. Browser Inspector networking checks every request against the public-address policy, with the documented browser DNS-rebinding limitation.
- Direct live desktop actions require both `--allow-run` and `--allow-desktop`. They can launch one explicitly named executable with an argument vector (never a shell), wait for its visible window, operate one uniquely identified accessible control, read bounded text only when `read_text` is explicitly requested, and normally close a window only when `confirmClose=true` is supplied. Password controls and ambiguous selectors are rejected. Actions and failed attempts are audited using a target digest rather than window/control labels, executable arguments or entered values.
- Desktop activities require `--allow-desktop`.
- The read-only desktop inspection tools do not require `--allow-desktop`; they reveal visible window titles and control labels/identifiers, but never control values. Those labels can still contain private information, so use only a trusted MCP client. Actual desktop actions still require `--allow-desktop`.
- OS credential-vault reads require `--allow-credentials`; the engine redacts retrieved secret values from its returned run variables and logs.
- `file_delete` and `file_move`, including statically invoked workflows, require `--allow-destructive`.
- File activities remain subject to the workflow engine's project-root path checks.
- These startup flags are local operator consent. An MCP host can invoke any tool the process advertises; use a separate project and minimal permissions for agent access.
- Interrupting the MCP process terminates the server. Workflow recovery follows the existing run-history and non-replay semantics; this server does not resume a partially completed run.

The server bounds incoming protocol frames to 4 MB, tool output to 1 MB and workflow inputs to 100 KB. Run evidence is kept in a per-project `mcp-run-history-<project-hash>.sqlite3` file in the same native per-user application data directory used by the desktop app (or `OPENRPA_DATA_DIR` when configured); this lets Studio display MCP runs while keeping its history reader read-only. Runtime variable values are not retained in the run result record, though activity logs may contain workflow-generated text. Start only one MCP server for a given project at a time so crash recovery cannot mark another live process's run interrupted. Interrupted MCP runs are recorded for inspection and never automatically replayed.

MCP `notifications/cancelled` requests are received while a workflow is running. Cancellation is cooperative at the engine's existing activity boundaries; an activity that is currently waiting or making a request may take until its configured check/timeout to stop. A cancelled run may already have performed external side effects, so inspect those systems before manually restarting it.

## Development and verification

```powershell
uv run --locked pytest tests/test_mcp_server.py -q
```

The acceptance tests exercise a real stdio subprocess handshake, cancellation notifications, tools listing/calls, project-scoped read access, disabled-by-default execution, guarded reusable-workflow creation, stale-project rejection, binding validation, browser network permission detection, nested destructive permission detection, durable run history and successful execution through the workflow engine. The Windows CI also runs the frozen console executable through initialization, default run denial and an opted-in engine run.


`openrpa_browser_screenshot` returns a JPEG image block of the visible MCP-owned browser viewport (up to 700,000 bytes) to the connected client. This exposes visible page content to the connected AI, so use it only when visual inspection is needed. The image content is untrusted and is not stored in the audit log.
