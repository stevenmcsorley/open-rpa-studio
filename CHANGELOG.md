# Changelog
## Unreleased

- Added Read Web Table, a Playwright activity that extracts a unique HTML table into editable workflow records with duplicate-header handling, optional header rows, strict row/column/response-size/time limits, pre-run read classification, and explicit errors instead of silent truncation. Added authoring support in the browser preview, regression coverage, documentation, and a public Studio screenshot.
- Added a product roadmap that sets the next major capability as a visual API connector builder with reusable OS-vault-backed API connections, API-key and OAuth 2.0 authentication, bounded pagination, rate limits, response mapping, and AI-safe connection references.
- Verification for Read Web Table: all 227 Python tests and 118 frontend tests pass; the production frontend and Windows release installer build; a real Playwright Chromium run extracts and bounds table data; the freshly installed bridge exposes the activity and accepts its schema. The v0.1.30 NSIS installer is 69.05 MiB, unsigned, SHA-256 `ce0fea0d9d95bc1147f689fe5094b79564b9c7585117634bb2615613520c5f62`.
- Added OCR Image, an optional local Tesseract activity for PNG, JPEG and BMP files. It probes runtime availability, preflights images with Pillow, enforces 30-megapixel/input/output/time limits, checks cancellation, redacts secret-like environment variables from the subprocess and records local audit evidence. Added an executable packaged-bridge OCR acceptance check and a public Studio screenshot.
- Added Map Rows, Distinct Rows and Validate Rows for bounded, non-mutating data preparation, typed-key deduplication and explicit schema validation with structured row errors.
- Verification: 225 Python tests, 116 frontend tests, production frontend build, frozen-bridge Pillow acceptance check and a real Tesseract workflow recognizing `OPEN RPA LOCAL OCR 2026` all pass. Current-source CI is pending.

- Added project-wide search across workflows, nested activities, sequence branches, flowchart nodes and transitions, state-machine states and transitions, and variable/argument names. Ctrl+Shift+F opens a navigable result list capped at 100 results. Credential-like fields and variable/argument default values are excluded. Added a public screenshot.
- Verification: all 77 frontend tests pass, including nested-path matching, graph/state coverage, secret-field exclusion and result caps. The production build passes; Playwright verified search results and selecting a match navigates to its editable activity. Python remains at 181 passing tests.
- Extended conditional breakpoints to flowchart control nodes and state-machine entries. The native debugger evaluates each expression at the boundary before execution, continues only when the condition is false, and fails closed by pausing on invalid expressions. Added a public screenshot of the state-entry inspector.
- Verification: all 181 Python tests pass, including schema validation and real debugger runs paused at conditional graph and state boundaries; all 72 frontend tests and the production build pass. Playwright captured the state-machine breakpoint editor.
- Improved OpenAI-compatible draft parsing across LM Studio, OpenRouter and compatible endpoints: accepts text content blocks and a complete `json` fence, and reports refusal, truncation, tool-only and malformed output explicitly.
- Verification: 25 provider tests and the full 181-test Python suite pass, including response-shape cases for LM Studio, OpenRouter and local/remote compatible endpoints. CI verification pending.
- Made the Output pane collapsible and resizable by pointer or keyboard. Its size is bounded by the available viewport so the minimum designer height remains visible; Home/End set bounds and Escape restores the default. Updated public screenshots.
- Verification: all 72 frontend tests pass; TypeScript and production Vite build pass. Playwright verified drag resizing, ArrowUp, Home, End, Escape reset, and automatic clamping on a 650 px viewport; browser console reports zero errors.
- Added a scoped, navigable activity outline for the selected flowchart action. It exposes nested branch paths, selects nested activities in the existing inspector, and keeps the containing graph action highlighted. Added a public browser-preview screenshot.
- Verification: 69 frontend tests pass; TypeScript and production Vite build pass. Playwright converted the sample workflow to a flowchart, added an If action and nested Log activity, and confirmed the action outline lists both activities while the nested Log is selected.
- Flowchart action inspectors now expose the existing nested sequence editor for If/Else, loops, Switch, and Try/Catch/Finally activities. Nested edits update the activity stored on the graph action node; branch additions, field edits, duplication and removal remain inside that node. Added tested graph-tree operations for locating, patching, appending and removing nested activities.
- Verification: 69 frontend tests pass; all 170 Python tests pass; TypeScript and production Vite build pass. Playwright added a flowchart If action, added and selected a nested Then activity, duplicated and removed it within the same action, and validated the workflow with zero problems and no console errors.
- Made sequence-canvas zoom functional with a live percentage, 10% increments, 50–150% bounds, and one-click reset; graph editors retain their own zoom controls. Kept the nested workflow outline pinned to its canvas viewport during scroll so deep-branch navigation remains available after jumping to an activity.
- Verification: 66 frontend tests pass; TypeScript and production Vite build pass. Browser preview verified zoom in (100%→110%) and reset, then selected a nested branch activity and confirmed the outline remained visible while the activity and its properties were brought into view.
- Added a navigable workflow outline for sequence workflows. It lists nested activities with their If/Else, loop, Try/Catch/Finally, and Switch branch context; selecting an entry selects the activity, scrolls it into view, and opens its properties. Added nested branch and Switch outline tests plus a public screenshot.
- Verification: 64 frontend tests pass; TypeScript and the production Vite build pass. Playwright preview confirmed outline expansion, live nested-branch updates, selection, and property inspection without console errors.
- State-machine graph edges are now directly editable: select an edge to change its destination or guard, reorder guarded routes, remove it, or add a new safe `False`-guarded route. Blank guards remain the final fallback, and duplicate fallbacks are rejected. Added regression tests and a public README screenshot of the actual editor.
- Verification: all 62 frontend tests pass; TypeScript and the production Vite build pass; `git diff --check` passes. Screenshot captured from the live browser preview.

