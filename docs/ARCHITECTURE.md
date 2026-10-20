# Architecture

The application is independent of Flowbench and has three parts:

1. `openrpa`: project schema, static validation, safe expression evaluator, adapters and Python workflow engine.
2. `src`: React/TypeScript visual editor and local browser preview. Browser preview runs a limited TypeScript engine in a worker and cannot access local files or OS automation.
3. `src-tauri`: desktop host. It launches the Python bridge over newline-delimited JSON, drains diagnostics, stores persistent application data in the OS app-data directory, and forwards run events to the UI.

## Execution and persistence

The Python engine loads version 1 projects and workflows, checks the invocation graph, then executes sequence activities. Nested If/Else, For Each, While, Switch, and Try branches share activity/time quotas and cancellation. Switch values are JSON scalars; numbers compare numerically, while booleans remain distinct, and unmatched values take the default branch. Each activity boundary checks cancellation; waits check every 50 ms. Active browser and HTTP operations are bounded by adapter timeouts but cannot be force-cancelled safely mid-request.

Desktop debug runs use a condition-based controller shared between the bridge thread and the engine thread. They begin paused before the first activity and may stop at activity boundaries for configured breakpoints, explicit pause requests, step-over, step-into or step-out. Step-over finishes the selected control-flow activity and nested work; step-into stops at the next nested activity when one exists; step-out finishes the containing activity and pauses at the next caller-level boundary. The UI receives a bounded, redacted variable snapshot while paused; arbitrary variable values are stripped from durable run-event history. Cancellation wakes a paused run and is checked before the activity starts. A currently executing network, browser, or desktop operation is not interrupted. Debug runs save the currently open workflow first so breakpoints and unsaved edits are the executed version.

While paused at an activity boundary, the debugger can edit existing JSON-compatible variables up to 64 KiB. Declared variable and argument types are enforced, credential-bearing values are never editable, and edits are audited by variable name and type without recording the value. Dynamic variables in the active scope can be edited; new variables cannot be introduced through the debugger. Edits apply immediately before the paused activity executes.

The desktop bridge writes a SQLite WAL run ledger using full synchronous commits. The schema has its own version. A migration first creates a separate SQLite backup; unsupported/newer schemas fail closed. It stores a workflow SHA-256, identity, start/end status, bounded activity event history, errors and audit records. At launch, leftover `running` rows are changed to `interrupted`; there is no automatic retry/resume because external effects may already have occurred. History retains up to 300 runs, 512 KB of events per run and 10,000 audit events.

## Capabilities and security boundaries

File paths are canonically resolved beneath the project root; bounded local writes use same-directory temporary files and atomic replacement. File, loop, activity, regex, event, run-time, network and package sizes have hard ceilings even when a project asks for larger values. The OS keyring is used for credentials; unsupported or plaintext backends are refused.

HTTP activity sockets use validated public DNS answers and connect to a pinned address, with redirects disabled and a finite response limit. Chromium checks destination DNS on navigation and every routed request, but Chromium performs its own lookup, leaving a documented DNS-rebinding race. Browser and desktop adapters are optional, runtime-probed and reported unavailable when their system dependencies are missing.

The engine is not an OS sandbox. Network/desktop permissions reduce accidental actions, but a user-approved workflow can still perform harmful actions within granted access. See [THREAT_MODEL.md](THREAT_MODEL.md).

Workflows may use either the existing ordered `activities` sequence or an explicit flowchart graph. Flowcharts have one Start node, action nodes containing ordinary activities, boolean decision nodes with true/false transitions, and End nodes. Validation checks node and transition identities, graph reachability and node-degree rules before execution. Optional node `x/y` coordinates are bounded to 0–10,000 and saved in the workflow JSON; workflows without positions receive an automatic initial layout. Loops are allowed and bounded by the activity quota; cancellation is checked at every node. Action nodes retain normal activity-level logs, errors and breakpoints; graph control nodes expose their own run state and can also have breakpoints. Browser preview executes the same graph subset but still has no filesystem or OS automation access.

Retry Scope is a nested reliability activity. It retries only configured error codes, with up to 10 attempts and up to 60 seconds of bounded exponential backoff. Before multiple attempts are valid, the author must acknowledge that the entire body is safe to repeat and select at least one error code. Workflow variables are restored to their pre-attempt snapshot after a failed attempt. This cannot roll back file, HTTP, desktop or other external side effects; matching failures therefore have at-least-once semantics and require idempotent operations or an idempotency key. HTTP socket timeouts emit `http-timeout`; other HTTP failures emit `http-error`.

## Format and migration

`project.json` and workflow documents have explicit format versions. This release supports version 1 only; future incompatible formats must use an explicit, backup-first migration. Older or newer unknown formats fail validation instead of being guessed.

Flowchart palette insertion is path-aware: adding to Start or Action splices the existing outgoing edge; adding to a Decision inserts on its True route and preserves False; adding to an End redirects all incoming paths through the new action. If the selected path lacks the required connection, the editor reports an error without mutating the graph. This avoids silently creating unreachable nodes.
