# Local job orchestration

Open RPA Studio includes a durable, single-machine worker queue for MCP-submitted workflows. It runs inside the local MCP server process and stores queue metadata in a project-scoped SQLite database under the application data directory. It does not create a cloud connection or expose a network listener.

## MCP tools

When the MCP server starts with `--allow-run`, it exposes:

- `openrpa_submit_job`: enqueue a saved workflow immediately or at an ISO-8601 timestamp with a timezone. An optional idempotency key prevents duplicate submissions.
- `openrpa_list_jobs` and `openrpa_get_job`: inspect status, timestamps, linked run ID and bounded error details. Inputs and idempotency keys are omitted from monitoring responses.
- `openrpa_cancel_job`: cancel a queued job or request cooperative cancellation of a running job.

The worker inherits only the MCP server's startup grants. A workflow that needs network, desktop, credential or destructive permissions is rejected at enqueue time unless the corresponding server flag was explicitly enabled. Each job binds to a digest of its workflow and statically invoked workflows; a changed workflow fails closed before it runs.

## Execution guarantees and limits

- One worker executes one job at a time.
- Queue state is committed synchronously to SQLite WAL storage.
- A repeated idempotency key for the same project returns the original job.
- Scheduled times are bounded to 365 days in the future; the MCP process must be running for a job to execute at its due time. A due job waits in the durable queue while the MCP server is offline and is picked up when the server starts again.
- Worker shutdown or process failure changes a previously running job to `interrupted`. It is never automatically replayed because the workflow may have already caused external side effects.
- Whole-workflow automatic retries are deliberately disabled. Use workflow Retry Scope only for individually reviewed repeat-safe operations.
- Queued jobs retain input arguments in the local queue database until its data is removed. Monitoring APIs never return those inputs. Avoid placing credentials or unnecessary personal data in arguments.
- This is local orchestration, not a central multi-user service. There is no distributed locking across machines, high availability, SLA, or remote worker pool.

Studio's **Jobs** output tab reads queue state without opening the database for writes. It can request cancellation, including for an MCP worker job; cancellation takes effect at the next engine activity boundary.