- Added request-ID-scoped AI draft cancellation across Studio, the native bridge and provider HTTP transports. Cancellation interrupts socket waits and discards late results; requests already received by a provider may continue server-side.
- Verification: the native-bridge cancellation regression, 169 Python tests, 58 frontend tests and the production Vite build pass.

- AI model selection now accepts an exact manually entered provider model ID when an endpoint does not expose or filters its model catalogue; saved model IDs are preserved across a catalogue refresh.
- Added a distinct catalogue-unavailable status so a missing `GET /models` route does not incorrectly imply the generation endpoint is unusable.
- Added a flowchart minimap showing graph topology, selected node and the visible canvas viewport, with pointer and keyboard navigation.
- Fixed large flowcharts expanding the designer beyond its allocated workspace; long graphs now scroll inside the canvas. The Fit control accounts for both graph dimensions.
- Added a state-machine transition overview generated from saved states and guards; selecting a state in the graph opens its existing editable state panel.
- Refreshed public README screenshots to show both graph editors.
- Verification: 58 frontend tests, the production Vite build, and 33 targeted AI adapter/profile tests pass. A localhost OpenAI-compatible mock returned HTTP 404 for `/models` and successfully generated a validated-shape draft using a manually supplied model ID.

## 0.1.28 — Local MCP server for AI clients

- Added a provider-neutral Model Context Protocol stdio server for one explicitly selected local project. Tools list workflows, read and validate workflows, inspect permission plans, update a workflow with an expected SHA-256 and opt-in validation, and (only when enabled at startup) run workflows through the existing engine.
- The server has no network listener, accepts no client-selected filesystem paths, bounds protocol frames and results, keeps protocol output on stdout, and sends diagnostics to stderr. Execution, network, desktop, OS-vault credentials and file move/delete permissions are separate startup opt-ins; permission discovery follows statically invoked workflows.
- Added cooperative MCP cancellation notifications and durable, per-project MCP run records with status, activity events, hashes and recovery warnings. MCP run history is separate from Studio's interactive run-history database.
- Extended the frozen Windows engine executable to expose the same CLI/MCP server when launched with command-line arguments, so installed users can configure a local MCP client without installing Python or adding another large bundled runtime.
- Added tests for the stdio handshake, notifications, tools, project confinement, nested destructive-permission detection, disabled execution and real engine execution.
- Verification: 166 Python tests, 50 frontend tests, production Vite build, zero npm audit findings, offline Cargo check and `git diff --check` passed. The 61.52 MiB unsigned Windows installer installed into a clean isolated folder; the installed executable passed MCP handshake, default permission denials, validated workflow edit, separate credential permission guard and real opt-in workflow execution. CycloneDX SBOM lists 479 locked components. Installer SHA-256: `cfdf6a57612fccb8a6491b28a52c1e400ed904a91b028fa9801c1d6c14c927f6`.

## 0.1.27 — Bounded read-only SQLite integration

