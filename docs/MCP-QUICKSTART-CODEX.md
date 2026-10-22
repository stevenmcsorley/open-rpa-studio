# Open RPA Studio MCP — Codex quick start

This connects Codex to the **local Open RPA Studio MCP bridge**. It does not connect an AI provider (such as DeepSeek) directly to MCP. Codex launches the bridge as a private stdio process; there is no MCP terminal window to keep open.

## 1. Open the project in Studio

Open Open RPA Studio and the project you want Codex to manage. The bridge follows Studio's active project while Studio is open. The project path in the configuration is only the fallback used if Studio has not published an active project.

## 2. Find the bridge shipped with your installed version

In PowerShell, run:

```powershell
$bridge = Get-ChildItem "$env:LOCALAPPDATA\Programs\Open RPA Studio\engine\openrpa-bridge-*.exe" |
  Sort-Object { [version]($_.BaseName -replace '^openrpa-bridge-', '') } -Descending |
  Select-Object -First 1
$bridge.FullName
```

If this returns nothing, locate the per-user installation in Windows Settings → Installed apps, or reinstall the current Studio release. Do not point Codex at a bridge copied from the source tree or an older release. The bridge and desktop app should be from the same release.

## 3. Add the server to Codex

Open `%USERPROFILE%\.codex\config.toml` and add a server entry. Replace the bridge path and fallback project path with paths that exist on your computer:

```toml
[mcp_servers.open_rpa_studio]
command = 'C:\Users\YOUR_NAME\AppData\Local\Programs\Open RPA Studio\engine\openrpa-bridge-0.1.128.exe'
args = [
  'mcp',
  'C:\Users\YOUR_NAME\Documents\Automation\MyProject\project.json',
  '--allow-edit'
]
startup_timeout_sec = 30
tool_timeout_sec = 120
```

Restart Codex after changing `config.toml`. In Codex, call `openrpa_project_info` and check `projectBinding` is `studio-active` before editing. Then use `openrpa_stage_workflow_draft` to show validated construction on the Studio canvas, `openrpa_validate_workflow_drafts` to check a draft, and `openrpa_create_workflow` or `openrpa_update_workflow` to save it.

The example grants workflow editing only. Add startup flags only for capabilities you want the connected agent to use:

| Flag | Enables |
|---|---|
| `--allow-run` | Workflow execution and the local job queue |
| `--allow-network` | HTTP and browser network operations during an allowed run |
| `--allow-desktop` | Desktop activities; direct live browser MCP controls also require run and network grants |
| `--allow-credentials` | Reading credential values from the OS credential vault during allowed runs |
| `--allow-destructive` | File move/delete and other explicitly destructive activities; MCP workflow deletion additionally requires `--allow-edit` |

Permissions are fixed when Codex starts the MCP process. If a needed tool is absent, update the flags and restart Codex. The host can invoke every tool the bridge advertises, so grant only the capabilities appropriate for the project.

Recurring schedules can be managed from Studio's **Workflow Manager → Schedules** view or through `openrpa_create_schedule`, `openrpa_list_schedules`, `openrpa_set_schedule_enabled`, and `openrpa_delete_schedule`. They execute only while an Open RPA MCP process for the project is running with `--allow-run` and the workflow's required grants. The schedule pins the workflow version; editing it pauses the schedule so a changed automation never runs silently. See [local job orchestration](LOCAL-JOB-ORCHESTRATION.md) for cron syntax and missed-run behavior.

## Troubleshooting

- **No Open RPA tools appear:** restart Codex, inspect its MCP server status, and check that `command` points to an existing versioned bridge executable.
- **Wrong project:** leave Studio open with the intended project selected; verify `projectBinding` is `studio-active` and check the project name returned by `openrpa_project_info`.
- **Draft appears only after completion:** ask Codex to call `openrpa_stage_workflow_draft` after each meaningful increment. Draft validation alone does not update the canvas.
- **Edit or run tools are missing:** MCP permissions are startup flags. Add `--allow-edit` or `--allow-run` as appropriate, then restart Codex.
- **Bridge/app version mismatch:** use the executable installed beside the running Studio release. Reinstalling Studio may change the versioned executable name; update the config path afterward.
- **No terminal window:** this is expected. Codex starts the stdio server in the background and owns its lifecycle.

See [MCP integration](MCP-INTEGRATION.md) for the complete protocol, tool and security reference. See [local job orchestration](LOCAL-JOB-ORCHESTRATION.md) for scheduling guarantees and limitations.
