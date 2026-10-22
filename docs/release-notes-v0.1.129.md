## Open RPA Studio 0.1.129

### Responsive workspace layout

- Fixed the Studio interface being cut off at the left or right edge in smaller windows.
- Reduced the desktop window minimum size to 700×480 so users can work on smaller displays.
- Activity library and Properties panels automatically collapse into persistent, labeled rails when the window becomes compact. Click a rail to reopen the panel; use its heading control to collapse it again.
- Side-panel widths adapt to the window while retaining the existing Properties resize handle.
- Header actions and output-panel tabs can be reached by horizontal scrolling when the window is too narrow to show every control at once.
- Shorter windows keep the workflow designer usable by limiting the output pane to available height. The output pane can still be resized and collapsed.

### Verification

- Python: 570 tests passed; frontend: 213 tests passed.
- TypeScript and Vite production build passed; frozen MCP acceptance passed.
- Windows x64 NSIS installer: 69.82 MiB. SHA-256: `ee4aecb503cdcf105b5b5d2d7bff9b29f47b0cb6d47f418c89b12e9901cc9f6f`.
- Linux and macOS release packages are built by the tagged GitHub Actions release workflow.