- Added the native **Query SQLite Database** activity for approved local database files. Query parameters are bound through SQLite rather than inserted into SQL text.
- Enforces `mode=ro`, `query_only`, `trusted_schema=OFF`, disabled extension loading and an authorizer allowlist. Write/DDL, `PRAGMA`, `ATTACH`, temp database reads and multiple statements are rejected.
- Adds bounded row, input-file, output-size and query-time limits. SQLite VM progress callbacks enforce deadlines and cancellation; lock waits are capped at 500 ms.
- Returns JSON-compatible rows, deterministically renames duplicate columns, and tags BLOB values as base64. Records query attempts and completion counts without recording SQL or parameter values. Audit paths now remain root-relative for explicitly approved external roots.
- The browser preview validates this desktop-only activity and reports its filesystem-engine requirement.
- Verification: 159 Python engine tests, 50 frontend tests across 8 files, production frontend build, offline Cargo check, `npm audit --audit-level=moderate` (zero vulnerabilities), and `git diff --check` passed. The 61.49 MiB unsigned Windows x64 installer was installed into a new isolated directory. Its frozen bridge executed a parameterized read from a local database, stored attempt/completion audit records without SQL text or values, and blocked a `DELETE` while confirming that the database remained unchanged. The installed app launched and its only child process was the expected `openrpa-bridge.exe`; no terminal process appeared. CycloneDX SBOM: 479 locked components. Installer SHA-256: `e909efa5221ea41515a101598062abfaacc82cb6673cac1c2f356e37d62552e9`.

## 0.1.26 — Bounded PDF text extraction

- Added the native **Read PDF Text** activity for selectable text, form-feed page boundaries, a page-count output, optional layout-oriented extraction, cancellation between pages, and configured input/output size limits.
- Enforces `.pdf` input, rejects encrypted files, and validates distinct output variables plus a configurable 1–5,000 page limit. The browser preview validates settings and clearly requires the desktop filesystem engine to execute.
- Added PDF read entries to the impact review and audit trail. Documented that image-only pages are not OCR and that layout extraction does not reconstruct tables.
- Added pypdf 6.21.1 as a locked runtime dependency.
- Verification: 139 Python tests, 48 frontend tests, production frontend build, offline Cargo check, zero npm audit vulnerabilities, and a 479-component SBOM passed. The 61.49 MiB Windows x64 installer installed into a fresh directory; its frozen bridge validated and ran a two-page PDF extraction with page boundaries and durable run evidence. Existing installed-bridge checks for AI model discovery/drafting, saved profiles, debugger watches and spreadsheet security also passed. Installer SHA-256: `2b3308bd4f8c06640109cea75f73c31973662d120b633c76fa089db969343cad`. GitHub CI passed (run 39531354859).

## 0.1.25 — AI provider connection diagnostics

- Added an explicit endpoint check beside model selection. The native provider adapter now reports connection success, available model count and request duration, distinguishes an empty model catalogue, and presents provider errors as an accessible status alert.
- Changing providers or saved profiles clears stale connection health so the UI never implies an untested endpoint is still connected.
- Supports the existing Ollama, LM Studio, OpenAI, OpenAI Responses, Anthropic Claude, OpenRouter and compatible endpoint adapters; the check uses model discovery and does not submit a prompt.
- Verification: 136 Python tests, 46 frontend tests, production frontend build, offline Cargo check and SBOM generation passed. The 60.78 MiB unsigned Windows x64 installer installed to a fresh directory; its frozen bridge passed credential-free model discovery (two local model IDs) and structured AI draft acceptance. Installer SHA-256: `1560e7deb150f7928101308e103797976ee06b8246335d7e0864e072bb764daa`. GitHub CI passed (run 39529520042).

## 0.1.24 — Provider message contract and prompt separation

- Fixed the Claude Messages API request to include the required user `messages` payload alongside its system policy and forced structured-output tool.
- Separated user task text from system instructions across Claude, OpenAI Chat Completions, OpenAI Responses, OpenAI-compatible and Ollama adapters. Task text is JSON encoded and remains untrusted input.
- Added installed-bridge acceptance against a local OpenAI-compatible contract server; no external provider or credential is required for the test.
- Verification: 136 Python tests, 44 frontend tests, production Vite build, offline Cargo check, `npm audit` with zero vulnerabilities, and installed Windows acceptance for provider request message separation, validated draft output, credential-free local endpoint, debugger watches and conditional breakpoints, spreadsheet processing and saved provider profiles. GitHub CI passed (run 39527704827).

## 0.1.23 — Conditional activity breakpoints

- Added optional safe-expression conditions to activity breakpoints. False conditions continue execution; true conditions pause at the boundary.
- Invalid or non-Boolean conditions pause for review instead of silently skipping a breakpoint. Workflow validation bounds conditions to 2,048 characters and requires an enabled breakpoint.
- Verification: 135 Python tests, 44 frontend tests, production Vite build, offline Cargo check, `npm audit` with zero vulnerabilities, and installed Windows bridge acceptance for false/true/invalid conditions plus watches and safe resume. GitHub CI passed (run 39526203667).

## 0.1.22 — Live debugger watch expressions

- Added watch expressions to the paused debugger panel. They evaluate against the engine's current full scope using the same restricted expression evaluator as workflows.
- Watch evaluation is permitted only at an activity boundary while paused, rejects Python code, redacts registered credentials, limits expression length to 2,048 characters, and truncates serialized results beyond 16 KiB.
- Watch expressions and results are session-only; they are not stored in projects, run history or the audit trail.
- Verification: 44 frontend tests, 132 Python tests, production Vite build, offline Cargo check, `npm audit` with zero vulnerabilities, Windows installer launch, frozen-bridge debugger-watch acceptance, and spreadsheet acceptance. GitHub CI passed.

