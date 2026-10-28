# Changelog

## 0.1.130

- Added compact MCP search/execute discovery and portable sequential batches to Windows, macOS, Linux and frozen bridges, with native permission and validation checks preserved.
- Added optional sandboxed JavaScript for Linux source installations, bounded output/calls, partial-completion traces and full native compatibility mode.
- Added cross-platform contract CI and packaged-runtime compact MCP acceptance; release automation now builds Windows x64, Linux x64, macOS Apple Silicon and macOS Intel.
- Aligned desktop, engine, MCP and Rust package versions at 0.1.130. Reconnect MCP clients after upgrading.


## 0.1.112
- Studio scrollbars now use the application graphite/green palette with slim rounded thumbs and consistent Chromium/WebView and Firefox styling.
- Verification: frontend suite 179 passed; production build and frozen MCP packaging acceptance passed.
- Windows NSIS: `release/Open-RPA-Studio-Setup-0.1.112-x64.exe` (72,987,802 bytes; SHA-256 `c364b4a87f638c95607de8f3655693967693d081b140050922b1480826877eff`).

## 0.1.111
- AI draft preview shows provider-reported token usage for supported local and remote providers; no price estimates are inferred.
- Verification: Python suite 497 passed; frontend suite 179 passed; production build and frozen MCP acceptance passed. Live Ollama sequence, flowchart, and state-machine drafts validated and executed with reported usage counts.
- Windows NSIS: `release/Open-RPA-Studio-Setup-0.1.111-x64.exe` (72,983,599 bytes; SHA-256 `82187cb902456f5196252d0b0a13b298e974d7d3e78a021df9b257f9d5f1edca`).

## 0.1.101
- Browser JSON schema discovery distinguishes fields present in every sampled item from optional sample fields and preserves mixed scalar types without returning API values. Responses without `Content-Length` remain rejected before body reads because Playwright buffers response data.
- Verification: Python 464 passed; frontend 170 passed; production build and frozen MCP acceptance passed. Installed bridge acceptance passed; Studio upgraded and launched responsive.
- Windows NSIS: `release/Open-RPA-Studio-Setup-0.1.101-x64.exe` (72,962,398 bytes; SHA-256 `2fa074678848d19229429b192f04f37d3d7d882fa77f8d95c54eb2d406ae3779`).

## 0.1.100
- Browser API response inspection can return bounded, value-free JSON structure metadata or map selected scalar fields. Schema discovery reports object-array JSON Pointers without exposing response values.
- Verification: Python 463 passed; frontend 170 passed; production build and frozen MCP acceptance passed. Installed bridge acceptance passed; Studio upgraded and launched responsive.
- Windows NSIS: `release/Open-RPA-Studio-Setup-0.1.100-x64.exe` (72,963,556 bytes; SHA-256 `734eace0e78cf4f1c4ad28e9e8e1b03086be30ccf742615d791f1f377d9718d3`).

## 0.1.51
- Browser Launch now lets authors choose Playwright Chromium, Firefox or WebKit, Chrome, Edge, or a custom Chromium executable, with visible/headless mode exposed in the inspector. The default is visible.
- Added bounded repeated-card extraction into structured records and paced page scrolling with live per-step progress events. Added a safe AI drafting preference to keep browser windows visible when the user asks to watch a task.
- Verification and Windows installer details will be recorded after the release build.

## 0.1.48
- AI workflow drafting can now use saved API connection metadata to construct API Request activities. Provider prompts receive only connection ID, display name, base URL and authentication type; API headers, OAuth client details, vault references and credentials are excluded. The bridge rejects API activities that reference an unsaved connection, and the drafting panel discloses metadata sent to providers.
- Verification: 289 Python tests, 142 frontend tests, production frontend build and live Ollama acceptance passed. Ollama sequence, flowchart and state-machine drafts validated and executed successfully. Windows NSIS installer: 69.23 MiB, SHA-256 `3060609c2b57a7f7e0310b88e4ea5af055a3767f456afe07b895168998e430ac`.
