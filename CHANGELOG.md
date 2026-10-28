## 0.1.130

- Added compact MCP search/execute discovery and portable sequential batches to Windows, macOS, Linux and frozen bridges, with native permission and validation checks preserved.
- Added optional sandboxed JavaScript for Linux source installations, bounded output/calls, partial-completion traces and full native compatibility mode.
- Added cross-platform contract CI and packaged-runtime compact MCP acceptance; release automation now builds Windows x64, Linux x64, macOS Apple Silicon and macOS Intel.
- Aligned desktop, engine, MCP and Rust package versions at 0.1.130. Reconnect MCP clients after upgrading.

## 0.1.129

- Fixed window clipping in the Studio workspace. The activity library and properties panel now collapse to reachable expand rails in compact windows; side-panel widths adapt to the available width.
- The header toolbar and lower output tabs remain accessible when their controls exceed the visible width. Short windows allocate more height to the designer and constrain the resizable output panel to the available space.
- Removed the page-level minimum dimensions that forced the outer header, side panels, and lower panel outside smaller desktop windows.
- Lowered the native desktop window minimum to 700×480 so the responsive compact layout is available on smaller displays.
- Verification: Python 570 passed; frontend 213 passed; TypeScript and Vite production build passed; frozen MCP acceptance passed; Windows x64 NSIS installer built (69.82 MiB). SHA-256: `ee4aecb503cdcf105b5b5d2d7bff9b29f47b0cb6d47f418c89b12e9901cc9f6f`. Linux and macOS packages are built by the tagged GitHub Actions release workflow.

## 0.1.128

- Added recurring cron schedule management to Workflow Manager and matching Open RPA MCP tools for create/list/pause/resume/delete.
- Added a bounded five-field cron parser with IANA timezone support, DST-aware matching, skipped missed occurrences, and a durable per-project SQLite schedule table migrated from queue schema v1.
- Schedules pin their workflow and invoked dependencies; changed workflows or permissions pause a schedule before it runs. Scheduled runs inherit only MCP startup grants, use one worker, and do not automatically retry.
- Studio schedule management opens the queue with recovery disabled, so it cannot mark a live MCP run interrupted. Schedule inputs are not returned by monitoring tools.
- Added `tzdata` as a locked dependency and bundled its timezone database into the Windows MCP bridge.
- Verification: `uv run --locked pytest -q` (567 passed), `npm test -- --run` (212 passed), `npm run build`, frozen MCP acceptance, and Windows x64 NSIS installer build passed.
- Installer: `Open-RPA-Studio-Setup-0.1.128-x64.exe` (70.00 MiB), SHA-256 `89f98ca9bb57c5d816e98f2f05870b4a46793b840d0136f67023e428cf5cd72d`.

## 0.1.127

- Added a dedicated Workflow Manager to browse, search, open, duplicate with Save As, rename, delete, and create sequential chains from reusable workflows.
- Workflow renames update `invoke_workflow` references. Deletion protects Main and invoked workflows. Save As preserves the original workflow; chain creation validates the resulting project and exposes required child inputs as chain arguments.
- Closing a workflow with unsaved edits now prompts to save the project; cancelling keeps the tab open.
- Added Codex MCP quick-start documentation covering the installed bridge executable, active Studio project binding, `config.toml`, permission flags, version mismatches, and troubleshooting.
- Verification: TypeScript/Vite build passed; 212 frontend tests and 552 Python tests passed; frozen MCP acceptance passed; Windows x64 NSIS installer built (69.76 MiB). Installer SHA-256: `81ae1212fc715e649d0154c6de580af5cf9ee2293d0c8b1059b65152e83b0d55`.

## 0.1.126

- Replaced text-heavy API connection, credentials, and run permission controls with compact monochrome toolbar icons. Permission switches retain accessible labels, tooltips, and exposed on/off states.
- Verification: 210 frontend tests passed; TypeScript and Vite production build passed. Windows x64 NSIS installer build passed; frozen MCP acceptance passed. Installer SHA-256: `e19e0583d2519109a4a431448d0317fdc8407654fc47fd868dc0745d13ab4696`.
## 0.1.125
- Added opt-in Windows desktop typed-text recording for uniquely resolved, focused, non-password Edit/Document controls. Captured text is grouped into editable target-window activation and `desktop_type` activities; Enter and other allowlisted navigation keys remain separate activities. Typed capture is off by default, scoped to the selected window, bounded, reviewed before insertion and unavailable on Linux in this release.
- Added guarded MCP workflow deletion. It requires both edit and destructive startup grants, current project and workflow hashes, protects Main and invoked workflows, removes the manifest entry, retains the unreferenced workflow file for recovery and records an audit event.
- Added a concise inline disclosure and explicit text-capture opt-in in the desktop inspector.
- Verification: full Python suite 552 passed; frontend suite 210 passed; TypeScript/Vite build passed; frozen MCP acceptance passed; Windows x64 NSIS installer built. GitHub CI remains pending after push. Installer SHA-256: `4b7c045b6c936b7ef081d4b8f47f8cb5239706ef88f8d5cf50693acf46c8bca4`.

## 0.1.124
- Added a named Credentials manager in Studio for storing, replacing, checking and deleting secrets through the approved OS credential backend. Its local index stores only labels and service/username references; secrets stay out of projects and MCP output.
- Added permission-gated MCP credential reference discovery. `openrpa_list_credentials` is advertised only when the MCP server starts with `--allow-credentials` and never returns secret values.
- Added explicit per-workflow run trust. Users can remember the grants for a specific workflow and its dependencies, then opt into automatic runs without the review modal. Any workflow content or permission-plan change invalidates the trust; the default remains review each run.
- Documented how desktop trust and MCP startup grants differ. MCP autonomy remains directly configurable using its startup grant flags.
- Verification: 210 frontend tests passed; focused credential/MCP tests passed; TypeScript/Vite production build passed; initial installer build completed before the final 0.1.125 changes.

## 0.1.123
- Fixed live run feedback across Sequence, Flowchart and State Machine designers. Run state now exists before activity events arrive, the canvas follows the executing step, active and failed steps are marked in place, and completed runs focus End/the final state or the failed activity instead of leaving Start selected. State-machine initial styling is demoted after execution.
- Flowchart action nodes now emit and retain start/completion/failure and selected-transition data in both the native Python engine and browser preview, so executed connectors remain visible after the run.
- Fixed the AI Activity Monitor spinner selector. It had applied the loader's circle size, border and rotation to every span in the waiting banner, causing the explanatory progress text to spin and overlap. Only the loader icon now rotates.
- Added an explicit pending connector after the last complete, validated activity while a streamed sequence is still being received. It is labelled as a wait state and never presented as a generated activity. Empty drafts now say clearly that no complete step has arrived yet.
- Failures now mark their inferred lifecycle stage (Prepare, Connect, Generate, Parse or Validate). A lower-panel Warnings & Errors list shows validation messages, activity IDs, provider failures and output-mode fallback warnings.
- The live status distinguishes provider connection, waiting for first output, receiving output and validated steps, separating a model wait from actual workflow-step construction.
- Verification: all 206 frontend tests passed; 86 focused engine and debugger tests passed in the project virtual environment; TypeScript and Vite production build passed; frozen MCP acceptance passed; Windows x64 NSIS installer built. The DeepSeek API was not live-tested because this session had no provider credential configured. Installer SHA-256: `8ad0d963f3fbef7b06671fcadf034eb6e395557cd43695d6a95dde4e1e5a96c1`.