## 0.1.21 — Patched frontend build and test dependencies

- Upgraded Vite and its React plugin to supported patched major versions, and Vitest/Tinypool to versions without the advisories reported by npm audit.
- Declared the Node.js compatibility range required by the build plugins.
- Verification: `npm audit` reports zero vulnerabilities; 42 frontend tests, 130 Python tests, production build and offline Cargo check passed. Windows x64 installer built (60.77 MiB); SHA-256: `765ae50bfa40f50d1c64a5b3664da8492f4a2efe616cca01a18cee0985673ccd`. Fresh isolated install and launch passed; only the expected bundled `openrpa-bridge.exe` child appeared. The installed bridge passed XLSX round-trip, XML DTD/entity rejection and persisted `run.get` event-timestamp verification.

## 0.1.20 — Inspectable durable run history

- Replaced the bare run-history list with a selectable execution record showing activity status and duration, stored events and their durable timestamps, workflow digest, error details, and interruption guidance.
- Interrupted executions explicitly warn that external side effects are uncertain. History is for inspection; it does not offer a resume or replay action.
- The history panel avoids displaying the machine-specific project path.
- Verification: 42 frontend tests, 130 Python tests, production Vite build, offline Cargo check, targeted interruption-history test; Windows installer build produced a 60.77 MiB NSIS package. Installer SHA-256: `587cc881c5b8f1b37ef1be9fa79885f5c033ab642ac6da492276b04130a82600`. CycloneDX SBOM contains 478 dependency components; fresh isolated install and launch passed. The bundled bridge passed spreadsheet read/write, XML DTD/entity rejection, and live `run.get` verification including persisted event timestamps. No terminal process was launched.

## 0.1.19 — Provider-neutral AI failure repair

- Added a repair-from-failure path to the existing AI workflow panel. It captures the workflow snapshot and structured failure identifiers, then uses the same configured provider, workflow validator and review-before-replace path as normal drafting.
- The provider prompt omits runtime variable values, argument defaults, error messages and fields whose keys look like secrets. It warns that configured workflow literals, including paths, URLs, selectors and strings, may be sent to a remote provider.
- Added privacy and immutability tests for the repair prompt, and refreshed the public README screenshot with the current Studio interface.
- Verification: 40 frontend tests, 130 Python tests, production Vite build, offline Cargo check, and a 60.77 MiB Windows x64 installer build. Installer SHA-256: `36b819df8c0b6014a73d3a37b6e3547b78336c03c13513df4a515a09a13477b1`. CycloneDX SBOM contains 478 dependency components. Fresh-install acceptance: the installer completed in an isolated directory, the installed app launched with only its expected `openrpa-bridge.exe` child (no terminal process), and the frozen bridge passed the spreadsheet read/write and XML entity rejection fixture.

## 0.1.18 — Per-run impact review

- Added a pre-run impact review for normal and debug execution. It inventories file reads/writes, HTTP destinations, browser and desktop actions, credential reads, destructive file operations, and saved child-workflow actions across sequences, nested branches, flowcharts and state machines.
- Network and desktop access are granted for the specific run from the review dialog; saved toolbar toggles no longer silently grant those permissions to unrelated workflows. Missing child workflow definitions trigger fail-safe network and desktop approval prompts.
- Screenshot and file-copy output paths are shown as writes; move/delete operations are highlighted as destructive. The review warns that expressions may change actual runtime targets.
- Added planning tests for nested/reusable workflows, flowchart and state-machine coverage, destructive actions, output paths and fail-safe handling of unavailable children. Refreshed the README screenshot with the live run-impact review.
- Verification: 37 frontend tests, 130 Python tests, production frontend build, offline Cargo check and real Playwright preview interaction/screenshot. The 60.77 MiB installer silently installed in a fresh temporary directory; the installed app launched with its bundled bridge and no terminal process, and the bridge passed its XLSX round-trip/entity rejection acceptance fixture. Installer SHA-256: `a4f13147608917e4f32d8f57f953301d8d30ae76b03946b986c19cefd9d80bef`. CycloneDX SBOM contains 478 dependency components. GitHub CI follows this commit.

## 0.1.17 — Local Excel workbook activities

