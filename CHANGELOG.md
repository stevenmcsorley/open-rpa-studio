# Changelog

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
