# Changelog

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