- Added executable XLSX Read and Write activities for local desktop workflows, including worksheet selection, header rows, data-only formula values, audit records, atomic writes, and formula-like text safety.
- Enforced workbook size, row, column, cell and ZIP expansion limits; reject non-unique headers, invalid worksheet names and unsupported cell types. The browser preview lists these activities but clearly refuses execution without filesystem access.
- Made defusedxml a locked runtime dependency and configured openpyxl to use its hardened parser; an entity-expansion regression test verifies this runtime behavior, and the XLSX archive preflight rejects DTD/entity declarations before parsing.
- Added documentation, a live desktop-engine workbook round trip, malicious archive and configuration tests, plus an installed-bridge packaging acceptance fixture.
- Verification: 130 Python tests, 31 frontend tests, production build, offline Cargo check, hardened openpyxl parser check, browser editor screenshot and activity insertion, and a 60.77 MiB Windows x64 installer silently installed to an isolated directory. The installed bridge completed an XLSX write/read round trip and rejected an XML entity declaration before parser execution. Installer SHA-256: 3741d81354aae2c602c392d867a520870d5b804dfc54628b014a3d47bf218b59. The SBOM contains 478 locked components. GitHub CI follows this commit.
## 0.1.16 — Internal activity clipboard

- Copy and paste complete activity subtrees with toolbar controls or Ctrl/Cmd+C and Ctrl/Cmd+V. Paste inserts after the current selection; every inserted activity and descendant gets fresh IDs.
- The Studio clipboard works across workflows and stays inside the application; it does not read or modify the operating-system clipboard. Sequence, state-machine and flowchart action paths are supported.
- Refreshed the README screenshot with the copy and paste controls and resulting workflow steps.
- Verification: 30 frontend tests, including recursive subtree ID remapping; 125 Python tests; production Vite build; offline Cargo check; Playwright browser-preview toolbar copy/paste and Ctrl+C/Ctrl+V raised the activity count from two to four with no console errors; 59.92 MiB Windows x64 NSIS installer built and silently installed; bundled bridge passed reusable-workflow acceptance. Installer SHA-256: `5cb79721f8fdc605c5a52c2c437e2a226de159fd9ee63b45582d644aee36883d`. CycloneDX SBOM: 475 dependency components.
## 0.1.15 — Duplicate activity subtrees

- Duplicate an activity beside its source from the canvas toolbar or Ctrl/Cmd+D. Nested branch and switch descendants are deep-copied with fresh IDs, avoiding collisions in selection, breakpoints and execution state.
- Supports sequence trees, state-machine activity sequences and flowchart action nodes.
- Refreshed the repository screenshot with the duplicate control and resulting copied step visible.
- Verification: 29 frontend tests, including nested branch and switch remapping; 125 Python tests; production Vite build; offline Cargo check; Playwright browser-preview duplication increased the activity count from two to three; 59.92 MiB Windows x64 NSIS installer built and silently installed in an isolated directory; the installed bridge passed reusable-workflow argument acceptance. Installer SHA-256: `8ee7a431d2c70dd6ba751ea27426bd2182172659c1c7e3b38c90055a7e0b8500`. CycloneDX SBOM: 475 locked dependency components.

## 0.1.14 — Bounded workflow undo and redo

- Added per-workflow, bounded 100-snapshot undo/redo history for authoring changes, with toolbar buttons and Ctrl/Cmd+Z, Ctrl/Cmd+Y, and Ctrl/Cmd+Shift+Z shortcuts.
- New edits clear the redo branch; switching workflows preserves each workflow's history, while opening, creating or importing a project clears prior-project history.
- Refreshed the README screenshot to show the undo and redo controls in the visual editor.
- Verification: 27 frontend tests, 125 Python tests, production Vite build, offline Cargo check and SBOM generation (475 components) passed. A Playwright browser-preview interaction test changed a breakpoint, used toolbar undo/redo and Ctrl+Z/Ctrl+Y, confirmed a new edit clears redo, and verified button availability and restored values. The 59.92 MiB Windows x64 installer built with SHA-256 `db075a8e057dbc69eabb7d403032d56f4883acb4a247224d8fc5043732410dd5`, silently installed, and its frozen bridge passed reusable-workflow acceptance (bridge SHA-256 `df5caf05b1ebd8533b142928e7d27e5e46dacc4fa9bb171fc4680dc27d94e9c0`). GitHub CI results are recorded after publication.

## 0.1.13 — Flowchart canvas navigation and edge editing

- Pan large flowcharts with Space+drag or middle-button drag and center the selected node without changing graph coordinates.
- Reconnect an existing True, False or Next edge by dragging its connector handle onto a destination node; keep the destination selector for keyboard and accessible editing.
- Validate graph identities, node kinds and branch compatibility centrally before saving edge changes.
- Refreshed the README screenshot with a valid branched workflow and the current canvas controls.
- Verification: 25 frontend tests, 125 Python tests, Vite production build, offline Cargo check, SBOM generation (475 components), and a fresh silent Windows installation passed. The installed bridge passed the reusable argument/output binding acceptance fixture. Installer (59.92 MiB) SHA-256: `5cfdf06dc1d355a3309b37e9610822061a4c678363b0c03d3b3eea8a78e001ed`; installed bridge SHA-256: `ffddc7858b03b9937fa49ccc13708a025efb0b2102a30b8c2bf74a34464e86e4`. The flowchart preview was validated and a drag operation completed without client errors.

