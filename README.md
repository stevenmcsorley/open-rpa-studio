# Open RPA Studio

Open RPA Studio is a local-first, open-source desktop environment for visually authoring and executing automations. It is an independent application: it does not use Flowbench code, services, branding, or runtime components.

This repository contains the editor, the versioned workflow format, a separate Python execution engine, optional automation adapters, and packaging/build scripts. The product is under active development. It is a capable early release, not yet a certified enterprise RPA platform or a complete UiPath replacement.

API integrations include bounded **Paginated API Read**, reusable HTTPS connection profiles, a visual **API Request** activity, and local OpenAPI 3.0/3.1 operation import. Profiles support no authentication, bearer tokens, API-key headers, OAuth 2.0 client credentials, and OAuth Authorization Code with PKCE; secrets and long-lived access/refresh tokens stay in the operating-system credential vault. The connector supports GET/POST/PUT/PATCH, query parameters, shared headers, request bodies, bounded response mapping, cursor/next-link pagination, transient GET retries, response limits and per-connection pacing. OpenAPI import fills editable operations and parameter variables and can prefill a reusable connection with an unambiguous server and supported authentication scheme, without importing credentials, fetching external references, or executing spec content. See [API activity documentation](docs/API-ACTIVITIES.md) for provider constraints, limits and permissions.

![Open RPA Studio browser preview showing the CSV workflow in the flowchart designer, with the selected node, properties inspector and graph minimap](docs/assets/studio-overview.png)

*The screenshot shows the isolated browser preview and the flowchart minimap. Desktop-only capabilities such as filesystem access and Windows UI Automation are available in the installed application, not in this preview.*

![Open RPA Studio authoring a bounded paginated JSON API read with its activity properties visible](docs/assets/api-pagination-activity.png)

*Paginated API Read exposes page and record limits, response mapping, and metadata directly in the workflow properties. The screenshot is from the isolated browser preview; actual requests run only in the desktop engine after network permission is granted.*

