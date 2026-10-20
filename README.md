# Open RPA Studio

Open RPA Studio is a local-first, open-source desktop environment for visually authoring and executing automations. It is an independent application: it does not use Flowbench code, services, branding, or runtime components.

This repository contains the editor, the versioned workflow format, a separate Python execution engine, optional automation adapters, and packaging/build scripts. The product is under active development. It is a capable early release, not yet a certified enterprise RPA platform or a complete UiPath replacement.

![Open RPA Studio desktop workspace](docs/assets/studio-overview.png)

## Download and install

The Windows setup executable built and smoke-installed during development is published as the unsigned development pre-release [Open RPA Studio v0.1.4](https://github.com/stevenmcsorley/open-rpa-studio/releases/tag/v0.1.4). The installer is also present locally at `release/Open-RPA-Studio-Setup-0.1.4-x64.exe` after running the build command below.

The NSIS installer supports a per-user installation and uninstall. The app bundle includes a frozen Python bridge, so Python does not need to be installed on the target computer. Windows WebView2 is required; current Windows 10/11 installations normally provide the Evergreen runtime. The packaged Playwright adapter also needs a browser binary. Browser binaries are not included in this installer, so browser automation will report unavailable until Chromium is installed in a compatible Playwright environment. Runtime capability status is displayed by the app rather than inferred from package presence.

The installer is unsigned in this development build. Windows SmartScreen may show an unknown-publisher prompt. Published installer SHA-256: `7aa27dc3f5708261aaa521b05b21f18535a293b33e0795be011fa1ce9454300e`. Verify the file before running it:

```powershell
Get-FileHash .\release\Open-RPA-Studio-Setup-0.1.4-x64.exe -Algorithm SHA256
```

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
- Create and open local projects, add workflows, save, validate, and inspect validation problems.
- Search a categorized activity catalog, configure activity properties, reorder sequence actions, and edit nested control-flow branches.
- Author either a sequence or a flowchart. Flowcharts include Start, action, Decision, and End nodes; transitions, positions, and edits persist in the workflow file.
- Author a state machine with named states, per-state activity sequences, ordered boolean guards, an explicit initial state, and terminal states. State visits obey the workflow execution quota; interrupted workflows are not automatically replayed.
- See the [workflow format and state-machine example](docs/WORKFLOW-FORMAT.md) and the [architecture notes](docs/ARCHITECTURE.md).
- Convert a linear flowchart to a sequence when it contains no branches or loops.
- Insert ordinary activities in the selected flowchart path while preserving downstream transitions.
- Use the visible, permission-gated Playwright inspector to discover named page controls and add editable click, fill, select, check, uncheck, and read-text actions.
- Generate a candidate workflow from an optional AI provider, review the validation output, then explicitly insert the draft. Generated workflows are not run automatically.
- Choose whether AI drafts an activity sequence, connected flowchart, or state machine. Model-specific schemas and the same local workflow validator are applied before a draft can replace the current workflow.

### Workflow execution

The Python engine is separate from the UI process and can also run from the command line. Supported control flow includes If/Else, For Each, While, Switch, Retry Scope with explicit repeat-safety acknowledgement, Try/Catch/Finally, flowcharts, and reusable workflow invocation with typed arguments. The expression evaluator accepts a bounded expression grammar and never calls `eval()` on workflow text.

Core activities include variable assignment and logging; credential lookup by vault reference; file read/write/copy/move/delete/list operations; text/regex processing; JSON and CSV transforms; wait; HTTP requests; browser actions; screenshots; and optional desktop coordinates. Activity permissions, quotas, validation, structured logs, and execution status are handled by the engine, not simulated by the editor.

### Debugging and run history

- Boundary-based breakpoints and debugger start-paused mode.
- Pause, continue, step-over, step-into, step-out, and cancellation at activity boundaries.
- Inspect variables and edit supported JSON-compatible values while paused, subject to type and credential protections.
- Durable SQLite run history records workflow digests, times, statuses, activity events, errors, and security audit events.
- Interrupted runs are marked for inspection; they are never resumed or repeated automatically because prior activities may have changed external systems.

### Optional AI providers

The core editor and execution engine work without an AI model or network access. Workflow drafting has adapters for:

- Ollama.
- LM Studio.
- OpenAI-compatible local servers on loopback.
- OpenAI API (including API access to OpenAI models; a ChatGPT subscription is not an API credential).
- Anthropic Claude API.
- OpenRouter.
- Compatible remote HTTPS endpoints configured by the user.

Provider credentials are references into the operating-system credential vault (Windows Credential Manager, macOS Keychain, or Linux Secret Service). Secrets are never placed in workflow files or AI prompts. Remote prompts disclose the provider route before a request. AI output is treated as untrusted, parsed as a bounded schema, validated by the workflow validator, and requires user review before insertion. Local models are optional; unavailable providers do not disable non-AI features.

This is a set of provider-protocol adapters, not a promise that every model endpoint implements tool calling or structured output identically. Some compatible servers may reject schema-constrained requests.

### Browser and desktop adapters

Browser activities use Playwright with role, label, text, placeholder, test-id, or CSS selectors. The library includes explicit element waits and visible/hidden/enabled/disabled/checked/text assertions with activity-scoped timeouts. The Browser Inspector uses a visible browser, permission-gated navigation, request destination checks, and editable selector-based actions. Its interaction recorder captures bounded click, fill, selection, and checkbox actions for uniquely identified named controls, including across page navigation in one browser tab. It records selector metadata only: it does not read typed values, and it excludes password, email, payment, file, and hidden fields. Generated fill/select activities have blank values and must be reviewed before use. The bridge checks Playwright and Chromium availability at runtime. Install Chromium for development with:

```powershell
uv sync --locked --extra dev --extra browser
uv run playwright install chromium
```

Linux coordinate-based desktop actions use optional PyAutoGUI and require explicit per-run permission. AT-SPI/AT-SPI2 accessibility inspection is not implemented yet; a capability check reports this rather than presenting it as supported. Coordinate automation is inherently less resilient than semantic selectors and should be used only where an accessible interface is unavailable.

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

The desktop host starts the Python module in development when `OPENRPA_PYTHON` is not configured; set it to the desired Python executable to select another interpreter. On Windows, the bridge runs with redirected standard streams and `CREATE_NO_WINDOW`; it must not open a terminal window. Packaged Windows releases instead launch `engine/openrpa-bridge.exe` from the installer resources and do not look for Python on `PATH`.

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

Build and smoke-install the Windows release using `npm run build:windows-installer`. The v0.1.4 installer was installed silently into an isolated workspace-local directory. Its bundled bridge generated and executed sequence, flowchart, and state-machine drafts through Ollama without relying on a separately installed Python runtime. The run IDs and artifact hash are recorded in [the changelog](CHANGELOG.md). The Tauri host uses Windows `CREATE_NO_WINDOW` for the bridge subprocess to prevent a console window from appearing.

## Known gaps

This project has not yet reached the stated beyond-UiPath parity goal. The editor supports sequences, flowcharts, and state machines, but major unfinished areas include editable selector healing, accessibility-first Linux desktop automation, production-grade plug-in/package signing, upgrade/uninstall and clean-machine installer testing, workflow collaboration, unattended scheduling/orchestration, and adversarial security review. The included installer is a development artifact, unsigned, and not production-certified. The `examples/` workflows are fixtures and should be reviewed before execution.

The current Windows installer bundles the engine bridge and its Python dependencies, but not a Playwright browser binary. Browser adapter readiness is detected at runtime; install a matching browser binary separately if browser automation is required. Windows Desktop automation via PyAutoGUI may require interactive session access and explicit user permissions.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Security model and reporting](SECURITY.md)
- [Adapter details and limitations](docs/AUTOMATION_ADAPTERS.md)
- [AI workflow drafting: supported structures and live verification](docs/AI-DRAFTING.md)
- [Workflow format and execution models](docs/WORKFLOW-FORMAT.md)
- [Product roadmap](docs/ROADMAP.md)
- [Reverse-engineering evidence and behavior notes](docs/REVERSE_ENGINEERING_EVIDENCE.md)
- [CycloneDX SBOM](sbom.cdx.json)

## License

See [LICENSE](LICENSE).