## 0.1.12 — Reusable workflow argument mapping

- Added a dedicated Invoke Workflow properties editor that lists project workflows and their declared inputs/outputs, supports typed input bindings, per-call output destinations and new-variable result collection.
- Added project-level binding checks for missing required inputs, unknown names, invalid directions and output target names before save and run.
- Added per-invocation `outputs` mappings to the Python engine while preserving existing argument-level output targets for old workflow files.
- Brought nested reusable-workflow execution and typed argument transfer to the browser preview; run events now identify their workflow.
- Verification: 125 Python engine tests, 24 frontend tests, production build and offline Rust check passed. A fresh isolated silent NSIS installation succeeded; the installed bridge passed typed input preflight plus two independent output mappings through real workflow execution. Installer SHA-256: `404cace5effd4dad4c4e3392b8afa05f6e4bc8d47f92e25bc22f41e85970eb39`.

## 0.1.11 — Nested workflow error context

- Preserve the original failing workflow/activity and add a bounded call path for nested `invoke_workflow` failures.
- Include the structured origin and up to 40 workflow-call frames in run results and durable history; redact known credential values from all frame text.
- Show the call path in the Studio's existing Problems panel so failures inside reusable workflows can be traced to the caller.
- Verification: 123 Python tests, 22 frontend tests, production build, offline Rust check and installed Windows bridge call-path/history acceptance passed. The v0.1.11 installer was unsigned; its SHA-256 was `c4bd507eb828da19712504c4eb26572f82c57c83ced387e1736d92d1f14bdafe`.
- Verification: 123 Python tests, 22 frontend tests, frontend production build and offline Rust check passed. Windows x64 NSIS installer built and silently installed in an isolated directory. The installed bridge completed a nested-workflow failure scenario, returned the original failing workflow/activity and two caller frames, and persisted the same diagnostic in run history. A regression also confirms Unicode call-path text survives the Windows bridge protocol. Installer SHA-256: `c4bd507eb828da19712504c4eb26572f82c57c83ced387e1736d92d1f14bdafe`.

## 0.1.10 — Project package workflows

- Add desktop toolbar actions for deterministic `.orpa` project package export and import.
- Export saves current in-memory changes first, validates every workflow, emits a digest, and uses the existing secret-file exclusions.
- Import verifies package paths, manifest entries, sizes and SHA-256 hashes before extracting into an empty selected folder; it asks before replacing the open Studio project.
- Correct the README's Linux accessibility note to reflect the implemented AT-SPI support.
- Verification: 121 Python tests, 22 frontend tests, production build and Rust check passed. Windows NSIS installer built and silently installed in an isolated directory; installed bridge successfully exported, hash-verified and imported a project package. Installer SHA-256: `f73a8d8b8a0b51c0e2dc8b215e856e35b0d4b7ecde2cbf58492fadf7d701a89e`; installed bridge SHA-256: `f620d597b1ef0290eb164b96865b885a3f37015cd5e2fee60c2af2e5e4b383c4`.

## 0.1.8 — Saved AI provider connections

- Added persistent, named AI connection profiles for local and hosted providers. Profiles remember provider, endpoint, model and OS-vault references across app launches.
- Added strict profile schema validation, URL security checks, unique names/IDs, a 100-profile cap, one-megabyte file cap, atomic local writes and update/delete controls. The profile format rejects credential values and unknown fields.
- Added native bridge operations and metadata-only audit events. Removing a profile does not remove its OS-vault credential.
- Refreshed the public Studio screenshot.

### Verification

- AI profile tests: 10 passed; provider tests: 14 passed; full Python suite: 116 passed; frontend suite: 22 passed; production build, locked Rust check, dependency lock check and SBOM generation passed.
- Windows x64 NSIS installer built (59.90 MiB), SHA-256 `1f25240d0f30308e052961e78d61422b780c6bf95b38a041600afa8f19207367`.
- Fresh silent install passed. Installed bridge SHA-256 `39035b54dc0ce025dd3fde49a87a45757757308a56511e4385f0a5a7bdb7edc3` matched the build resource.
- Installed-bridge regression saved a provider profile, restarted the bridge, listed the persisted profile, deleted it, and confirmed it was gone. No API-key field was stored.

## 0.1.7 — In-app AI credential setup