## 0.1.122
- Clarified live AI drafting progress with provider, generation, parsing, validation and preview milestones derived from actual backend events. Complete activity definitions animate into a validated step preview as they arrive; partial JSON remains hidden. Providers without streaming explain that steps appear after the complete response.
- Added a bounded targeted AI repair action for invalid drafts. It sends only validation codes, activity IDs and a sanitized workflow definition, validates the proposed complete replacement, preserves the original until acceptance, and limits automatic repair to one attempt per draft. Runtime failure repair is labeled directly.
- Verification: targeted AI monitor and repair tests 8 passed; full frontend suite 203 passed; TypeScript and production Vite build passed; frozen MCP acceptance passed; Windows x64 NSIS installer built. GitHub CI pending. Installer SHA-256: `33c88a81db3d00274bd44a8445624dfe323fadb7690e997ab5a62e5ae7749195`.
## 0.1.121
- Fixed DeepSeek long-thinking responses failing at the previous 2 MB raw-stream transport ceiling. Streamed provider payloads are now bounded at 8 MB, including provider metadata, while generated workflow text remains capped at 2 MB. DeepSeek drafts request at most 65,536 output tokens; a still-oversized stream gets an actionable message recommending a non-reasoning model or a smaller draft.
- Verification: focused provider/cancellation suite 79 passed; full Python suite 540 passed in the project virtual environment; frontend suite 198 passed; production frontend build, frozen MCP acceptance, Windows x64 NSIS installer build, in-place install and installed-app launch passed. The normal global Python interpreter could not collect the full suite because it lacks the project's `defusedxml` dependency; the locked project environment passed. Remote DeepSeek API was not live-tested because no provider credential was configured. Installer SHA-256: `db2245fbbcbd02ecc2f2df1e928b514c4ef90097a3910b76facc1ea5405af17d`.
- GitHub Actions run [39713852337](https://github.com/stevenmcsorley/open-rpa-studio/actions/runs/39713852337) passed.

## 0.1.120
- Added DeepSeek as a first-class AI drafting provider with model discovery, OS-vault credentials, JSON-object output, streamed generation, final-frame token usage, cancellation, and native workflow validation. DeepSeek does not receive a JSON Schema parameter; the schema is included in the prompt and Studio's validator remains authoritative.
- Preserved normalized usage data from streamed responses instead of passing it through a second parser that discarded it.
- Added a live AI activity monitor with real backend request/stream/parse/validation events, measured elapsed and first-output times, received character counts, capability/output-mode details, validation warnings, and an uncommitted sequence preview of individually validated activities. Added request-scoped cancellation handling and separated AI model/profile/credential/draft busy states.
- Added conservative OpenRouter capability discovery and route filtering, Gemini model metadata and streaming support with a bounded structured-output fallback, a fragmented SSE parser, and cancellable bounded streaming transport.
- Verification: focused provider/cancellation/draft suite 86 passed; full Python suite 537 passed; frontend suite 198 passed; production frontend build, frozen MCP acceptance, Windows x64 NSIS installer, in-place upgrade over 0.1.118, and installed-app launch passed. GitHub Actions run [39710626090](https://github.com/stevenmcsorley/open-rpa-studio/actions/runs/39710626090) passed. Remote DeepSeek API was not live-tested because this run had no configured provider credential. Installer SHA-256: `3f6c75c9a26840851596019474e25f7b2ac99ff155d7ef5d80c66a22e162e59e`.

## 0.1.119
- Browser Select Multiple now supports custom accessible ARIA listboxes in addition to native HTML multiple-select controls. Custom listboxes must expose `role=listbox`, `aria-multiselectable=true`, and unique accessible option names. The engine replaces the selected set, verifies it, limits inspection to 500 options, checks cancellation during custom selection, and returns selected names without logging them. The live browser inspector detects and configures the same control type.
- Verification: focused browser inspection suite 57 passed; full Python suite 525 passed; frontend suite 198 passed; production frontend build, frozen MCP acceptance, and Windows x64 NSIS installer build passed. Installer: `release/Open-RPA-Studio-Setup-0.1.119-x64.exe` (SHA-256 `30e15c73a9800e9713f58d2ce984081d9e27d80e35e3671321d088e3172f6616`). CI verification pending.

## 0.1.118
- OpenAPI import now substitutes valid server-variable defaults using the operation, path-item, then document precedence. Missing defaults, invalid enum choices, and resolved URLs incompatible with saved API connections are warned and left unset so authors can configure the base URL manually.
- Verification: frontend suite 198 passed; production Vite build, frozen MCP acceptance, and Windows x64 NSIS installer build passed locally. Installer: `release/Open-RPA-Studio-Setup-0.1.118-x64.exe` (73,058,428 bytes; SHA-256 `c4e4051b3b08ca02e4fd58d4b603f6b1eebcd977d88138832e43d94375cd23aa`).

## 0.1.117
- API response discovery now offers value-free, heuristic pagination hints for conventional cursor and next-link fields. Authors can prefill bounded pagination settings, retain relevant page/item/byte limits, reuse a matching cursor query parameter, and edit the resulting configuration before execution.
- Verification: Python suite 523 passed; frontend suite 194 passed; production Vite build, frozen MCP acceptance, and Windows x64 NSIS installer build passed. Installer: `release/Open-RPA-Studio-Setup-0.1.117-x64.exe` (73,052,275 bytes; SHA-256 `522392dff3052feb623194b1f57422348bb17efbd9563e920ac99c7c8830e9a4`).

## 0.1.116
- Added live API response shape discovery to the API Request editor. A GET request can inspect a bounded, value-free sample from a saved API connection and suggest editable response mappings; public egress, request size, traversal, and sensitive-field checks apply.
- Verification: Python suite 521 passed; frontend suite 192 passed; production Vite build, frozen MCP acceptance, and Windows host check passed in CI. Windows x64 NSIS installer built locally (73,047,688 bytes; SHA-256 `cc2e3f9f9612fcc73f610111d62c58f5799c505886e249baa9cb922f9312d554`).

## 0.1.115
- Added `scroll_into_view` to the direct live desktop MCP action so connected agents can reveal uniquely selected off-screen controls without coordinate automation. The frozen bridge acceptance now checks that MCP operation.
- Verification: live MCP desktop action, Windows UIA and Linux AT-SPI targeted suites passed (100 tests total); frontend production build passed. Full Python suite 507 passed; frontend suite 179 passed; production build, frozen MCP acceptance and Windows x64 NSIS installer build passed. Installer: `release/Open-RPA-Studio-Setup-0.1.115-x64.exe` (73,023,070 bytes; SHA-256 `3038cf949b84b98d1bb66a8b65751546bcf3cc8f8ba06d9d195a7d6cdfddc4e2`).

## 0.1.114
- Added native Scroll Control Into View for uniquely identified off-screen controls through Windows UIA ScrollItem and Linux AT-SPI Component patterns. Desktop inspection exposes off-screen Windows UIA controls when they advertise the scroll pattern, and marks visibility in the inspector. No coordinate fallback is used.
- Verification: full Python suite 507 passed; frontend suite 179 passed; production Vite build and frozen MCP acceptance passed. Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.114-x64.exe` (73,023,543 bytes; SHA-256 `b49ea9027b66883de4b08e14b7fca1f8f6c83251e4f5f55d1396bb275a4da3ca`).

## 0.1.112
- Replaced platform-default scrollbars with slim graphite tracks, rounded green-gray thumbs, and a restrained green hover/active treatment across the Studio UI. Firefox and Chromium/WebView use matching dimensions and palette.
- Verification: frontend suite 179 passed; production Vite build and frozen MCP acceptance passed during installer packaging. The scrollbar treatment was visually checked in the browser preview. Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.112-x64.exe` (72,987,802 bytes; SHA-256 `c364b4a87f638c95607de8f3655693967693d081b140050922b1480826877eff`).

## 0.1.111
- AI workflow drafting now displays normalized token counts reported by Ollama, OpenAI Chat Completions/Responses, Anthropic, Gemini, and compatible OpenAI endpoints. Counts are bounded, model-supplied usage metadata is discarded, and monetary costs are not estimated. Reported counts are recorded in the local audit history without prompt or response content.
- Verification: Python suite 497 passed; frontend suite 179 passed; production Vite build and frozen MCP acceptance passed. Real local Ollama acceptance (`qwen35-4b:latest`) produced, validated, and executed sequence, flowchart, and state-machine drafts; all three returned reported input/output/total token counts (9.446 s, 6.188 s, and 5.271 s). Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.111-x64.exe` (72,983,599 bytes; SHA-256 `82187cb902456f5196252d0b0a13b298e974d7d3e78a021df9b257f9d5f1edca`).

## 0.1.110
- AI connection profile updates now reject changing the provider, endpoint, or custom auth header while retaining the same OS-vault reference. A new profile or different vault reference is required, preventing accidental credential reuse against a changed host.
- Verification: AI connection suite 18 passed; full Python suite 490 passed. The Windows x64 installer build and frozen MCP acceptance passed both during packaging and against the installed 0.1.110 bridge. The installed Studio opened responsively. Installer: `release/Open-RPA-Studio-Setup-0.1.110-x64.exe` (72,980,787 bytes; SHA-256 `10489d4a72bd3cf03a40444cfbf8f381012f1f738332d483ae0a311f60b849a5`).

## 0.1.109
- AI draft review now shows the same execution-impact plan used by Studio's run review: configured file/API/browser/desktop targets, risk labels, and network/desktop/destructive requirements before insertion. The separate run review remains the permission gate.
- Verification: frontend suite 177 passed; production web build passed; frozen MCP acceptance passed during packaging and against the installed bridge. Windows x64 installer: 72,977,793 bytes, SHA-256 `ddcc1b7c33be8ccf49678049cc04c276c1280242240c370a2b871aecbb68d3c7`; installed version 0.1.109 launched responsively.

## 0.1.108
- Accepting an AI draft now opens it as a separately named workflow in a new tab, preserving the active workflow. Replacement remains available as a separate confirmation-backed action; the inserted draft supports normal undo and project save.
- Verification: frontend suite 175 passed; production web build passed; frozen MCP acceptance passed against the installed bridge. Windows x64 installer: 72,984,411 bytes, SHA-256 `5b820372ea57b59c50858f698783587347c57dc948d1f26625cab4ec036b4386`; installed version 0.1.108 launched responsively.

## 0.1.107
- AI workflow drafting now includes the canonical native activity titles, categories, descriptions, and property defaults for only the activity types permitted in the draft. Catalog data is allowlisted and excludes project contents and secret-bearing fields; normal engine validation still gates insertion and execution.
- Verification: provider and bridge AI-draft suites 65 passed; full Python suite 486 passed; production Windows build and frozen MCP acceptance passed. Real Ollama acceptance with `qwen35-4b:latest` drafted, validated, and executed one-log workflows for sequence, flowchart, and state machine (9.475s, 5.792s, and 4.930s); one flowchart node/activity ID collision was repaired and reported. Installer: 72,981,767 bytes, SHA-256 `818ffcd84f074a90c72e772e058494bf812c5f9f7a92579397f1b60cd9552180`.

## 0.1.106
- API Request retries now honor a valid server `Retry-After` delta-seconds or HTTP-date response, bounded to 30 seconds. Missing or invalid values retain exponential backoff; transport errors retain existing backoff behavior. Retry audit events record only the selected bounded delay and its source, never the raw header.
- Verification: API connection suite 52 passed; full Python suite 486 passed; frontend suite 173 passed; production web build passed. Frozen MCP acceptance passed during packaging and against the installed bridge. Installer 72,977,976 bytes, SHA-256 `043a8f9b48921c8796e42c30783b2aab66bf8d7e43d1ef85e2d28b5f708077a4`; installed version 0.1.106 launched responsively.

## 0.1.105

- Extended Set UI Range Value to Linux AT-SPI Slider and Spin Button controls through the native Value interface. The adapter checks bounds and verifies the resulting value; read-only state is rejected when exposed by AT-SPI. The Windows UIA Slider/Spinner behavior remains supported.
- Verification: Python suite 481 passed, including adapter and engine workflow execution; frontend suite 173 passed. Production Windows build passed; frozen MCP acceptance passed against both packaged and installed bridge. Version 0.1.105 installed and opened responsively. Linux AT-SPI behavior was verified with a controlled accessibility fixture, not a live Linux desktop session.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.105-x64.exe` (72,978,150 bytes; SHA-256 `e6898cdb060778083ecb6f60839f308520c328d3777b83991dbb1e4cfb4b3aea`).

## 0.1.104

- Added the Windows UI Automation RangeValue activity for safely setting Slider and Spinner controls from workflows and live MCP actions. Native bounds and read-only state are enforced, and the resulting value is verified. Linux AT-SPI range setting remains unsupported.
- Verification: Python suite 478 passed; frontend suite 173 passed; production Windows build passed. Frozen MCP acceptance passed against both the packaged and installed 0.1.104 bridge. The app was installed and opened responsively. Range setting was tested against controlled UIA adapters; compatibility with third-party target applications remains application-dependent.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.104-x64.exe` (72,974,063 bytes; SHA-256 `b73a210da463720cfd770deea9106e4493a96af55b2e2805c54590527e5baa95`).

## 0.1.103

- OpenAPI operation import can now prefill a reusable API connection with an absolute HTTPS server and one unambiguous supported security scheme. Secrets remain in the OS vault; ambiguous, combined, unsupported, or unsafe server metadata is not guessed. Saving the connection automatically selects it for the imported API Request activity.
- Verification: Python suite 475 passed; frontend suite 173 passed; production build passed. Frozen MCP acceptance passed during packaging and against the installed 0.1.103 bridge. Silent upgrade exited 0 and the installed Studio opened responsive.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.103-x64.exe` (72,970,079 bytes; SHA-256 `3fe67f727ac470dfdac9c38dae337c3b3cee41fa2018b0b1864957fc43750abd`).

## 0.1.102

- Added selectable Bearer or custom API-key header authentication for generic OpenAI-compatible HTTPS gateways. Header configuration is persisted with the named connection profile, while key material continues to come only from the OS credential vault. Provider-specific authentication formats remain unchanged, and unsafe or transport-sensitive header names are rejected.
- Fixed indentation in the OpenAI Responses schema-fallback path while wiring authentication options through the provider adapter.
- Verification: Python suite 475 passed; frontend suite 170 passed; production build passed. Frozen MCP acceptance passed both before packaging and against the installed 0.1.102 bridge. Silent upgrade exited 0 and the installed Studio opened responsive.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.102-x64.exe` (72,966,270 bytes; SHA-256 `35d499c34b5d041d7cafc9d9ce7e5c2f84032fa48903b5b1f27f0cd48a832cb5`).

## 0.1.101

- Improved value-free browser JSON schema discovery for heterogeneous API responses. Array samples now identify fields present in all sampled items, expose sample-only optional fields and preserve mixed scalar types rather than discarding their alternatives. The inspector still returns no response values and retains strict size, depth, property and node bounds. Responses without Content-Length remain rejected before Playwright reads their bodies, because Playwright buffers response bodies before exposing them.
- Verification: Python suite 464 passed, including live Chromium inspection and heterogeneous-array coverage; frontend suite 170 passed; production Vite build passed. Frozen MCP acceptance passed during packaging and against the installed 0.1.101 bridge. Silent upgrade exited 0 and the installed Studio window opened responsive.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.101-x64.exe` (72,962,398 bytes; SHA-256 `2fa074678848d19229429b192f04f37d3d7d882fa77f8d95c54eb2d406ae3779`).

## 0.1.100

- Browser API response inspection now has a value-free schema discovery mode alongside explicit field mapping. It exposes discovered object keys, JSON types and object-array JSON Pointers, bounded by response bytes, depth, per-object property count, array samples and total inspected nodes. The schema can be used to configure a follow-up mapping without putting sample API values into workflow history.
- Verification: Python suite 463 passed, including live Chromium response inspection and schema caps; frontend suite 170 passed; production Vite build passed. Frozen MCP acceptance passed during packaging and against the installed 0.1.100 bridge. Silent upgrade exited 0 and the installed Studio window opened responsive.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.100-x64.exe` (72,963,556 bytes; SHA-256 `734eace0e78cf4f1c4ad28e9e8e1b03086be30ccf742615d791f1f377d9718d3`).

## 0.1.99

- Browser Wait Response can optionally map selected scalar fields from one bounded JSON response array into workflow data. Raw response bodies stay out of logs and audit events; mapping is opt-in, size bounded, and requires a recent successful uncompressed JSON response with a declared content length. The properties editor exposes field pointers and limits.
- Verification: Python suite 461 passed; frontend suite 169 passed; production Vite build passed. Frozen MCP acceptance passed during packaging and against the installed 0.1.99 bridge, covering accepted bounded mappings and rejected malformed pointers/result collisions. Silent upgrade exited 0 and the installed Studio window opened responsive.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.99-x64.exe` (72,955,135 bytes; SHA-256 `ab431a6f15925cd63a2c37285e79381f69c1863548c3786a60a957f9c418685c`).

## 0.1.98

- Browser repeated-item extraction can now append across pagination or gradual scrolling while deduplicating overlaps by up to ten mapped fields, such as a product URL or SKU. Keys use exact values, the first matching record is kept, blank composite keys are retained separately, and aggregate limits apply to the final deduplicated result. Studio includes a field-based deduplication editor and validation rejects unmapped keys.
- Verification: Python suite 459 passed; frontend suite 168 passed; production Vite build passed. Local browser acceptance passed repeated-card extraction, overlapping-item deduplication, pagination, page scrolling and nested-feed scrolling on Chromium 156, Firefox 157 and WebKit 27.2. Frozen MCP acceptance passed during packaging and against the installed bridge; Studio 0.1.98 upgraded and launched with a responsive window.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.98-x64.exe` (72,945,043 bytes; SHA-256 `720d986f1551f136cc75f317fd54562a8f42a8dd2569253bfb221930ce97a240`).

## 0.1.97

- Added browser scrolling inside modern sites' nested feeds and result panels. **Scroll Page or Container** can target the whole page or one visible, uniquely matched CSS container; it reports container-local position and progress, uses pointer wheel input with a native-scroll fallback when a browser routes wheel events to the document, checks cancellation between steps, and keeps a bounded maximum-step limit. Added a focused properties editor and runtime/schema coverage.
- Verification: Python suite 457 passed; frontend suite 167 passed; production Vite build passed. Local browser acceptance passed repeated-card extraction, visible pagination and page scrolling on Chromium 156, Firefox 157 and WebKit 27.2; nested-feed scrolling reached the end on all three engines (Firefox used the native-scroll fallback). Frozen MCP acceptance passed during packaging and against the installed bridge. Silent upgrade installed 0.1.97; Studio opened with a responsive application window.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.97-x64.exe` (72,945,377 bytes; SHA-256 `dcdfc7d342c6fb9d3881b4145574fa51fcf135686cba325af9fd59008740fb0d`).

## 0.1.96

- Replaced raw JSON fields for API request query parameters, request headers, and reusable connection headers with a key/value editor. Header names are validated as HTTP tokens; transport and credential-like headers are blocked from workflow files and OpenAPI operation import warns and skips them. API credentials continue to come from the saved connection's OS vault.
- Verification: Python suite 455 passed; frontend suite 165 passed; TypeScript/Vite production build passed. Frozen MCP acceptance passed during packaging and against the installed bridge, including permission-gated browser/desktop tools, bounded selector/process inputs, loopback navigation blocking, selector recovery constraints, and staged workflow handling. Silent upgrade installed 0.1.96; the installed application launched with a responsive `Open RPA Studio` window.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.96-x64.exe` (72,936,955 bytes; SHA-256 `db52f53be6ebd75f0cef68104eaa1d088e16bc6d3f34f24a187e09d51a910aae`).

## 0.1.95

- Browser repeated-item extraction can now append records across paginated pages while enforcing combined record and text limits. A page failure or aggregate-limit breach removes the partial result, preventing downstream steps from treating an incomplete scrape as complete. Studio exposes the append switch and aggregate limits in the extraction editor.
- Verification: Python suite 450 passed, including live Chromium multi-page accumulation, aggregate-bound enforcement and partial-result cleanup; frontend suite 162 passed; production build passed; frozen MCP acceptance passed during packaging and against the installed bridge, including checks that the installed catalog exposes append defaults and validation enforces aggregate limits. Silent upgrade registered as 0.1.95 and the installed Studio window launched and remained responsive.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.95-x64.exe` (SHA-256 `2a7ed72e3db2a4b5d3ccb5d4fff93a2afa35cf21330dcba6bf41c63f4ef6242a`).

## 0.1.94

- Replaced raw JSON editing for browser repeated-item extraction with a visual field mapper. Users can add/remove columns, set each relative CSS selector, choose visible text or an HTML attribute, mark required values, and extract a whitespace-token index from class attributes such as star ratings. The editor exposes the engine's existing field and record bounds and keeps the workflow's normal editable schema.
- Verification: frontend suite 161 passed; production build passed; frozen MCP acceptance passed both during packaging and against the installed bridge; silent upgrade registered as 0.1.94 and the installed Studio window launched and remained responsive. Python engine code was unchanged from 0.1.93.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.94-x64.exe` (72,930,818 bytes; SHA-256 `7e041c4e644676777f9f72c59dda7a1b6491409773139531fea034c5c22fd454`).

## 0.1.93

- Claude model discovery now follows Anthropic's opaque `after_id` pagination cursor, deduplicates model IDs across pages, and enforces a 5,000-model cap. It continues only against the validated configured endpoint and fails clearly on missing or repeated cursors rather than silently truncating the model list.
- Added multi-page, duplicate, malformed-cursor and safety-bound coverage. Verification: Python suite 448 passed; frontend suite 160 passed; production build passed; frozen MCP acceptance passed both in the build and after installation. Installed application started and reported a responsive `Open RPA Studio` window.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.93-x64.exe` (72,927,657 bytes; SHA-256 `9acc4a3fe79e3acb6875d69de712ddffbc88c87f4da2672582e777630ff19722`).

## 0.1.92

- Added optional named persistent browser profiles for Chromium, Firefox and WebKit. Profiles are isolated by project, stored in OS application data outside project exports, and require per-run desktop permission because they may retain signed-in state. The Studio editor explains how to use the isolated profile; audit events contain only a hashed profile identifier.
- Added schema and MCP permission-plan checks, fail-closed app-data path containment, browser session persistence acceptance across browser restarts, and a visible warning that session-only cookies or site policies can require signing in again.
- Verification: Python suite 445 passed; frontend suite 160 passed; production build passed. A real Chromium profile restart test preserved an expiring cookie across two independently launched Playwright contexts; a profile without desktop permission failed before runtime startup. Local browser extraction/pagination/gradual-scroll acceptance passed on Chromium 156, Firefox 157 and WebKit 27.2. Live Windows UIA/MCP acceptance passed on a disposable WinForms app (14 controls; fill/invoke/readback; grid and multi-select; state wait; app launch/close; password and ambiguous selectors blocked; audit value-free). Frozen MCP acceptance passed in the build and installed bridge; silent install and visible Studio launch passed.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.92-x64.exe` (72,928,129 bytes; SHA-256 `0317bb2abee0775ec5d0b29d36e808599a2f4a1c9d4a2603c10a810b4a3a2a23`).

## 0.1.91

- Replaced the Linux recorder's unsupported assumption about AT-SPI `pressed` events with an X11/XWayland RECORD listener that observes primary-button presses and an allowlist of navigation keys. Clicks are resolved against the selected active window's AT-SPI tree and produce activities only for a unique selector; key events are emitted only for safe keys and a unique focused control. Printable keys, typed text, screenshots and clipboard values are never captured. Pure Wayland windows without an XWayland surface remain unsupported for recording.
- Added Linux-only `python-xlib` dependency, runtime capability reporting, selector hit testing, queue bounds, updated Studio keyboard-capture capability negotiation, and unit plus live GTK integration acceptance.
- Tightened Windows OCR clicking to restore and verify the exact target HWND is foreground before capture and again before acting. A live local test recognized the synthetic target at 96.6% and exposed that the background automation runner could not activate its window; the activity now fails with an actionable error and does not send a click in this case.
- Added a repeatable local browser-engine acceptance workflow at `scripts/acceptance_browser_engines.py`. Chromium 156, Firefox 157 and WebKit 27.2 each passed real local-site card extraction, visible next-page navigation and gradual scrolling to the bottom with progress events (7, 10 and 6 scroll steps respectively). No external site or network was used.
- Corrected the Python engine's version constant to 0.1.91. Verification: live Ubuntu/WSLg GTK acceptance recorded one `desktop_ui_invoke` and one focused `desktop_ui_press` (Enter); fixture confirmed both actions and captured no typed text. Live Windows OCR acceptance confirmed the no-foreground case fails closed; successful foregrounded OCR clicking remains unverified in this runner. Full Python suite: 442 passed; frontend suite: 160 passed; production build passed. Frozen MCP acceptance passed during build and against the installed bridge; silent install and visible Studio launch passed. The bridge remains hidden with no visible console window. Rebuilt installer details follow after package verification.

## 0.1.90

- Continued desktop automation acceptance and strengthened selector-based Linux AT-SPI recording coverage. Live GTK testing confirmed the local control click but exposed that the recorder did not receive a semantic pressed event in this environment; Linux interaction recording remains unverified pending a reliable event source.
- Verification: 431 Python tests and 160 frontend tests passed; production frontend build, frozen MCP acceptance, Windows x64 installer build, silent install, installed bridge acceptance, and visible Studio launch passed. Linux GTK live-recording fixture clicked its control but produced no AT-SPI event, so live Linux recording remains unverified; OCR click accuracy against a real app remains unverified.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.90-x64.exe` (72,904,304 bytes; SHA-256 `46a9cb737423896a5559c82f3e9a30c74bbf303ba8ee7e3f69559d9d45f4e44b`).

## 0.1.89

- Added `desktop_ocr_click` for Windows applications whose visible text controls are not exposed through UI Automation. It scopes capture to one exact window, uses local Tesseract, and clicks only a unique exact OCR line above a configurable confidence threshold. Ambiguity, weak confidence, oversized/invalid window bounds, timeouts, or a changed target process fail closed; text and coordinates are not persisted or audited.
- Added Linux AT-SPI interaction recording for uniquely identified buttons, links, menu items, and stateful checkbox/radio controls within one selected process and window. It listens only for semantic accessibility events and does not capture typed text, global keys, coordinates, screenshots, or clipboard data.
- Added activity catalog and schema support, execution-plan labeling, documentation, and tests for confidence, ambiguity, bounds, permission gating, and successful unique-match dispatch.
- Verification: 429 Python tests, 160 frontend tests, production build, frozen bridge MCP acceptance (including valid and invalid OCR activity schemas), and Windows NSIS installer build passed. Live OCR clicks and Linux AT-SPI event recording still need acceptance against real visible applications; this command environment blocked launching a GUI fixture.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.89-x64.exe` (72,896,262 bytes; SHA-256 `c26220d08510ebb158ba7bda90079ea9fde4c6825f1e2bd439ae2b2562b41505`).

## 0.1.88

- Added opt-in conservative browser selector recovery for exact accessibility-role/name selectors. After explicit fallbacks, it checks a bounded set of visible, enabled controls with the same role; requires a strong unique name match; rejects ambiguous or missing matches; and leaves CSS, text, placeholder, and test-ID selectors untouched. Recovery is disabled by default and use is recorded without logging selector text or page content.
- Added visual editor controls, activity-catalog metadata, schema validation, documentation, and real Chromium recovery/ambiguity tests.
- Verification: 420 Python tests, 160 frontend tests, production build, frozen bridge acceptance (including recovery schema), Windows installer build and silent install, installed bridge acceptance, and Studio 0.1.88 launch passed. `git diff --check` reported no whitespace errors (only pre-existing CRLF conversion warnings).
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.88-x64.exe` (72,863,503 bytes; SHA-256 `10cddcd975e70952efff42ea509e339dbf4946de3143b24c91e4aa6171ededb1`).

## 0.1.87

- Studio and the live Browser UI Inspector now detect and offer installed Brave, Vivaldi, Opera and Opera GX alongside Chrome and Edge. Selecting one stores its detected executable path and launches it through Playwright's Chromium mode; custom Chromium-based executables remain supported. Firefox and WebKit remain separate Playwright engines.
- Added cross-platform browser discovery coverage and UI regression coverage for named installed-browser selection. Real local Chrome and Edge launch probes passed without navigating or using network.
- Verification: 417 Python tests, 159 frontend tests, production build, frozen MCP acceptance, Windows installer build and silent install, installed bridge acceptance, and Studio 0.1.87 launch passed. `git diff --check` reported no whitespace errors (only existing CRLF conversion warnings).
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.87-x64.exe` (72,861,408 bytes; SHA-256 `cac064548c21320265eb37062483f0213ba6f41831953e8369635e5fd4736eaf`).

## 0.1.86

- Added `openrpa_browser_screenshot`, a visible-browser MCP tool that returns a viewport JPEG as a native MCP image block for visual agent inspection. It is permission-gated, limited to 700,000 bytes, captures only the current viewport, strips URL query/fragment metadata, and writes no image data to audit history.
- Added real Chromium screenshot and MCP image serialization tests, bounded-payload failure coverage, and frozen-bridge tool/schema acceptance.
- Verification: 415 Python tests, 158 frontend tests, production build, live Windows UIA/MCP acceptance, frozen bridge acceptance, installer build/install, and installed Studio acceptance pending.

## 0.1.85

- Completed browser multi-selection end to end: visible inspector detects native HTML `<select multiple>` controls; workflows and live browser MCP can set up to 100 unique submitted values, verify the result, and keep those values out of logs and MCP responses. Studio includes an editable value-list editor and selection result variable. Custom ARIA listboxes are explicitly unsupported by this activity.
- Fixed the previously advertised but unimplemented live browser MCP `select_many` action; added frozen bridge schema and workflow validation.
- Verification: 414 Python tests, 158 frontend tests, production frontend build, real Chromium multi-select inspection/MCP/workflow tests, frozen MCP schema and workflow acceptance, NSIS build and silent install, installed bridge acceptance, and Studio 0.1.85 launch passed. `git diff --check` passed.

- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.85-x64.exe` (69.48 MiB; SHA-256 `1db14a07c0871c3f5fc46971749a2b439763bc183442bc03f8bf27009d9ecb5b`).

## 0.1.84

- Added `desktop_ui_select_many`, a native accessibility activity for replacing, adding, and removing exact named options in Windows UIA Lists and Linux AT-SPI List Boxes. Selection names are bounded, ambiguous or unsupported selections fail closed, the resulting names are returned to a workflow variable, and Studio exposes an editor and inspector action.
- Fixed the MCP desktop action allowlist and result handling for multi-selection. Added live acceptance for replace/add/remove using a real multi-select WinForms ListView, plus frozen MCP schema and workflow validation.
- Verification: 412 Python tests, 158 frontend tests, production frontend build, live Windows UIA/MCP acceptance (including exact multi-selection, result readback, audit redaction, and existing desktop actions), frozen-bridge acceptance, NSIS installer build and install, installed bridge acceptance, and Studio 0.1.84 launch passed. `git diff --check` passed.

## 0.1.76

- Added a native, bounded Playwright ARIA accessibility snapshot activity. It exposes roles, accessible names and states for AI and workflow selector planning, fails instead of truncating, and reports accurately that browser preview requires the desktop browser engine.
- Verification: 390 Python tests, 158 frontend tests, production build, real Chromium accessibility snapshot coverage and frozen MCP staging acceptance passed. Installed Open RPA Studio 0.1.76 and verified the app and bridge launch.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.76-x64.exe` (72,795,888 bytes; SHA-256 `3d41b89c5df30bccbf94586754c7851754a4be30666ffb9013a679cb56dc57db`).

## 0.1.75

- Added API DELETE to the native connector and OpenAPI importer. DELETE is presented as destructive, requires explicit per-run permission in Studio or `--allow-destructive` through MCP/CLI, is audited, and is excluded from automatic retry.
- Verification: 389 Python tests, 156 frontend tests, production build, frozen MCP acceptance and installed bridge/app launch passed. Focused regression coverage: 66 Python API/MCP tests and 31 frontend API/run-plan tests.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.75-x64.exe` (SHA-256 `612525c375a5a03cfc0cd4e285b2bccbc27a4c25c783a5a7d308ca157f4a356a`).

# Changelog

- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.84-x64.exe` (69.47 MiB; SHA-256 `78b42e9893ca1d3fbdb7a5ef8699b2e6ad066bd252bde1c8d1a9a5ebf6dd14fb`).

## 0.1.83

- Added selected/unselected state inspection and wait support for accessible ListItem and TreeItem controls. UIA state is read from the native selection pattern; AT-SPI reports selection when the platform exposes `STATE_SELECTED`.
- Verification: 406 Python tests, 158 frontend tests, production frontend build, live Windows UIA/MCP acceptance (ListBox selection and selected-state wait, grid read, text entry, app lifecycle and permission refusals), frozen MCP acceptance, NSIS installer build, silent install, installed bridge startup and Studio 0.1.83 launch passed. `git diff --check` passed.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.83-x64.exe` (69.46 MiB; SHA-256 `dace26445bda95ec51207bae6089deff5f993947cb05b29d63773a5b2b2660a9`).

## 0.1.82

- Completed Windows UIA `desktop_ui_select` support for selecting an exact named option from a List container. The inspector advertises the action only for supported list controls; execution rejects missing or ambiguous option names and verifies the native selection state.
- Verification: 404 Python tests, 158 frontend tests, production frontend build, live Windows UIA/MCP acceptance (including selecting “Queued” from a WinForms ListBox and confirming its selected state), frozen MCP acceptance, NSIS installer build, silent install, installed bridge startup, and Studio 0.1.82 launch passed. `git diff --check` passed.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.82-x64.exe` (69.45 MiB; SHA-256 `f76a18ead40f794533c28b5be45b048b7b13607a7230f05b1a6e7b7d098d2ebc`).

## 0.1.81

- Added bounded structured desktop grid reading through Windows UIA Grid and Linux AT-SPI Table. The activity returns records for workflow transformations plus row/column, truncation, redaction and output-size metadata; sensitive cell values are excluded from audit history. The desktop inspector and live MCP expose the same capability where the adapter reports a supported table pattern.
- Verification: 401 Python tests, 158 frontend tests, production frontend build, live Windows UIA/MCP acceptance (including two real WinForms grid rows), frozen MCP acceptance, NSIS installer build, silent install, installed bridge startup and Studio 0.1.81 launch passed. `git diff --check` passed.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.81-x64.exe` (69.45 MiB; SHA-256 `a0cbeba215812e61e576b86827655847c21681038111b59368428795caf22348`).

## 0.1.80

- Initial implementation of bounded structured desktop grid reading through Windows UIA Grid and Linux AT-SPI Table, completed and release-verified in 0.1.81.
- Verification: superseded by the completed 0.1.81 release acceptance below.

## 0.1.79

- Added selector-only desktop drag recording and clear “Drag Accessible Control” labels in Studio. Drag gestures become editable activities only when both endpoints resolve to distinct unique accessible controls; raw coordinates remain transient.
- Verification: 395 Python tests, 158 frontend tests, TypeScript/Vite production build, frozen MCP acceptance, Windows x64 installer build, silent installation, installed bridge startup and Studio v0.1.79 launch passed. Focused desktop recorder/UIA/MCP tests: 67 passed.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.79-x64.exe` (69.44 MiB; SHA-256 `f62f65850e5190b7099838f88c293dc71a1f94e69cc37ce7014068d09345ad42`).

## 0.1.78

- Extended the Windows desktop action recorder to recognize drag gestures and emit editable `desktop_ui_drag` activities only when both points resolve to distinct, uniquely identified UIA controls. Coordinates remain transient and are excluded from recorded workflows.
- Verification: 395 Python tests, 158 frontend tests, TypeScript/Vite production build, frozen MCP acceptance, Windows x64 installer build, silent installation, installed bridge startup and Studio v0.1.78 launch passed. Focused recorder/UIA/MCP regressions: 67 passed.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.78-x64.exe` (69.44 MiB; SHA-256 `fbfaca4dd559a7f5287bac350bcb5e10b743e95ef8c6d7db173d7c558724bb04`).

## 0.1.77

- Added selector-based accessible drag-and-drop for Windows desktop automation and the live MCP desktop action. Source and target must each resolve uniquely within the same exact window. Coordinates are derived internally, password and ambiguous controls fail closed, and pointer release is attempted after failures.
- Verification: 393 Python tests, 158 frontend tests, TypeScript/Vite production build, frozen MCP acceptance, Windows x64 installer build, silent installation, and installed Studio v0.1.77 launch passed. The new drag adapter has successful, ambiguous-target and failed-move/release regression coverage.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.77-x64.exe` (69.43 MiB; SHA-256 `beb894d8986124b11d3d24485df726e05b2e7bf2e1a0b7837e3a694cff7ff205`).

## 0.1.74
- Added a **Check browser** action to the Browser Inspector. It launches the selected Playwright engine/channel in a temporary headless session, closes it, and performs no page navigation or network request. Successful checks report the browser version; missing runtimes return installation guidance. Audit records include only engine, channel and success status, never a custom executable path.
- Verification: 387 Python tests, 154 frontend tests, production build, frozen MCP acceptance and installed bridge acceptance passed. Local Chromium, Chrome and Edge probes all launched successfully without network access. Installed Studio 0.1.74 and confirmed it launched. Codex MCP configuration points to the 0.1.74 bridge; restart Codex to reload it.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.74-x64.exe` (72,765,742 bytes; SHA-256 `0e03179a56256d7344709632bd56854bea564faa302c81296eee0a471bbe48fd`).

## 0.1.73
- Connected browser runtime detection to the Browser Inspector & Recorder. Before opening a page, users see whether the selected Playwright engine or Chrome/Edge channel was detected; custom executable paths remain launch-checked. Detection does not claim that a present binary is launch-compatible.
- Verification: 154 frontend tests and the TypeScript/Vite production build passed. Python browser adapter, inspector and MCP tests passed (63). Frozen and installed MCP acceptance passed; installed Studio 0.1.73 launched successfully. Codex MCP configuration points to the 0.1.73 bridge; restart Codex to load it.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.73-x64.exe` (72,759,122 bytes; SHA-256 `30e7529909a282244a07fd8e6bb34fbfd7c14d09a7a35f2eeff2c95fa3abd549`).

## 0.1.72
- Expanded browser runtime status to detect Playwright-managed Chromium, Firefox and WebKit executables plus commonly installed Chrome and Edge binaries. Browser Launch properties now report availability for the selected engine/channel, distinguish executable detection from verified launch compatibility, and explain when a runtime was not detected.
- Verification: 383 Python tests, 154 frontend tests, TypeScript/Vite production build, frozen bridge acceptance, and installed bridge acceptance passed. On this machine the probe detected Playwright Chromium, Google Chrome and Microsoft Edge; Firefox and WebKit were not installed. Installed Studio 0.1.72, confirmed it launched, and updated Codex MCP configuration to the installed 0.1.72 bridge; restart Codex to reload it.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.72-x64.exe` (72,761,230 bytes; SHA-256 `7edd51baf4b323197262ee5c0a5837da2d4bb6a07ab8387118c30071cab71a90`).

## 0.1.71
- Added a native Google Gemini API adapter with OS-vault API key handling, model discovery, schema-constrained JSON drafts, and explicit blocked/truncated/malformed response errors. The adapter uses Gemini's `generateContent` protocol and reduces workflow schemas to its supported subset before submission.
- Verification: 378 Python tests, 153 frontend tests, TypeScript/Vite production build, frozen bridge acceptance, and installed bridge acceptance passed. Installed Studio 0.1.71 and confirmed it launched. Codex MCP configuration points to the installed 0.1.71 bridge; restart Codex to load the new executable.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.71-x64.exe` (72,755,041 bytes; SHA-256 `4210afcaf3cf8962b6632ade63f88a7f09a58b9ae081bcffc0572e6ef1685208`).

## 0.1.70
- Fixed recorded browser events to accept all supported primary selector types (including CSS and label selectors), while continuing to reject malformed or unsupported fallback entries.
- Verification: 371 Python tests and 153 frontend tests passed; the production frontend build and frozen MCP acceptance passed. The 0.1.70 installer is installed, its bridge passed frozen MCP acceptance, Codex config points to that executable, and the app launched successfully.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.70-x64.exe` (72,753,049 bytes; SHA-256 `a3fe886e28363fa76ccdf783167d567bc4d030a1b2635ddd3586b59006bd335d`).

## 0.1.69
- Browser interactions recorded through the visible browser now include one unique, independently derived selector fallback when available (for example, a stable `data-testid` alongside an accessible role/name). The stored fallback omits typed values and plugs into the existing validated fail-closed selector recovery path.
- Verification: 370 Python tests and 153 frontend tests passed; the production frontend build and frozen MCP acceptance passed. A real Chromium test recorded an editable field interaction, changed the page's accessible label, and successfully replayed the generated activity via its recorded test ID. Installed Open RPA Studio 0.1.69, reran frozen MCP acceptance against the installed bridge, verified Codex's config points at it, and launched the app.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.69-x64.exe` (72,749,773 bytes; SHA-256 `c32714add43729db2c793ca46d3e790b60f13e015442dcf506e18dff90c8f171`).

## 0.1.68
- Extended the live desktop MCP tool with application launch, window discovery/waiting by title or process ID, and normal window close guarded by `confirmClose=true`. Launch accepts an explicit absolute executable path and bounded argument vector; it never invokes a shell. Each action remains gated by `--allow-run --allow-desktop` and audited without arguments or text values.
- Verification: MCP unit tests and a live controlled Windows acceptance cover launch → wait for its visible UIA window → interact with controls → normal close, plus password-field refusal and ambiguous-selector failure.
- Verification: 369 Python tests passed; live Windows acceptance launched a disposable app through MCP, waited for and identified its window, and closed it normally. The installed 0.1.68 bridge passed frozen MCP acceptance with the lifecycle tool schema. Codex MCP config now points to `openrpa-bridge-0.1.68.exe`; restart Codex to load it.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.68-x64.exe` (72,747,524 bytes; SHA-256 `7ffa0c4589dfc0486248e02d3f95aac284309fffc803ee0e8e9fac0b0c31b750`).

## 0.1.67
- Added permission-gated `openrpa_desktop_action` to the local MCP bridge for real-time accessibility-targeted reading, state checks, clicks, invokes, text entry, allowlisted key presses, selection, checkboxes, tree expansion, waits and visible-window activation/minimize/restore. Requires both `--allow-run` and `--allow-desktop`; it rejects ambiguous targets and bounds text/timeouts.
- Added a regression guard that prevents the MCP desktop action from filling password controls. The audit trail records action outcomes and a target hash without recording entered values or control labels.
- Verification: 369 Python tests, 153 frontend tests, TypeScript/Vite production build and frozen bridge checks passed. A live controlled WinForms acceptance verified project tool calls against accessible controls, fill/click/readback, state wait, ambiguous selector failure and password refusal.
- Verification: installed Open RPA Studio 0.1.67, confirmed the packaged bridge hash matches the built bridge, and reran frozen MCP acceptance against the installed executable. Codex MCP config now points to `openrpa-bridge-0.1.67.exe`; restart Codex to load it.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.67-x64.exe` (72,743,863 bytes; SHA-256 `b2b70525c650a9f348871629c4f0317ec307d1214132f719291baba77983ed21`).

## 0.1.66
- Added opt-in live browser tools to the local MCP server: open/navigate a visible browser, read a bounded rendered-text and accessible-control snapshot, perform unique selector-based actions, scroll up/down at a controlled pace, and record editable selector-based interactions.
- Live browser MCP tools appear only with `--allow-run --allow-network --allow-desktop`. The browser is MCP-owned and visible, applies public-address request checks, rejects ambiguous or hidden targets, blocks password/payment/file/hidden field fills, strips URL query/fragment data from results, warns that page text is untrusted, and records actions without typed values or selectors in the audit ledger.
- Verification: 368 Python tests and 153 frontend tests passed; TypeScript/Vite production build and frozen MCP acceptance passed. Installed MCP acceptance exposed all 7 browser tools with grants. A live Edge MCP session read Books to Scrape, performed two paced scrolls, followed its unique Next link, and verified page 2.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.66-x64.exe` (72,739,055 bytes; SHA-256 `849869b93712fd7fbedfaaca02751a54c7e6fc05b0a93422b7473b12f862ca2a`). Installed and launched as version 0.1.66. Codex MCP configuration now points to the matching bundled bridge.

## 0.1.65
- Fixed the desktop keyboard recorder startup race so recording begins only after Windows has registered its native hooks, and added an engine preflight mapping for selector-targeted `Press UI Key` activities.
- Verification: 365 Python tests and 153 frontend tests passed; TypeScript/Vite production build and frozen MCP acceptance passed. A controlled live Windows UIA test confirmed printable text is not recorded, Enter is captured against a uniquely identified editor, and a workflow keypress plus text readback succeeds.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.65-x64.exe` (72,719,652 bytes; SHA-256 `5a7715f5469daf139f3941cd141d72f9eb7b7178a063baea104ffb171a521254`). Installed and launched successfully as version 0.1.65.
## 0.1.64
- Expanded the Windows desktop recorder to capture an allowlist of non-text navigation keys and shortcuts as selector-targeted `Press UI Key` activities. Printable keys, typed values, password fields, clipboard shortcuts and out-of-target events are not recorded.
- Verification: 363 Python tests and 153 frontend tests passed; TypeScript/Vite production build passed. Frozen MCP acceptance confirmed the UI key activity accepts Enter, rejects Alt+F4, and stages a live workflow draft.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.64-x64.exe` (72,721,199 bytes; SHA-256 `e9270d3912a503ec945d33ea18878af35d919f6ed8ac6b832a69bedb2aa710bd`).

## 0.1.63
- Hardened `Press UI Key`: the Windows UIA and Linux AT-SPI adapters now require the selected control to confirm keyboard focus before emitting any key event.
- Verification: 52 focused Python tests passed across key validation, workflow schema, Windows UIA, and Linux AT-SPI adapters. Frozen MCP acceptance confirmed `Enter` is accepted and `Alt+F4` is rejected, then staged a live draft successfully.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.63-x64.exe` (72,710,451 bytes; SHA-256 `b9d3f65259c31ae2a077676a9b55497402b28021131daa02476511497e53733e`). Installed and launched successfully.

## 0.1.62
- Added `Press UI Key`, a selector-targeted desktop keyboard activity that focuses one exact accessible control and supports navigation keys plus a short, explicit shortcut allowlist. Password controls, clipboard shortcuts and arbitrary combinations are rejected.
- Verification: 353 Python tests and 153 frontend tests passed; TypeScript/Vite build passed. Focused tests cover the allowlist, workflow schema, Windows UIA focus, Linux AT-SPI focus and password rejection. The frozen MCP activity-catalog and live-draft acceptance check passed.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.62-x64.exe` (72,711,725 bytes; SHA-256 `bcc985b5e0c014233a886d503af6523368922b023875a6a9a5a2139b0cc15271`). Built but not installed because the running 0.1.61 app was left open.

## 0.1.61
- Added an opt-in Windows desktop click recorder to the accessibility inspector. It resolves clicks against one selected foreground application using UIA, excludes password and ambiguous controls, and creates editable selector-based activities. It does not record keyboard events, typed text, screenshots or clipboard data; transient coordinates used for hit testing are not stored or shown.
- Verification: 340 Python tests passed; 153 frontend tests passed across 36 files; TypeScript/Vite build, lockfile check, frozen MCP catalog/staging acceptance and Windows NSIS build passed. Recorder tests verify app scoping, selector-only output, ambiguity/password rejection, explicit permission and count-only audit data. The live recorder has not yet been exercised against a separate real Windows application.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.61-x64.exe` (72,707,460 bytes; SHA-256 `da6ec6a3a3184d09baffbaf554040e0c975fbbcc0e336097f5bf7bfd2d2fdac7`). Built but not installed; the installed Studio process remains live.

## 0.1.60
- Added a bounded `Wait for Browser Response` activity for synchronizing with API-driven pages. It filters recent responses by URL path substring, method and status, and exposes only method, status and content type; response bodies and URL query data are not retained in workflow state, logs or audit records.
- Verification: 332 Python tests passed; 153 frontend tests passed across 36 files; TypeScript/Vite production build, locked dependency check, frozen MCP staging/catalog acceptance, and Windows NSIS installer build passed. A local Playwright test triggered a real response and verified that only method/status/content type reached variables, logs and audit evidence.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.60-x64.exe` (72,690,552 bytes; SHA-256 `2f34a10cab5afb11ccb3e30659e95abe2686092b22007004874245aa16b406cd`). Built but not installed; the installed Studio process still has a live window handle.

## 0.1.59
- Added native tree-item expansion and collapse on Windows UI Automation and Linux AT-SPI, with inspector capability detection, idempotent state-aware operations, selectable tree items, and expanded/collapsed wait conditions.
- Verification: 330 Python tests passed; 150 frontend tests passed across 35 files; TypeScript/Vite build, locked dependency check, frozen MCP acceptance, and git diff check passed. Controlled Windows UIA and AT-SPI adapter tests verified expand/collapse, exact selection, state waits, and fail-closed behavior.
- Windows x64 NSIS installer: release/Open-RPA-Studio-Setup-0.1.59-x64.exe (72,682,579 bytes; SHA-256 b007ea8c044810468857bb54f6b2fe1d657c31004d00aacd74059f53d45bb4de). Built, not installed; the previously installed Studio still has a live process and window handle.
## 0.1.58
- Browser interactions, waits, assertions, repeated-record extraction and HTML table reads can now target a uniquely identified iframe with `frameSelector`. Ambiguous, missing or non-iframe matches fail with a node-specific error; omitted selectors continue to target the main document.
- Verification: 326 Python tests passed; 149 frontend tests passed across 35 files; TypeScript/Vite build, locked dependency check, frozen MCP acceptance and `git diff --check` passed. Real Chromium exercised iframe interaction, repeated-record and table extraction, URL resolution, and ambiguity rejection.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.58-x64.exe` (72,675,990 bytes; SHA-256 `088f387022bb655d7a93a91df308c6144aea47c93fd865f61fbc5409d1452b58`). Built successfully; not installed because the prior Studio process still has a live window handle.
## 0.1.57
- Added window wait, activate, minimize, restore and normal close activities matched by exact title and/or process ID. Ambiguous matches fail closed; close waits for disappearance and never terminates the process forcibly.
- Closing requires `confirmClose: true` and a separate destructive-action confirmation for each run. Timeout after a close request is reported explicitly, including apps waiting for in-app confirmation.
- Verification: 324 Python tests passed; 149 frontend tests passed across 35 files; TypeScript/Vite build, dependency-lock check, frozen MCP acceptance and `git diff --check` passed. Window lifecycle behavior was exercised through the controlled Windows UIA adapter fixture; live third-party app compatibility remains platform dependent.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.57-x64.exe` (72,676,271 bytes; SHA-256 `28c368709991e7c1f3768ad35f5f4b3756155d065141f695a3d1ee18e7e98369`). The existing Studio process remained open and untouched; this installer has not been installed or launch-tested.

## 0.1.56
- Added semantic `Invoke UI Control` for exact Windows UIA and Linux AT-SPI selectors. Windows calls the native InvokePattern without pointer movement and does not fall back to coordinate clicks; the desktop inspector exposes it only for supported control types.
- Added execution-plan classification as an external desktop action, so the one-run desktop permission review accurately covers UIA invocation.
- Verification: 318 Python tests passed; 148 frontend tests passed across 35 files; TypeScript/Vite build, locked dependency check and frozen MCP acceptance passed. UIA invoke behavior was tested against a controlled Windows adapter fixture; cross-platform live-app acceptance remains platform dependent.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.56-x64.exe` (72,663,951 bytes; SHA-256 `5f63c53c0284422896f6c9dfe668654a189e10ecd4192e7a5c1ea8128f4e0409`). The existing Studio process remained open and untouched; this installer has not been installed or launch-tested.

## 0.1.55
- Browser interaction recording now captures coalesced wheel scrolling as bounded, editable `Scroll Page` activities with a paced delay. Stopping recording flushes the last pending scroll event.
- Verification: 316 Python tests passed, 147 frontend tests passed across 35 files, TypeScript/Vite production build and locked dependency check passed, and frozen MCP acceptance passed. A real Chromium recorder test confirmed wheel capture and workflow validation.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.55-x64.exe` (72,659,788 bytes; SHA-256 `13dabf506d7b0187b2df05b2a0e89af3725e925e1753cfb0170702e6eed5cae3`). The 0.1.52 app process remained open and untouched; this installer has not been installed or launch-tested.

## 0.1.54
- Added Browser Upload for up to 20 project-root-approved files and Browser Download for selector-triggered downloads. Uploads use the workflow file-size limit; downloads save atomically with a no-overwrite default and are checked against the limit before being written into the project.
- Added audit events and result metadata that record file counts, paths and byte counts without logging file contents. Network permission review includes upload and download actions.
- Verified: 315 Python tests passed; 147 frontend tests passed across 35 files; `npm run build` and `uv lock --check` passed.
- Real Chromium acceptance verified approved-root upload, download persistence, default no-overwrite, and oversized-download rejection. Downloads are initially spooled by Playwright to its temporary cache before the application checks the size; the configured size limit protects the project destination, not that temporary cache.
- Windows x64 NSIS installer: `release/Open-RPA-Studio-Setup-0.1.54-x64.exe` (72,658,596 bytes; SHA-256 `a93648df88cd09550596eb7ed671ca84a752032bce06419e54ccd89e57656bf5`).
- The already running installed application was left untouched; installing 0.1.54 has not yet been verified on this machine.

## 0.1.53
- Browser workflows can now open named tabs, assign stable names to popups opened by prior actions, switch tabs and close a tab without ending the session. Capture Popup handles delayed page-created notifications and refuses to close the last tab.
- New browser pages receive the same explicit network permission checks, public-address filtering and WebSocket blocking as the original page. Browser interactions that may initiate requests now require the network permission in the pre-run plan.
- Verification: 312 Python tests, 147 frontend tests, production TypeScript/Vite build, locked dependency check, real Chromium popup/tab acceptance, frozen MCP catalog acceptance, and Windows NSIS installer build passed. Installer: 69.29 MiB, SHA-256 `21cde3cfb68de4ac6680068fbafcad897a1d38da1adc240b4c06c039baa4924d`.

## 0.1.52
- Browser UI recording now produces editable hover and safe keyboard steps alongside clicks, fills, selections and checkbox actions. Key recording is allowlisted, and text entry values remain excluded.
- Added native Hover Web Element and Press Key on Web Element activities with exact selector validation and an explicit safe-key allowlist. Browser inspector controls also offer direct hover activities where supported.
- Verification: 310 Python tests, 146 frontend tests, production TypeScript/Vite build, locked dependency check, frozen MCP catalog acceptance, and Windows NSIS installer build passed. Installed app launched with version 0.1.52. Installer: 69.28 MiB, SHA-256 `bfed48624a512dc4b1207ff757287f1d71b98d3934ccc8c7bd7663daf8cdab4a`.

## 0.1.51
- Browser Launch now lets authors choose Playwright Chromium, Firefox or WebKit, Chrome, Edge, or a custom Chromium executable, with visible/headless mode exposed in the inspector. The default is visible.
- Added bounded repeated-card extraction into structured records and paced page scrolling with live per-step progress events. Added a safe AI drafting preference to keep browser windows visible when the user asks to watch a task.
- Expanded accessibility-based desktop automation with exact ComboBox/ListBox/ListItem selection and state-aware checkbox/radio actions on Windows UIA and Linux AT-SPI.
- Verification: 309 Python tests, 146 frontend tests, production frontend build, and frozen MCP activity-catalog acceptance passed. The Windows installer built successfully: 69.28 MiB, SHA-256 `416c705fa7fa8583bb44710b664f760b9c4df680312ca1a6ec7d6e0a9dafe46c`.

## 0.1.48
- AI workflow drafting can use saved API connection metadata to construct API Request activities. Provider prompts receive only connection ID, display name, base URL and authentication type; API headers, OAuth client details, vault references and credentials are excluded. The bridge rejects API activities that reference an unsaved connection, and the drafting panel discloses metadata sent to providers.
- Verification: 289 Python tests, 142 frontend tests, production frontend build and live Ollama acceptance passed. Ollama sequence, flowchart and state-machine drafts validated and executed successfully. Windows NSIS installer: 69.22 MiB, SHA-256 `bcdb16f079b1bc66aa74b8f40aabddc7e63b531115d73a9213d4697830f5d1d6`.
## 0.1.39
- OpenAPI import now detects an unambiguous 2xx JSON array-of-objects response and generates editable JSON Pointer field mappings. The API Request editor can configure or adjust the array pointer, scalar output fields, result variable and row ceiling.
- Native API Request execution parses and maps successful JSON responses into bounded record arrays while retaining the raw response. Added strict schema checks for RFC 6901 pointers, unique field names, output-variable conflicts and a 10,000-record cap; mapping errors identify the activity without exposing response contents.
- Verification: 130 frontend tests, 258 Python tests, TypeScript production build and `cargo check --locked` pass. The frozen v0.1.39 bridge passes real MCP stdio staging/clear acceptance and advertises all 14 expected tools. Unsigned Windows NSIS installer: 69.18 MiB, SHA-256 `5c58e1ca8e6b17dd0492a4b286abfb8fbd5767cc4673a623793f0635d80f0df6`.

## 0.1.38
- Made staged MCP workflows visible directly in the Studio designer: the active canvas now renders the latest validated snapshot under a non-modal live-build banner, with Insert and Dismiss controls. The editor updates as staged snapshots change instead of placing a full-screen dialog over the canvas.
- Corrected the packaged MCP rollout path. The installed 0.1.30 bridge did not advertise `openrpa_stage_workflow_draft`, although current source does. This release packages the current MCP server and live canvas preview together.
- Verification: 256 Python tests, all 127 frontend tests, TypeScript/production frontend build and `cargo check --locked` pass. The frozen 0.1.38 bridge was queried over MCP stdio: it advertises 14 tools including `openrpa_stage_workflow_draft`, reports all configured startup permissions, accepted a live draft, and cleared it successfully. The unsigned Windows NSIS installer is 69.17 MiB, SHA-256 `393260d40fdf61f1ae5392fe0dbbe9e1db2992ca769f99d91ab336ac0c20af82`.

## 0.1.37
- Added validated MCP live workflow snapshots. With `--allow-edit`, an agent can stage each meaningful build step and Studio displays successive snapshots without changing the saved project. Users can insert a snapshot into the editor or dismiss it; a final MCP create/update clears the matching preview. Preview files are project-local, atomically replaced, validated before display and excluded from `.orpa` exports.
- Added cross-layer MCP-to-Studio preview and commit regression coverage. Verification: 256 Python tests, all 127 frontend tests, production frontend build and `cargo check --locked` pass. The packaged bridge advertises the preview tools and successfully stages a workflow through real MCP stdio. Windows installer: 69.17 MiB, SHA-256 `28872c4e1a74a17fe5e26c24f5acefa245fbc1c4738561c8adb9263acac86054`.

## 0.1.36
- Added local OpenAPI 3.0/3.1 JSON and YAML import to the API Request editor. It lists supported operations, applies path/query/header parameters and JSON request examples to the normal editable activity, and creates matching string variables for required parameters.
- Import is bounded to 2 MB, resolves local references only, reports external references without fetching them, and executes no specification content. Verification: 125 frontend tests and production build pass; `npm audit --omit=dev` reports zero vulnerabilities. Windows NSIS installer: 69.16 MiB, SHA-256 `d34cd790ac0647ea45b2979dd7725c939d4da91f31accd416d3b72849059cd1f`.

## 0.1.35
- Added OAuth 2.0 client-credentials authentication to API connection profiles, including client-secret Basic and form-body methods, scope/audience, restricted token exchange, in-memory expiry-aware token reuse, and token-aware connection tests. Existing v1 API connection files remain readable and migrate on save.
- OAuth token exchange and the connection-test UI path have mocked coverage; no provider account was available for live OAuth acceptance. Verification: 253 Python tests, 121 frontend tests, frontend production build, `cargo check --locked`, and `uv lock --check` pass. Windows NSIS installer: 69.13 MiB, SHA-256 `3f55c27de40c028bc4e84f2701e3c433d56f3efead5428a74a28338523db25c5`.

## 0.1.34
- MCP project synchronization now selects the single newly created or changed workflow after a clean reload, so newly built workflows appear directly in the designer. Studio identifies the MCP-created/updated workflow in its status message. Multiple simultaneous changes keep the current selection; unsaved local edits still require a deliberate reload.
- Added focused workflow-change detection tests. Verification: 247 Python tests, 121 frontend tests and the production frontend build pass. Windows NSIS installer: 69.12 MiB, SHA-256 `8e13a9bde3f4f5ca567809dbfebd42a3df1260397569dbb0b34879defc65cf36`.

## 0.1.33
- Added a reusable API connection manager in Studio and native MCP discovery for saved connection metadata. Bearer tokens and API-key values remain in the OS credential vault; API workflow results and audit records do not include the stored secret.
- Added a dedicated **API Request** activity editor and engine support for bounded GET/POST/PUT/PATCH calls, query parameters, request bodies, shared headers, host-bound relative paths, request-size/time limits, per-connection pacing, network permission checks, and audit events.
- Added API connection persistence, validation, vault, bridge, workflow schema and MCP permission tests. Changing authentication modes clears the old vault credential rather than silently reusing it. Live MCP acceptance run `7c4de51f-ba01-4030-bc4b-ecc26ef5cf7d` fetched JSONPlaceholder `/todos/1` in 186 ms. Verification: 247 Python tests and 119 frontend tests pass; frontend production build, `cargo check --locked`, and `uv lock --check` pass. Windows NSIS installer: 69.12 MiB, SHA-256 `66ad7d2d0e88071b87e58da85986c2eb10602454c99a04674272003d1960690e`.
- OAuth 2.0 flows, DELETE requests, cursor/next-link pagination, automatic retries and generated field mappings remain unsupported.

## 0.1.31
- Added **Paginated API Read**, a native bounded GET activity for page-numbered JSON APIs. It maps a selected JSON array into records, reports page/count/byte/truncation metadata, observes cancellation between pages, limits pages/items/bytes, rejects unsafe headers, and requires the existing per-run network permission and restricted egress client. It can use OS-vault credentials from the existing Credential Get activity through header expressions without persisting secrets in the workflow.
- Added API activity documentation, MCP network preflight, browser-preview catalog support and a public screenshot. Cursor/next-link pagination, OAuth, reusable connection profiles, pacing and advanced response mapping remain future work.
- Verification: 232 Python tests and 119 frontend tests pass; production frontend build, Rust host check and locked dependency check pass. A live workflow-engine GET to JSONPlaceholder fetched two pages and four records in 670 ms with the expected `truncated=true` at the configured page cap. Windows NSIS installer is 69.06 MiB, SHA-256 `ca3addfec4394eeb8462e75f4beeae68df97d133f1a6cd706b02af7d1e2c517c`.

## 0.1.32
- Studio now detects stable external project changes, including edits made by the bound Open RPA MCP server. It reloads clean projects automatically and offers an explicit reload when local edits are unsaved, preserving in-memory work.
- Added `project.signature` to the native bridge for validated, content-based project change detection.
- Browser Launch can target installed Chrome or Microsoft Edge when bundled Playwright Chromium is unavailable; missing Chromium now reports an actionable setup error.
- Verification: 235 Python tests and 119 frontend tests pass; production frontend build, `cargo check --locked`, and `uv lock --check` pass. Actual MCP execution `233a8837-e829-4218-909f-a6878671d438` succeeded: Chrome opened Google (which returned anti-automation content), a public Nasdaq quote supplied MSFT $528.1132 at 4:33 AM ET, and the workflow logged the source and timestamp. Windows NSIS installer: 69.06 MiB, SHA-256 `88ae019abd43248d017183f4ad542de2340dbbd5bdabd8df14e0f1bbb0ba5c87`.

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
## 0.1.113
- Added a durable local MCP job worker with immediate or scheduled single-run submissions, idempotency keys, workflow-content snapshots, queue status inspection and cancellation. Interrupted jobs are marked and never replayed; automatic whole-workflow retries remain disabled.
- Added a Studio Jobs tab for live queue monitoring and cooperative cancellation, backed by a read-only queue view. Job inputs are not shown by monitoring tools or the Studio UI.
- Verification: 38 focused Python/MCP tests passed; frontend suite 179 passed; production Vite build, frozen MCP acceptance and Windows x64 NSIS packaging passed. Installer: `release/Open-RPA-Studio-Setup-0.1.113-x64.exe` (69.64 MiB; SHA-256 `ce211af2f26a68f9ff6ecde34c0244b4ce5ec3f290ef6819249823b35b6eb5ea`). See `docs/LOCAL-JOB-ORCHESTRATION.md` for worker guarantees and limitations.