![Open RPA Studio run history with workflow search, status filtering and a selected run's saved activity and event evidence](docs/assets/run-history-filters.png)

*Run History includes searchable workflow, run-ID and error fields, status filters, and a read-only view of saved run evidence. This public screenshot uses illustrative sample records.*

![Open RPA Studio showing the selected run's versioned JSON evidence export action](docs/assets/run-history-export.png)

*Export creates a versioned JSON record and reports its SHA-256 digest. This public screenshot also uses illustrative sample records.*

![Open RPA Studio state-machine editor showing initial and final states, a directed transition overview and the selected state's activities](docs/assets/state-machine-overview.png)

*State-machine overview nodes are generated from the executable state and transition definitions. Select a node to edit that state's activities and guards.*

![Open RPA Studio state-machine editor with a conditional debug breakpoint configured on state entry](docs/assets/conditional-debug-breakpoints.png)

*Conditional breakpoints on flowchart nodes and state-machine entries use the safe expression language; invalid conditions pause for review.*

![Open RPA Studio project search locating a configured activity message and showing its workflow context](docs/assets/project-wide-search.png)

*Find configured content across project workflows, nested branches and graph models with Ctrl+Shift+F, then jump to the matching activity or state.*

![Open RPA Studio configuring an explicit browser selector fallback chain](docs/assets/selector-fallbacks.png)

*Browser workflows can use up to ten author-defined alternatives. The engine uses a fallback only when exactly one alternative resolves uniquely and records the choice without logging selector text.*

![Open RPA Studio displaying an AI provider compatibility warning above a draft preview](docs/assets/ai-schema-fallback.png)

*The draft panel discloses a schema-guided retry when a compatible endpoint rejects JSON Schema mode. The local HTTP acceptance test verifies the adapter exchange; this screenshot illustrates the resulting UI state.*

![Open RPA Studio sequence editor with its navigable nested workflow outline open beside an If branch and a selected branch activity](docs/assets/workflow-outline.png)

*The workflow outline includes branch context for nested activities and stays pinned while the canvas scrolls. Select an entry to focus that activity and open its properties.*

![Open RPA Studio flowchart editor with a nested If branch and its editable Then activity shown in the action properties inspector](docs/assets/flowchart-nested-branches.png)

*Flowchart action nodes can contain nested control flow. Add and edit branch activities from the action inspector; these activities remain part of that executable graph node.*

![Open RPA Studio flowchart with the selected action's nested activity outline open and a branch activity selected in the properties inspector](docs/assets/flowchart-action-outline.png)

*Select a flowchart action to open its scoped outline. Branch paths remain visible while selecting nested activities, and the corresponding graph action stays highlighted.*

![Open RPA Studio flowchart with the output pane resized to show a larger editable activity area](docs/assets/resizable-output-pane.png)

*Drag the divider above Output or focus it and use the arrow keys. Home and End move to the available bounds, and Escape restores the default height.*

![Open RPA Studio state-machine graph with a selected transition and inline guard and destination editor](docs/assets/state-machine-editor.png)

*Select a transition edge to edit its destination or guard, reorder guarded routes, remove it, or add a new safe False-guarded route. Blank guards represent the fallback and remain last.*

Execution history now opens full saved run records with activity durations, event timestamps, workflow digests, errors and clear interruption warnings. Interrupted runs are inspectable and are never silently replayed.

When the bound MCP server creates or updates a workflow, Studio detects the saved project change, opens that workflow, and names it in the status message. With `--allow-edit`, the agent can also stage successive validated snapshots while it builds; Studio opens or focuses the matching workflow tab and applies each staged snapshot directly to the canvas. The active tab shows a subtle live-update indicator. Staging does not change the saved project; a final MCP create/update saves the workflow. Studio waits for an explicit reload when local edits would otherwise be overwritten.

The AI drafting panel can also prepare a workflow repair from the latest failed run. It excludes runtime variable values, argument defaults and raw error text from the repair prompt, then requires validation and review before replacing the current workflow. Remote providers may receive configured literals from the workflow.

Before every run, Studio now shows an impact review that expands saved child workflows, identifies file reads and writes, highlights destructive operations, and requests network or desktop permission for that run only. The review is a static plan: expressions and runtime data can still change actual targets. See [Run impact review](docs/RUN-IMPACT-REVIEW.md) for coverage and limits.

## Download and install

The latest Windows installer is [Open RPA Studio v0.1.112](https://github.com/stevenmcsorley/open-rpa-studio/releases/tag/v0.1.112). It is unsigned and intended for evaluation; verify its SHA-256 against the release before running it.

The NSIS installer supports a per-user installation and uninstall. The app bundle includes a frozen Python bridge, so Python does not need to be installed on the target computer. Windows WebView2 is required; current Windows 10/11 installations normally provide the Evergreen runtime. Playwright browser binaries are not included in this installer. Browser Launch defaults to a visible Playwright Chromium window, and can select installed Chrome, Edge, Brave, Vivaldi, Opera or Opera GX when detected, any custom Chromium-based browser, Firefox or WebKit. Install the selected Playwright browser runtime where needed; the engine reports a clear error instead of silently switching browsers. Runtime capability status is displayed by the app rather than inferred from package presence. The visible browser inspector can record editable click, hover, fill, select and safe-key actions; field values are omitted and must be added in the workflow editor. Browser workflows can manage named tabs and capture popups, with network access and public-address checks applied to new pages. Exact accessibility-role selectors can opt into conservative recovery when a control label changes slightly; ambiguity fails closed and recovery is off by default. Browser file uploads are project-root bounded; downloads are size-limited before saving to the project, default to no-overwrite, and use Playwright's temporary download cache before that check.

The v0.1.112 installer is unsigned. Windows SmartScreen may show an unknown-publisher prompt. Verify the downloaded file against the SHA-256 in the release before running it: `c364b4a87f638c95607de8f3655693967693d081b140050922b1480826877eff`.

```powershell
Get-FileHash .\release\Open-RPA-Studio-Setup-0.1.112-x64.exe -Algorithm SHA256
```

To build an installer from the current source on Windows, run `npm ci` and then `npm run build:windows-installer`. This creates an unsigned `release/Open-RPA-Studio-Setup-<version>-x64.exe`; the installer build includes the optional Pillow OCR preflight dependency, but Tesseract and language data remain separate system dependencies.

## Build the Windows installer

### Prerequisites

- Windows 10/11 x64 and the Microsoft C++ Build Tools (MSVC linker).
- Rust stable with `x86_64-pc-windows-msvc` installed.
- Node.js 20 or newer and npm.
- Python 3.11 or newer plus `uv`.
- WebView2 runtime for launching the packaged desktop app.

From PowerShell:

```powershell
cd open-rpa-studio
npm ci
npm run build:windows-installer
```

The build script locks and syncs the Python dependency graph, freezes the Python bridge with PyInstaller, compiles the Vite and Tauri release builds, and creates an NSIS setup executable. Tauri downloads and hash-checks its pinned NSIS tooling and helper DLL when needed. The resulting setup executable is copied into `release/`; generated engine executables and build outputs are intentionally ignored by Git.

To build the frontend only, run `npm run build`. To build the desktop host without packaging an installer, run `npm run tauri -- build --no-bundle` (or invoke `node_modules/.bin/tauri.cmd` directly if your npm version rewrites option arguments).

## What works today

### Visual authoring

- Project and workflow files use versioned JSON formats (`openrpa.project` and `openrpa.workflow`, format version 1).
- Export and import deterministic `.orpa` project packages from the desktop toolbar. Exports validate workflows and exclude secret files; imports verify the manifest, file hashes and paths before extracting to an empty folder.
- Create and open local projects, add workflows, save, validate, and inspect validation problems.
- Search a categorized activity catalog, configure activity properties, reorder sequence actions, edit nested control-flow branches, and zoom sequence canvases from 50% to 150% with a reset control.
- Read page-numbered JSON APIs through bounded **Paginated API Read** requests. The activity supports header expressions, JSON item paths, response and page limits, cancellation checks, audit events, and explicit network permission; see [API activity documentation](docs/API-ACTIVITIES.md).
- Save reusable API connection profiles, keep bearer/API-key credentials in the OS vault, and configure relative API requests visually. Network permission remains explicit per run; endpoint profiles are HTTPS-only and use the restricted public egress client.
- Search configured text across workflows, nested control-flow branches, flowcharts and state machines with Ctrl+Shift+F. Results show workflow context and navigate to the selected activity or graph element; search excludes credential-like fields and variable or argument defaults.
- Collapse or reopen the Output pane to give the workflow designer more vertical room; the output tabs remain accessible while collapsed.
- Author either a sequence or a flowchart. Flowcharts include Start, action, Decision, and End nodes; transitions, positions, and edits persist in the workflow file. Flowchart action nodes can contain editable nested If/Else, loop, Switch, and Try/Catch/Finally activities in the properties inspector.
- Author a state machine with named states, per-state activity sequences, ordered boolean guards, an explicit initial state, and terminal states. State visits obey the workflow execution quota; interrupted workflows are not automatically replayed.
- See the [workflow format and state-machine example](docs/WORKFLOW-FORMAT.md) and the [architecture notes](docs/ARCHITECTURE.md).
- Convert a linear flowchart to a sequence when it contains no branches or loops.
- Use Excel workbook activities to read .xlsx sheets into records and write records to new workbooks. See [Excel workbook activities](docs/EXCEL-ACTIVITIES.md) for limits, formula handling, archive protections and unsupported features.
- Query approved local SQLite files using parameter-bound read-only SQL, row/result-size quotas, VM timeouts, cancellation and audit events. Writes, `PRAGMA`, attachment, and multi-statement SQL are denied. See [SQLite Query activity](docs/SQLITE-ACTIVITY.md).
- Sort bounded record lists by up to 50 unique fields, with ascending/descending order, explicit null-first/null-last behavior independent of direction, stable ties, homogeneous typed scalar comparisons and native/browser-preview parity.
- Extract selectable text from local PDFs with page separators, configurable page limits, page-count output and run cancellation checks. Scanned/image-only PDFs need an external OCR process; encrypted files are rejected. See [PDF activity limits](docs/PDF-ACTIVITIES.md).
- Query approved local SQLite files with parameter-bound, read-only SQL, result/time limits, cancellation and durable audit events. See [SQLite Query activity](docs/SQLITE-ACTIVITY.md).
- Insert ordinary activities in the selected flowchart path while preserving downstream transitions.
- Pan a large flowchart with Space+drag or middle-drag, center the selected node, and reconnect a transition by dragging its connector handle onto a destination node. The minimap shows the whole graph, selected node and visible viewport; click it to navigate. The accessible destination selector remains available for keyboard editing.
- Undo and redo workflow edits across sequence, flowchart, state-machine, activity properties, variables and arguments using the toolbar or Ctrl+Z/Ctrl+Y (Cmd+Z/Cmd+Y on macOS). Each workflow keeps a bounded 100-step edit history; loading another project clears the prior project's history.
- Duplicate a selected activity beside its source with Ctrl/Cmd+D or the canvas toolbar. Control-flow descendants and switch cases receive fresh activity IDs, so duplicated breakpoints and execution results remain independent. Works in sequences, state-machine states and flowchart action paths.
- Copy and paste activity subtrees within the Studio clipboard using Ctrl/Cmd+C and Ctrl/Cmd+V or the canvas controls. Paste inserts after the current selection, remaps IDs on every paste, works across workflows and does not access the system clipboard.
- Use the visible, permission-gated Playwright inspector to discover named page controls and add editable click, fill, select, check, uncheck, and read-text actions.
- On Windows, inspect visible application windows and accessible controls with UI Automation; on Linux, inspect controls through the AT-SPI accessibility bus. Both adapters add editable click, set-text, read-text, and wait activities using exact window titles and accessible names/IDs. Ambiguous selectors fail closed, and password controls are omitted.
- Generate a candidate workflow from an optional AI provider, review the validation output, then explicitly insert the draft. Generated workflows are not run automatically.
- Invoke reusable project workflows through a dedicated argument-mapping editor. Map typed inputs and per-call output variables; project validation catches missing required arguments, unknown names and incompatible directions before execution.
- Choose whether AI drafts an activity sequence, connected flowchart, or state machine. Model-specific schemas and the same local workflow validator are applied before a draft can replace the current workflow.
- Stop an in-flight AI draft from the native Studio panel; cancellation travels through the bridge to the provider socket, while warning that a provider may continue processing after it receives a request.
- Test configured AI endpoints from the model picker. Studio reports reachability, model count and request time, and distinguishes an empty model catalogue from a connection failure without sending a prompt.
- Connect a compatible AI agent to one project over the local stdio Model Context Protocol server. It supports project/workflow discovery, the canonical native activity catalog, workflow reading, draft-bundle validation, opt-in creation and updates with optimistic concurrency, repeated validated snapshots applied directly to the active Studio workflow tab and canvas, and read-only desktop adapter/window/control inspection. With `--allow-run --allow-desktop`, it can also perform live accessibility-targeted desktop actions, including fill, safe keypress, select, click/invoke, state waits and window activation/minimize/restore; protected edits are blocked and values are excluded from audit records. With `--allow-run --allow-network --allow-desktop`, it can open a visible, MCP-owned browser, inspect bounded page text and accessible controls, perform selector-based actions, pace scrolling, and record editable interactions. It never attaches to an existing browser profile; page text is untrusted, form values are not audited, protected fields are blocked, and URL query/fragment data is omitted from results. Staging keeps the saved project unchanged; the agent commits the workflow through the validated create/update tools. The Windows installer bundles this command in `engine/openrpa-bridge-<version>.exe`; see [MCP client integration](docs/MCP-INTEGRATION.md).

### Workflow execution

The Python engine is separate from the UI process and can also run from the command line. Supported control flow includes If/Else, For Each, While, Switch, Retry Scope with explicit repeat-safety acknowledgement, Try/Catch/Finally, flowcharts, and reusable workflow invocation with typed arguments. The expression evaluator accepts a bounded expression grammar and never calls `eval()` on workflow text.

Core activities include variable assignment and logging; credential lookup by vault reference; file read/write/copy/move/delete/list operations; text/regex processing; JSON, CSV and XLSX data operations, including typed row filtering, bounded typed-key joins, grouped aggregates, stable multi-key sorting, expression-based row projection, typed-key deduplication and explicit row-schema validation; selectable PDF text extraction and optional local Tesseract image OCR; wait; HTTP requests; browser actions; Windows UI Automation; Linux AT-SPI desktop accessibility; screenshots; and optional desktop coordinates. Activity permissions, quotas, validation, structured logs, and execution status are handled by the engine, not simulated by the editor.

![Open RPA Studio workflow designer with a Filter Rows activity selected and typed status and value conditions configured in its properties panel](docs/assets/filter-rows-activity.png)

*Filter Rows supports AND/OR combinations, typed JSON comparison values, case-insensitive text rules, and empty-field checks. The screenshot uses illustrative procurement-style field names.*

![Open RPA Studio with the Join Rows activity configured for a left join between orders and customers](docs/assets/join-rows-activity.png)

*Join Rows supports typed matching keys, inner and left joins, duplicate-key expansion, a right-field prefix, and an explicit maximum output size. This is an illustrative unsaved browser-preview workflow.*

![Open RPA Studio with Group Rows configured by department and showing sum, average and count aggregations](docs/assets/group-rows-activity.png)

*Group Rows builds repeatable summaries from tabular workflow data, with typed group fields, null-aware aggregates and a configurable group ceiling. The screenshot shows an illustrative unsaved preview workflow.*

![Open RPA Studio with the Sort Rows activity configured for stable multi-key sorting and explicit null ordering](docs/assets/sort-rows-activity.png)

*Sort Rows supports ordered field priorities, ascending or descending order, explicit null placement, stable ties, mixed-type rejection and a configurable input limit. This is an illustrative unsaved browser-preview workflow.*

![Open RPA Studio with Map Rows projecting displayName, ordinal and calculated value fields from source records](docs/assets/map-rows-activity.png)

*Map Rows builds a new record shape from safe expressions over each source row and its zero-based index. Only configured output fields are included; the screenshot shows the default editable browser-preview workflow.*

![Open RPA Studio with Distinct Rows configured to deduplicate records by buyer and supplier keys](docs/assets/distinct-rows-activity.png)

*Distinct Rows uses typed composite keys, explicit first-or-last retention and stable source order, and reports how many duplicate rows it removed.*

![Open RPA Studio with Validate Rows rules for required typed fields and explicit validation outputs](docs/assets/validate-rows-activity.png)

*Validate Rows checks records against explicit field types and required/non-empty constraints. It leaves source rows untouched and emits invalid rows with structured field-level reasons.*

![Open RPA Studio with the local OCR Image activity configured for an installed Tesseract runtime](docs/assets/image-ocr-activity.png)

*OCR Image reads an approved local PNG, JPEG or BMP through Tesseract. The desktop runtime reports whether OCR is installed; the browser preview cannot read local files. See [local image OCR limits and setup](docs/IMAGE-OCR.md).*

![Open RPA Studio with Read Web Table configured in the workflow designer](docs/assets/web-table-activity.png)

*Read Web Table converts one uniquely selected HTML table into bounded workflow records; its desktop Playwright engine enforces row, column, time, and output-size limits.*

### Debugging and run history

When you run or debug a workflow with input arguments, Studio collects typed values in the run review dialog, validates required fields and JSON values, and passes the inputs to the selected workflow. Output and in/out argument values appear in the execution variables.

![Open RPA Studio argument editor configuring required inputs, optional inputs, a typed JSON default and an output argument](docs/assets/argument-default-editor.png)

*Workflow arguments now expose direction, required/optional status and typed JSON defaults in the editor. Defaults are checked against the declared type before they can be saved.*

![Open RPA Studio run review dialog collecting string, integer, boolean, object and array workflow inputs](docs/assets/run-input-arguments.png)

*The example shows illustrative workflow arguments. Input values are run-specific and are not written into the workflow definition.*

- Boundary-based breakpoints and debugger start-paused mode.
- Conditional breakpoints on activities, flowchart nodes and state-machine entries use the safe expression language. False conditions continue; true conditions pause, and invalid conditions pause for review rather than being silently ignored.
- Pause, continue, step-over, step-into, step-out, and cancellation at activity boundaries.
- Inspect variables and edit supported JSON-compatible values while paused, subject to type and credential protections.
- Add watch expressions using the safe workflow expression language. Watches evaluate against the live engine scope only while paused, with registered secrets redacted and large results truncated.
- Durable SQLite run history records workflow digests, times, statuses, activity events, errors, and security audit events.
- Interrupted runs are marked for inspection; they are never resumed or repeated automatically because prior activities may have changed external systems.
- Select a saved run and choose **Export evidence** to write a versioned JSON record with its status, workflow digest, activity results, errors and bounded event history. The export is atomic and its SHA-256 is shown after saving; export metadata is recorded in the audit log without retaining the destination path. Review exported evidence before sharing because saved events can contain sensitive business information. See the [run evidence format](docs/RUN_EVIDENCE_EXPORT.md).

### Optional AI providers

The core editor and execution engine work without an AI model or network access. Workflow drafting has adapters for:

- Ollama.
- LM Studio.
- OpenAI-compatible local servers on loopback.
- OpenAI API (including API access to OpenAI models; a ChatGPT subscription is not an API credential).
- OpenAI API through either Chat Completions or the Responses API, selectable as separate profiles.
- Google Gemini API, using its native `generateContent` protocol and schema-constrained JSON output.
- Anthropic Claude API.
- OpenRouter.
- Compatible remote HTTPS endpoints configured by the user.

The model picker accepts typed model IDs as well as discovered IDs. This lets compatible endpoints work when their model catalogue is disabled or filtered; the chosen ID is still sent to the selected provider and provider errors remain visible.

Provider credentials are references into the operating-system credential vault (Windows Credential Manager, macOS Keychain, or Linux Secret Service). In the desktop AI panel, enter a key into the password field and choose **Store API key securely**; the key is sent to the local bridge, stored in the OS vault, then cleared from the form. Save named connection profiles to remember provider, endpoint, model and vault references across launches. Profiles contain no credentials. Alternatively, use `openrpa credential SERVICE USERNAME`. Secrets are never placed in workflow files or audit records. Remote prompts disclose the provider route before a request. Task descriptions are JSON-encoded user content, separate from system instructions; this does not eliminate prompt injection. AI output is treated as untrusted, parsed as a bounded schema, validated by the workflow validator, and requires user review before insertion. Local models are optional; unavailable providers do not disable non-AI features.

This is a set of provider-protocol adapters, not a promise that every model endpoint implements tool calling or structured output identically. Some compatible servers may reject schema-constrained requests.

### Browser and desktop adapters

Browser activities use Playwright with role, label, text, placeholder, test-id, or CSS selectors. The library includes explicit element waits and visible/hidden/enabled/disabled/checked/text assertions with activity-scoped timeouts. **Read Web Table** turns one uniquely selected HTML table into workflow records, with optional first-row headers and strict row, column, timeout, and total-text limits. **Extract Repeated Web Items** maps bounded card/list elements into structured records using relative CSS selectors, required/optional fields, attribute extraction, normalized text, absolute links, and ambiguity checks. **Scroll Page** can move gradually and emits live position/percentage events, checking cancellation between steps. The Browser Launch properties let the author select a browser engine/channel and visible or headless mode; visible is the default. The Browser Inspector uses a visible Chromium browser, permission-gated navigation, request destination checks, and editable selector-based actions. Its interaction recorder captures bounded click, fill, selection, and checkbox actions for uniquely identified named controls, including across page navigation in one browser tab. It records selector metadata only: it does not read typed values, and it excludes password, email, payment, file, and hidden fields. Generated fill/select activities have blank values and must be reviewed before use. The bridge checks browser runtime availability when launching. Install the Playwright Chromium runtime for development with:

```powershell
uv sync --locked --extra dev --extra browser
uv run playwright install chromium
```

Windows UI Automation is available through the optional `desktop` extra and the Studio's **Inspect UI → Inspect Desktop UIA** picker. It reads visible control metadata only, excludes password controls, rejects ambiguous selectors, and creates ordinary editable workflow activities. Every desktop inspection and interaction requires explicit desktop permission. Linux semantic inspection and interaction use AT-SPI/AT-SPI2; its availability depends on distribution bindings and an active accessibility bus. Linux interaction recording observes primary-button presses and allowlisted navigation keys through X11/XWayland, then converts them to unique AT-SPI selectors; printable keys and typed text are never captured. Native Wayland windows without XWayland surfaces cannot be recorded. Linux coordinate-based fallback uses optional PyAutoGUI and is less resilient than semantic selectors.

## Safety and security model

Workflows can act on files, networks, browsers, or desktop sessions. Only run workflows and packages you trust.

- File paths are confined to the project root plus explicitly configured extra roots. Path traversal, unsafe project paths, and unapproved writes are rejected.
- Network activities are disabled until a run is explicitly granted network permission. HTTP requests validate DNS/IP destinations, block private/special-use networks, pin the checked address, cap ports/timeouts/response sizes, and disable redirects. Browser navigation also checks destinations and blocks WebSockets/service workers/downloads in inspection mode; Chromium resolves hostnames itself, so browser DNS-rebinding protections are not equivalent to a pinned HTTP connection.
- Desktop automation is permission-gated each run.
- Credential values come from supported OS vaults. Unsupported plaintext/fallback keyrings are refused. Secret-bearing values are redacted in returned state and logs.
- Workflow expressions are parsed by a constrained evaluator. There is no general-purpose Python or JavaScript activity in the default catalog.
- Imported project files and `.orpa` packages are validated. Package extraction rejects unsafe/duplicate paths, symlinks, excessive sizes, and suspicious compression ratios. `.orpa` hashes provide integrity checks, not publisher identity; packages are not digitally signed.
- AI-generated workflow data is not trusted code. It is schema-checked and workflow-validated before a person may insert it.
- Security controls are still undergoing adversarial testing; see [SECURITY.md](SECURITY.md) for the current threat model and reporting process.

## Project and workflow format

A project contains a `project.json` manifest and workflow JSON documents, commonly under `workflows/`. The project manifest maps workflow names to project-relative paths and names a main workflow. Each workflow declares format/version, variables, arguments, execution model, and activities (or flowchart graph data).

Use the CLI to validate, execute, package, or unpack a project:

```powershell
uv sync --locked --extra dev
uv run openrpa validate examples/csv-cleanup/project.json
uv run openrpa run examples/csv-cleanup/project.json
uv run openrpa pack examples/csv-cleanup .\csv-cleanup.orpa
uv run openrpa unpack .\csv-cleanup.orpa .\csv-cleanup-copy
```

Package export is deterministic for the same source contents, carries per-file SHA-256 integrity checks, and excludes environment files, key material, and certificates. Workflow and package validation limits are enforced before execution or extraction.

## Development

The codebase has three primary components:

- `src/studio/`: React/TypeScript application, visual authoring components, state helpers, and Tauri RPC client.
- `src-tauri/`: Rust desktop shell, secure local bridge process lifecycle, OS dialogs, and release bundle configuration.
- `openrpa/`: Python workflow format, validator, execution engine, activities, browser inspector, provider adapters, debugger, package manager, and durable run history.

Install and run the editor in development mode:

```powershell
cd open-rpa-studio
uv sync --locked --extra dev
npm ci
npm run tauri dev
```

The desktop host starts the Python module in development when `OPENRPA_PYTHON` is not configured; set it to the desired Python executable to select another interpreter. On Windows, the bridge runs with redirected standard streams and `CREATE_NO_WINDOW`; it must not open a terminal window. Packaged Windows releases instead launch `engine/openrpa-bridge-<version>.exe` from the installer resources and do not look for Python on `PATH`.

For browser automation and local browser inspection in development, install the browser extra and Chromium as shown above. For OS keyring and desktop extras, use:

```powershell
uv sync --locked --extra dev --extra browser --extra desktop --extra credentials
```

## Tests and verification

Run focused checks:

```powershell
uv run --locked --extra dev pytest -q
npm test
npm run build
```

Build and smoke-install the Windows release using `npm run build:windows-installer`. The changelog records release smoke evidence and artifact hashes. The Tauri host uses Windows `CREATE_NO_WINDOW` for the bridge subprocess to prevent a console window from appearing.

## Known gaps

This project has not yet reached the stated beyond-UiPath parity goal. The editor supports sequences, flowcharts, and state machines, but major unfinished areas include automatic fuzzy selector healing (explicit fallback chains are supported), broader cross-toolkit accessibility acceptance, production-grade plug-in/package signing, upgrade/uninstall and clean-machine installer testing, workflow collaboration, unattended scheduling/orchestration, and adversarial security review. Desktop application launch is available only to workflows with per-run desktop permission; it starts an explicitly configured executable and argument list without a shell, but it is not a sandbox. The included installer is a development artifact, unsigned, and not production-certified. The `examples/` workflows are fixtures and should be reviewed before execution.

The current Windows installer bundles the engine bridge and its Python dependencies, but not a Playwright browser binary. Browser adapter readiness is detected at runtime; install a matching browser binary separately if browser automation is required. Windows Desktop automation via PyAutoGUI may require interactive session access and explicit user permissions.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [SQLite Query activity](docs/SQLITE-ACTIVITY.md)
- [Security model and reporting](SECURITY.md)
- [Adapter details and limitations](docs/AUTOMATION_ADAPTERS.md)
- [AI workflow drafting: supported structures and live verification](docs/AI-DRAFTING.md)
- [Workflow format and execution models](docs/WORKFLOW-FORMAT.md)
- [Product roadmap](docs/ROADMAP.md)
- [Reverse-engineering evidence and behavior notes](docs/REVERSE_ENGINEERING_EVIDENCE.md)
- [CycloneDX SBOM](sbom.cdx.json)

## License

See [LICENSE](LICENSE).
