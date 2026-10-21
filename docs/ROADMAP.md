# Delivery roadmap

## Built in this slice

- Added `Filter Rows` with a visual typed-condition editor and bounded AND/OR evaluation.
- Added `Join Rows` with typed keys, inner/left modes, duplicate-key expansion, right-field prefixes, cancellation and an explicit output row ceiling.
- Added `Group Rows` with first-seen grouping, null-aware counts, exact decimal-backed sums/averages in the native engine, min/max and bounded group/aggregation counts.
- Added `Sort Rows` with stable multi-key ordering, typed scalar fields, independent null placement, malformed/mixed type rejection, a 100,000-row ceiling, native execution and browser-preview parity.

- Versioned local project format and Python execution engine.
- Safe expression evaluation, argument/variable scoping, sequence/if/for-each/while/retry/switch/try-call control flow with shared execution quotas. Retry Scope supports filtered errors, bounded backoff, variable rollback and explicit repeat-safety acknowledgement.
- File, text, regex, CSV, JSON, wait, and explicitly permissioned HTTP activities.
- Optional Playwright browser interactions, Windows UI Automation through pywinauto, Linux AT-SPI interactions through the system accessibility bus, and PyAutoGUI coordinate fallback, with explicit permissions and runtime capability checks.
- Optional provider-based workflow drafting for Ollama, LM Studio, local OpenAI-compatible servers, OpenAI, Anthropic Claude, OpenRouter and compatible HTTPS endpoints. Credentials stay in an OS vault; returned workflows are validated before explicit insertion.
- Desktop shell, activity palette, visual sequence editor, property inspector, validation, execution state and logs.
- Nested visual authoring for If/Else, For Each, While, Switch cases/default and Try/Catch/Finally branches, including branch-local insertion, sibling ordering and removal.
- Boundary-based desktop debugger with start-paused runs, activity breakpoints, pause/continue, step-over, step-into and cancellation while paused.
- Paused debugger variable editing for bounded JSON values, with declared-type enforcement, credential exclusion and value-free audit metadata.
- Visible Playwright browser inspection that discovers accessible controls and adds editable click/fill/select/check/read activities through the ordinary workflow authoring path.
- Cross-platform semantic desktop inspection: Windows UI Automation inspection lists visible windows and control metadata; Linux AT-SPI uses accessible windows and native Action, EditableText and Text interfaces. Both insert editable click/set-text/read-text/wait activities, omit password values and reject ambiguous matches. A live GTK3 workflow passed on Ubuntu 22.04 under WSL.
- Browser interaction recording for uniquely identified, named controls. Recording preserves action order and selector metadata, excludes password/email/payment/file/hidden fields, never reads typed values, and requires review before insertion; recorded fill/select values are left blank for explicit author completion.
- Flowchart palette insertion splices activities into the selected path, preserves downstream transitions, routes Decision insertions through True, and inserts before End nodes without leaving unreachable nodes.
- Flowchart minimap displays graph topology, selected node and current viewport, with pointer and keyboard navigation for large canvases.
- A scoped workflow outline for the selected flowchart action lists nested activities with branch context and navigates them in the inspector while keeping the containing graph node selected.
- The Output pane collapses to its tab strip and can be resized by pointer or keyboard with bounds that preserve minimum designer space.
- State-machine transition overview visualizes initial, final, guarded, cyclic and disconnected states, with graph-node selection wired to the existing state editor.
- Example CSV automation and engine/UI verification.
- Selected run records export as versioned JSON evidence with an atomic write, displayed SHA-256 digest, and destination-path-free audit metadata.
- Desktop toolbar import/export for deterministic, integrity-checked `.orpa` project packages, with export workflow validation and safe empty-folder extraction.
- Reusable workflow argument mapping with per-call-site outputs and preflight validation.
- Run and Debug collect typed main-workflow inputs with required/default handling, validation and end-to-end forwarding through desktop and browser-preview execution.
- Bounded text extraction from selectable PDF pages, with a page-count output, page boundaries, explicit file-read auditing, and documented no-OCR/encryption limits.
- Local SQLite data integration through parameterized read-only queries with an SQLite authorizer allowlist, approved-root confinement, row/byte/time caps, cancellation, and audited attempt/result metadata.
- Data Filter activity for typed, AND/OR record conditions, safe expression values, stable-order filtering, cancellation checks, aggregate execution evidence, and browser-preview parity.

## Next release gates

1. **Debugging completion:** workflow invocation failures now carry a bounded, redacted call path and origin workflow/activity through run results and durable history. Add durable debug checkpoints; paused variable editing and Step Out are supported at activity boundaries. Mid-activity pause remains adapter-dependent.
2. **Visual authoring:** explore a canvas-level graph view for nested flowchart action subtrees. Flowchart action properties now support authoring nested control-flow branches, and a scoped outline selects nested activities while keeping their containing graph action highlighted; the sequence editor has a pinned outline; the state-machine graph supports selecting, adding, editing, reordering, and removing transitions; flowchart navigation and the minimap are implemented.
3. **Automation adapters:** browser activities now support up to ten explicit, auditable selector fallbacks with ambiguity rejection; fuzzy/automatic selector healing is not implemented. Broaden accessibility acceptance across GTK, Qt, WPF, Win32, WinForms and packaged-app targets. Browser waits/assertions and bounded browser interaction recording are implemented.
4. **Security:** signed plugin metadata, dependency/SBOM scans, adversarial package and egress tests, threat-model review, safe package verification.
5. **Distribution:** Windows x64 per-user NSIS installer now builds and installs in a workspace-local smoke test, with a bundled Python engine and no-console child process. Still verify on a clean Windows machine; sign binaries; test upgrades, uninstall and WebView2 bootstrap behavior; produce Linux AppImage/deb on a supported Linux build host.
6. **AI (optional):** a reproducible live Ollama smoke acceptance now covers sequence, flowchart and state-machine drafting through validation and execution; per-protocol structured-output fallbacks and bounded cancellation are implemented. Authenticated remote-provider integration acceptance and compatibility across additional local models remain. Typed model IDs now work when a host's model catalogue is unavailable. Core authoring/execution remains available without a model.

