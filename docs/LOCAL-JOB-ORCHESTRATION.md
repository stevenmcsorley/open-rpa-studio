# Local job orchestration

Open RPA Studio includes a durable, single-machine worker queue for MCP-submitted workflows. It runs inside the local MCP server process and stores queue metadata in a project-scoped SQLite database under the application data directory. It does not create a cloud connection or expose a network listener.

## MCP tools

When the MCP server starts with `--allow-run`, it exposes:

- `openrpa_submit_job`: enqueue a saved workflow immediately or at an ISO-8601 timestamp with a timezone. An optional idempotency key prevents duplicate submissions.
- `openrpa_list_jobs` and `openrpa_get_job`: inspect status, timestamps, linked run ID and bounded error details. Inputs and idempotency keys are omitted from monitoring responses.
- `openrpa_cancel_job`: cancel a queued job or request cooperative cancellation of a running job.
- `openrpa_create_schedule`, `openrpa_list_schedules`, `openrpa_set_schedule_enabled`, and `openrpa_delete_schedule`: manage recurring five-field cron schedules for saved workflows.

The worker inherits only the MCP server's startup grants. A workflow that needs network, desktop, credential or destructive permissions is rejected at enqueue time unless the corresponding server flag was explicitly enabled. Each job binds to a digest of its workflow and statically invoked workflows; a changed workflow fails closed before it runs.

## Execution guarantees and limits

- One worker executes one job at a time.
- Queue state is committed synchronously to SQLite WAL storage.
- A repeated idempotency key for the same project returns the original job.
- One-time scheduled times are bounded to 365 days in the future. Recurring cron schedules use numeric `minute hour day-of-month month day-of-week` fields, lists, ascending ranges, and positive steps; month and weekday names and macros are not accepted. The timezone is an IANA name such as `Europe/London`. Day-of-month and day-of-week follow standard cron OR behavior when both are restricted.
- The MCP process must be running for a recurring occurrence to be materialized. If it was offline across an occurrence, one missed occurrence is run on restart and later missed times are skipped. One-time scheduled jobs remain queued while the server is offline. DST gaps naturally have no matching local minute; repeated local minutes can each match.
- A recurring schedule pins the workflow and all statically invoked workflows by content hash. If any change, the schedule is paused before its next run; review the changed workflow and create a new schedule to resume on the updated version. Permission or validation failures also pause the schedule. A workflow that fails during execution does not automatically pause future occurrences.
- At most 100 recurring schedules are stored per project. Occurrences use the same one-worker queue and active-job limit. Queue-full occurrences are skipped and reported in the schedule's last error.
- Worker shutdown or process failure changes a previously running job to `interrupted`. It is never automatically replayed because the workflow may have already caused external side effects.
- Whole-workflow automatic retries are deliberately disabled. Use workflow Retry Scope only for individually reviewed repeat-safe operations.
- Queued jobs retain input arguments in the local queue database until its data is removed. Monitoring APIs never return those inputs. Avoid placing credentials or unnecessary personal data in arguments.
- This is local orchestration, not a central multi-user service. There is no distributed locking across machines, high availability, SLA, or remote worker pool.

Studio's **Workflow Manager → Schedules** view can create, inspect, pause/resume, and delete recurring schedules. Studio uses a recovery-disabled database connection so managing schedules does not mark a live worker job interrupted. **Jobs** remains the execution-history view and can request cancellation, including for an MCP worker job; cancellation takes effect at the next engine activity boundary. Recurring schedules execute only while a local MCP server is running with `--allow-run` and the additional permission flags required by that workflow.
