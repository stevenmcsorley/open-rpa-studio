# Automation adapters

## Browser

Install the optional Playwright package and Chromium. A workflow can launch Chromium, navigate, click, fill, select an option, check/uncheck controls, read element text, take screenshots, and close it. Locator kinds include accessible role, label, visible text, placeholder, test ID, and CSS. Role and label selectors are preferred; CSS is available for applications with incomplete accessibility metadata.

The desktop Studio's **Inspect Web UI** tool opens a visible browser session only while the explicit network permission is enabled. Authors can navigate the page themselves, refresh a bounded list of visible named controls, then add click, fill, select, check/uncheck, or read-text activities. Generated activities use accessible role/name or test-id/placeholder selectors and enter the normal workflow editor for review. Ambiguous selectors cannot be added from the picker. This is an element picker, not an interaction recorder; it does not capture arbitrary user gestures or persist page content.

Inspection uses standard HTTP(S) ports and blocks non-public DNS answers on initial navigation and intercepted requests. The context blocks service workers, downloads, and WebSocket connections. Chromium performs its own DNS lookup, so DNS rebinding remains a residual limitation. Page JavaScript runs in the visible browser; inspect only sites you trust. Inspector history records the host and permission grant, not the full URL or page contents. Closing the inspector closes its browser context.

## Desktop

### Windows UI Automation

Install the optional `desktop` extra. On Windows this includes pywinauto's Microsoft UI Automation (UIA) backend. **Inspect UI → Inspect Desktop UIA** lists visible top-level windows and a bounded set of named interactive controls. The inspector records identity metadata only: accessible name, Automation ID, control type, match count and enabled state. It never reads field values and excludes password controls.

The picker creates normal editable activities: `desktop_ui_click`, `desktop_ui_fill`, `desktop_ui_text` and `desktop_ui_wait`. Selectors include an exact top-level window title, optional process ID, and an accessible name and/or Automation ID, optionally constrained by control type. Interactions require the explicit desktop permission. Ambiguous control matches are rejected; add an Automation ID or control type to disambiguate. Set Text only targets an Edit control. Reading password controls is blocked; use a credential-vault activity for secrets. Wait polls every 200 ms and checks cancellation between UIA queries. A single COM/UIA operation may still block until that call returns.

The UIA adapter was exercised against a local WinForms fixture: the workflow waited for an Edit control, set its text, clicked a button, and read the resulting label text. The engine returned `succeeded` and the expected value. This validates the adapter against a controlled Windows app; it does not prove compatibility with every target framework. Some applications expose incomplete UIA metadata or custom controls.

### Coordinate fallback

PyAutoGUI activities can click coordinates, type into the current focus, press keys/hotkeys, and capture screenshots. These operations depend on screen layout and foreground focus. The desktop action capability must be enabled for each run. PyAutoGUI's fail-safe remains enabled.

### Linux accessibility

Linux coordinate-based desktop actions use PyAutoGUI when a graphical session is available. AT-SPI/AT-SPI2 semantic inspection and actions are not implemented. The capability check reports this limitation instead of treating the bindings as a working adapter.

## Availability and limits

An absent optional dependency returns `runtime-unavailable` on the activity that needs it. The engine never converts an unavailable adapter into a successful no-op. Linux desktop control additionally depends on an active graphical session and its security model. Browser and desktop adapters are optional and do not change the deterministic core format. The limited browser preview cannot use Playwright, UIA, desktop, filesystem, or network adapters; these require the desktop engine.
