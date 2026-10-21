# Delivery roadmap

## Built in this slice

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
- State-machine transition overview visualizes initial, final, guarded, cyclic and disconnected states, with graph-node selection wired to the existing state editor.
- Example CSV automation and engine/UI verification.
- Desktop toolbar import/export for deterministic, integrity-checked `.orpa` project packages, with export workflow validation and safe empty-folder extraction.
- Reusable workflow argument mapping with per-call-site outputs and preflight validation.
- Bounded text extraction from selectable PDF pages, with a page-count output, page boundaries, explicit file-read auditing, and documented no-OCR/encryption limits.
- Local SQLite data integration through parameterized read-only queries with an SQLite authorizer allowlist, approved-root confinement, row/byte/time caps, cancellation, and audited attempt/result metadata.

## Next release gates

1. **Debugging completion:** workflow invocation failures now carry a bounded, redacted call path and origin workflow/activity through run results and durable history. Add durable debug checkpoints; paused variable editing and Step Out are supported at activity boundaries. Mid-activity pause remains adapter-dependent.
2. **Visual authoring:** add graph-style overview/navigation to flowchart action subtrees. The sequence editor now has a nested workflow outline that selects and scrolls to branch activities; the state-machine graph supports selecting, adding, editing, reordering, and removing transitions; flowchart navigation and the minimap are implemented.
3. **Automation adapters:** add editable selector healing and broaden accessibility acceptance across GTK, Qt, WPF, Win32, WinForms and packaged-app targets. Browser waits/assertions and bounded browser interaction recording are implemented.
4. **Security:** signed plugin metadata, dependency/SBOM scans, adversarial package and egress tests, threat-model review, safe package verification.
5. **Distribution:** Windows x64 per-user NSIS installer now builds and installs in a workspace-local smoke test, with a bundled Python engine and no-console child process. Still verify on a clean Windows machine; sign binaries; test upgrades, uninstall and WebView2 bootstrap behavior; produce Linux AppImage/deb on a supported Linux build host.
6. **AI (optional):** integration tests against available local models and authenticated remote providers; broader per-provider structured-output fallbacks, bounded cancellation, and compatibility handling remain. Typed model IDs now work when a host's model catalogue is unavailable. Core authoring/execution remains available without a model.

“Production” requires passing these operational and security gates for each supported platform; the initial vertical slice is not yet a production-certified release.