- Added secure API-key onboarding to the desktop AI panel for Anthropic, OpenAI, OpenRouter and compatible remote providers. Keys are sent to the local bridge, stored through the approved OS credential vault and cleared from the form.
- Added bounded input validation and an audit record that retains only the vault service/account reference. Vault write errors are sanitized so keyring exceptions cannot echo credential values.
- Added regression tests for secure storage, unsafe-vault rejection, invalid values and secret-free audit/error output.

### Verification

- Provider and credential bridge tests: 24 passed; full Python suite 106 passed, frontend suite 22 passed, production frontend build passed.
- Windows x64 NSIS installer built (59.89 MiB), SHA-256 `a0e16e982b86e0751cff9801af42deca7fa8d32a62b6157964fb3d51e73a6df4`.
- Fresh silent install passed. Installed bridge SHA-256 `f4d32756a0ead9dbb3ad102971af211c8459cc296735148c0ab1b9b99b8bf716` matched the build resource. The installed bridge stored and retrieved a temporary acceptance key through the Windows credential vault; the test entry was deleted after verification.
- Refreshed Studio screenshot captured for this increment.

## 0.1.6 — Linux desktop accessibility

- Added a platform-neutral semantic desktop accessibility interface shared by workflow activities, the desktop inspector and adapter status.
- Implemented Linux AT-SPI discovery and interaction using the system `python3-pyatspi` binding and the active accessibility D-Bus bus. Linux Entry, Action and Text interfaces now map to the existing editable click, set-text, read-text and wait activities.
- The inspector exposes only actions supported by each control, reads accessible labels, and excludes password controls by AT-SPI PasswordText role or explicit toolkit password metadata.
- Added Windows regression checks and a reproducible GTK3 acceptance fixture. On Ubuntu 22.04/WSL with Xvfb and AT-SPI, the installed system Python inspected the fixture and a workflow executed through the real JSON-RPC bridge: wait, fill, click and read all succeeded. Run IDs: `cc30318d-6e73-4092-9b46-a604e6927ad9`, `5eba2c3b-8bac-4a46-aebf-ff1b40693eb2`, and selector-bound regression `284e0eb6-a4a3-4508-8fc7-484d92c7309a`; latest result `Saved Northshire Council`.
- Refreshed the README screenshot and generated `docs/SBOM-0.1.6.cdx.json`.

The Linux path was verified with one GTK3 fixture and Ubuntu's system Python. Other toolkits and distributions remain unverified. Linux users need distribution-installed `python3-pyatspi`, AT-SPI D-Bus services, and a Python interpreter that can import the system bindings. The Windows installer remains unsigned and development-only.

### Verification

- Python suite: 100 passed; browser-preview suite: 22 passed; frontend production build and Rust check: passed.
- Ubuntu AT-SPI live workflow through `openrpa.bridge`: passed three times; four activities succeeded each run; password field omitted.
- Windows x64 installer: 59.89 MiB; SHA-256 `95c6f70894ee9e5abca021efc8a44c1b066b5793cdb979974e41b5bd23c1b8c2`. Fresh silent install passed. Installed bridge SHA-256 `003ad1467cbbde26fcbdf0ef8a25811d2b80b42ea294cfcc7af3a03b0d586c6c` matched its build resource.
- Installed Windows UIA workflow run `fd1cb76e-3378-4b60-90a4-1c86d56624b6`: four activities succeeded and read back `Saved Grace Hopper`.

## 0.1.5 — Windows UI Automation

- Added an optional Windows UI Automation adapter using pywinauto, alongside the existing coordinate-based desktop fallback.
- Added a permission-gated desktop inspector for visible windows and named interactive controls. The inspector returns identity metadata only and excludes password controls and values.
- Added editable UIA click, set-text, read-text and wait activities. Selectors use exact window title plus optional process ID and accessible name and/or Automation ID; ambiguous selectors fail closed.
- Added per-activity UIA schema checks and bounded polling with cancellation checks between UIA calls. The desktop actions still require explicit desktop permission.
- Ran a real Windows WinForms fixture through the engine: wait for a field, enter “Ada Lovelace,” click Save, and verify the status becomes “Saved Ada Lovelace.”
- Refreshed the public README screenshot and generated a CycloneDX dependency inventory at `docs/SBOM-0.1.5.cdx.json`.
- Built and silently installed the Windows x64 NSIS installer into an isolated workspace directory. Installer SHA-256: `4e46a7a6b51284f33235d74eccdec51e446ce7cf734ca03f99dadd14fb634121` (59.83 MiB); installed bridge SHA-256: `65927b75a189b7d3d4a6d7a2a60e6fa14ebc02ac1d1609a41497525a441cb9ab`.
- The installed frozen bridge reported UI Automation available and executed the WinForms UIA workflow successfully with all four activities succeeded. Persisted run ID: `330270e3-70a3-476e-be58-013955b8a3f3`; the workflow read back `Saved Ada Lovelace`.