“Production” requires passing these operational and security gates for each supported platform; the initial vertical slice is not yet a production-certified release.
# Product roadmap: next capabilities

Open RPA Studio is independent of Flowbench. This roadmap records upcoming product capabilities; it does not claim completed parity with another automation product.

## API connector builder

**Goal:** make API-driven automations approachable without hand-authoring generic HTTP request fields or automating a website's UI.

The connector milestone will build on the existing restricted HTTP client, workflow activities, and OS credential vault. It will provide:

- Reusable, project-local API connection profiles with a visual editor.
- Secure API-key and OAuth 2.0 client-credentials setup. Client secrets remain in the operating-system vault; access tokens remain in memory for the run. Authorization Code/PKCE and refresh-token grants remain future work.
- Explicit method, base URL, path, query parameters, headers, and JSON request-body configuration.
- Bounded pagination strategies, request pacing/rate limits, timeouts, response-size quotas, cancellation, and clear partial-failure behavior.
- Safe response parsing and JSON-path mapping into workflow variables and data rows.
- Permission review, destination checks, redacted diagnostics, and audit evidence for every external request.
- AI draft support using the same validated activities and saved-connection references, without granting the model access to secret values.

**Delivered increments:** native **Paginated API Read** performs bounded page-numbered GETs and maps JSON arrays; reusable HTTPS connection profiles and a visual **API Request** editor support OS-vault bearer/API-key/OAuth client-credentials authentication, shared headers, GET/POST/PUT/PATCH, bounded responses and request pacing. OpenAPI import now detects unambiguous successful JSON object arrays, generates RFC 6901 field mappings for declared scalar properties and applies bounded native record mapping while retaining the raw HTTP response. Ambiguous arrays and external references fail closed with warnings. OAuth tokens are short-lived in-memory run data. All requests use restricted public egress and per-run network permission. A live MCP request against JSONPlaceholder succeeded; OAuth exchange currently has mocked protocol tests and still needs live acceptance with a provider account. See [API activity documentation](API-ACTIVITIES.md). Remaining work includes Authorization Code/PKCE, cursor/next-link pagination, retries, richer arbitrary JSON mapping, generated connector definitions and broader provider acceptance.

Remaining delivery gates: live OAuth acceptance with a provider account; cursor/next-link pagination and retry safety; richer mapping and generated OpenAPI connectors; broader provider acceptance. Private-network targets, redirects and unsupported OAuth flows must remain explicit rather than implied to work.

## Differentiated product direction

The product should compete on open, local control and a shorter path from intent to a reliable automation. UiPath already offers agentic automation, integrations, orchestration, and debugging; this project should not market those broad concepts as unique. Its opportunity is to make them easier to inspect, configure, run locally, and extend across providers.

1. **Universal local automation agent.** Discover tools the user explicitly makes available, then prefer a documented API, MCP tool, or CLI over browser or desktop interaction when both can satisfy the task. Generate a normal editable workflow, validate it, show a permission plan, and require review before actions with external effects. Start only after the API connector and tool-discovery contracts are established.
2. **Automatic API discovery.** Local OpenAPI 3.0/3.1 import now lists GET/POST/PUT/PATCH operations and fills editable API Request activities, parameters, JSON body examples and unambiguous bounded scalar-field response mappings. Remote documentation inspection, generated connector definitions, richer schema compositions and broader OpenAPI compatibility remain future work; external references are never fetched automatically.
3. **Provider-neutral offline AI.** Keep generation, explanation, and repair compatible with local runtimes such as Ollama and LM Studio, while retaining optional user-configured remote providers. Core execution must not depend on an AI provider.
4. **Workflow trace and replay.** Capture bounded, redacted activity inputs/outputs and UI/API evidence. Replay deterministic local steps from a checkpoint; never imply that a prior external action can be rolled back or safely repeated without idempotency evidence.
5. **Bidirectional source view.** Make the versioned workflow format readable and diffable in Git, with an editable source view that round-trips to the visual model without lossy conversion.
6. **Open activity packages.** Support documented, isolated, signed packages with dependency/SBOM evidence before offering a public community registry. Package trust and update safety come before registry scale.
7. **Cross-platform worker mesh.** Dispatch jobs to explicitly paired Windows, Linux, and macOS workers only after identity, transport security, permissions, updates, and audit semantics are defined.
8. **Automation cost and reliability view.** Track observed run time, retries, failures, and user-configured API/model cost rates; suggest cheaper paths only when equivalent output can be verified.

The suggested order is API connector and discovery first, then the local tool-selection agent and trace/replay foundation. Worker mesh and a public package registry are later investments because they expand the security and operations surface substantially.

## Current increment

- Bounded web-table extraction turns one selected HTML table into records for subsequent mapping and validation activities.
