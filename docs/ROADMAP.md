# Delivery roadmap

## Built in this slice

- Versioned local project format and Python execution engine.
- Safe expression evaluation, argument/variable scoping, sequence/if/for-each/while/retry/switch/try-call control flow with shared execution quotas. Retry Scope supports filtered errors, bounded backoff, variable rollback and explicit repeat-safety acknowledgement.
- File, text, regex, CSV, JSON, wait, and explicitly permissioned HTTP activities.
- Optional Playwright browser interactions and PyAutoGUI desktop actions, both permission-gated and capability-checked.
- Optional provider-based workflow drafting for Ollama, LM Studio, local OpenAI-compatible servers, OpenAI, Anthropic Claude, OpenRouter and compatible HTTPS endpoints. Credentials stay in an OS vault; returned workflows are validated before explicit insertion.
- Desktop shell, activity palette, visual sequence editor, property inspector, validation, execution state and logs.
- Nested visual authoring for If/Else, For Each, While, Switch cases/default and Try/Catch/Finally branches, including branch-local insertion, sibling ordering and removal.
- Boundary-based desktop debugger with start-paused runs, activity breakpoints, pause/continue, step-over, step-into and cancellation while paused.
- Paused debugger variable editing for bounded JSON values, with declared-type enforcement, credential exclusion and value-free audit metadata.
- Visible Playwright browser inspection that discovers accessible controls and adds editable click/fill/select/check/read activities through the ordinary workflow authoring path.
- Browser interaction recording for uniquely identified, named controls. Recording preserves action order and selector metadata, excludes password/email/payment/file/hidden fields, never reads typed values, and requires review before insertion; recorded fill/select values are left blank for explicit author completion.
- Flowchart palette insertion splices activities into the selected path, preserves downstream transitions, routes Decision insertions through True, and inserts before End nodes without leaving unreachable nodes.
- Example CSV automation and engine/UI verification.

## Next release gates

1. **Debugging completion:** add durable debug checkpoints and richer error stack context. Paused variable editing and Step Out are supported at activity boundaries. Mid-activity pause remains adapter-dependent.
2. **Visual authoring:** add richer graph navigation and state-machine workflow models. Flowchart layout is now draggable and persisted; node connections remain edited with destination selectors rather than link/reconnect gestures.
3. **Automation adapters:** browser element inspection and bounded interaction recording across navigation are available for public pages with explicit network permission. Add browser waits/assertions and editable selector healing; implement Linux desktop via AT-SPI/AT-SPI2 where available.
4. **Security:** signed plugin metadata, dependency/SBOM scans, adversarial package and egress tests, threat-model review, safe package verification.
5. **Distribution:** Windows x64 per-user NSIS installer now builds and installs in a workspace-local smoke test, with a bundled Python engine and no-console child process. Still verify on a clean Windows machine; sign binaries; test upgrades, uninstall and WebView2 bootstrap behavior; produce Linux AppImage/deb on a supported Linux build host.
6. **AI (optional):** integration tests against available local models and authenticated remote providers, per-provider endpoint validation and retry/compatibility handling. Core authoring/execution remains available without a model.

“Production” requires passing these operational and security gates for each supported platform; the initial vertical slice is not yet a production-certified release.