Linux AT-SPI automation remains unimplemented. UIA may not expose every application control, COM calls can block inside a single operation, and compatibility beyond the controlled WinForms fixture is not yet established. The installer remains an unsigned development build.

### Verification

- Python suite: 92 passed; browser-preview suite: 22 passed; Vite production build: passed.
- Windows UIA live fixture: wait, set-text, click and read-text all succeeded with the expected value.
- Windows x64 installer build and silent install: passed; installed bridge UIA execution: passed.
- Clean npm install in an isolated workspace copy: passed; 22 browser-preview tests and production Vite build passed from that clean install. The existing active preview processes were left running.

## 0.1.4 — AI-authored workflow structures

- AI drafting can now target a sequence, flowchart, or state machine through the same provider interface.
- Added model-specific structured output schemas. Flowchart nodes are discriminated by node kind, terminal nodes cannot contain actions, state finality is explicit, and invalid graphs remain review-only.
- Clarified prompts for top-level activity settings, unique node/activity IDs, reachable control flow, and concise user-facing explanations.
- Added provider schema and bridge validation tests for each workflow model.
- Captured an updated Studio screenshot for the public README.
- Live Ollama smoke: `qwen35-4b:latest` produced valid drafts for all three models; each was validated and run through the Python engine successfully. Qwen 3.5 9B exceeded the 180-second request timeout on graph drafts, showing that local model latency varies substantially.
- Built and silently smoke-installed the Windows x64 NSIS installer into an isolated directory. Installer SHA-256: `7aa27dc3f5708261aaa521b05b21f18535a293b33e0795be011fa1ce9454300e`.
- The installed bundled bridge generated and executed all three workflow models through Ollama. Run IDs: sequence `7b61b6f6-5bdd-4678-9711-0f5d2affcd82`; flowchart `bd04e9aa-5875-44bd-92ca-eb3c20afcd06`; state machine `9edc8e45-ea90-49dc-a28f-61c07630a601`. The installed bridge binary SHA-256 matched the build resource: `2262c89ea2a2bfbfdcec78ec8b44e0894e5fa0cbf83a7b07b8346d2ca4501997`.

The AI output is still a draft: users must inspect activities, selectors, expressions, and permissions before running it. The model is not a reliable substitute for requirements review.

### Verification

- Python suite: 82 passed.
- Browser-preview suite: 22 passed; production frontend build succeeded.
- `cargo check --locked --manifest-path src-tauri/Cargo.toml`: passed.
- Native Ollama draft → local workflow validator → real engine execution: sequence, flowchart, and state machine all returned `succeeded`; each emitted the expected `hello` log.

## 0.1.3 — State-machine workflows

- Added an editable state-machine workflow model alongside sequences and flowcharts.
- Added named states, per-state ordered activities, initial/final state controls, ordered Boolean guards, an optional fallback route, and transition editing.
- Added state-level debug breakpoints, execution status, bounded state visits, browser-preview execution, project invocation, and schema validation.
- Documented the state-machine workflow format with a complete JSON example.
- Refreshed the Studio screenshot to show a state-machine workflow and a successful preview run.
- Built and smoke-installed the Windows x64 NSIS installer. SHA-256: `820580c0715bcf0da62ec0d7f6711c298c4ed7a10e1054eb9f27f66d77902f03`.

This remains an unsigned development release. State-machine workflows do not provide automatic resume after interruption; operators must decide whether rerunning side-effecting activities is safe.

### Verification

- Python engine suite: 73 passed.
- Browser-preview suite: 22 passed; production frontend build succeeded.
- `cargo check --locked --manifest-path src-tauri/Cargo.toml`: passed.
- Installed Windows bridge smoke run: succeeded, selected the guarded approval path, returned `result=approved`, and recorded run ID `5f76395e-de6c-46ba-bc43-947266821a8e`.
- Installer was installed into a fresh isolated directory. The installed `openrpa-bridge.exe` SHA-256 matched the build resource byte for byte.
## 0.1.9 — OpenAI Responses API

- Add an explicitly selectable OpenAI Responses API provider alongside the existing OpenAI Chat Completions adapter.
- Use `/v1/responses` with schema-constrained workflow drafts, `store: false`, and refusal/incomplete response handling.
- Keep other compatible providers on Chat Completions.
- Refresh the README application screenshot.
- Windows installer SHA-256: `5825bb260ddaf5c220a556a0d1d2a724dda09df53d24e6f18ebd40f99660f792`.
- Verification: 119 Python tests, 22 frontend tests, Vite production build, Rust check, and isolated NSIS install passed. The installed bridge exposed and round-tripped the Responses profile across processes. Installed bridge SHA-256: `d67c9efa97fbc7f1035beaf1ce8c13fb129e2205594aa80474050c500b2916ea`.
