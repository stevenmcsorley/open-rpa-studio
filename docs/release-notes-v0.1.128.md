## Open RPA Studio 0.1.128

### Recurring workflow schedules
- Workflow Manager can create, inspect, pause, resume, and delete recurring schedules using five-field cron expressions and IANA timezones.
- The local Open RPA MCP exposes matching schedule management tools when started with `--allow-run`.
- Schedules pin the workflow and statically invoked workflows by content hash. Edits or permission/validation changes pause schedules rather than silently running changed automation.
- Missed occurrences are handled with a documented skip policy. Scheduled jobs use the durable single-worker local queue, are not replayed after interruption, and do not automatically retry.
- Windows builds bundle the timezone database needed for IANA timezone scheduling.

### MCP setup documentation
- Expanded the Codex quick start with commands to find the bridge beside the installed app, configure `%USERPROFILE%\.codex\config.toml`, verify the active Studio project, choose startup grants, and troubleshoot missing tools or version mismatches.
- Documented that recurring schedules run only while the project's local MCP process is running with the required grants.

### Verification
- Python: 567 tests passed.
- Frontend: 212 tests passed.
- Production frontend build passed.
- Frozen Windows MCP acceptance passed, including project-bound live draft staging and permission-gated tool discovery.
- Windows x64 NSIS installer: 70.00 MiB.
- SHA-256: `89f98ca9bb57c5d816e98f2f05870b4a46793b840d0136f67023e428cf5cd72d`.
- Added Linux x64 `.deb` and `.AppImage`, plus native macOS arm64 and x86_64 `.dmg` packages to this release. Each platform includes the matching MCP bridge and has a published SHA-256 checksum file.

### Operational limits
- This is local scheduling. The MCP worker must be running at due time; missed runs, worker interruption, and queue capacity behave as documented in [Local job orchestration](LOCAL-JOB-ORCHESTRATION.md).
- There is no cloud scheduler, distributed worker pool, or automatic whole-workflow retry.
- macOS packages are unsigned and not notarized; first launch may require explicit user approval in Gatekeeper.
