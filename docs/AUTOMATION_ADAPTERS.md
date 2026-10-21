# Automation adapters

## Browser

Install the optional Playwright package and Chromium. A workflow can launch Chromium, navigate, click, fill, select an option, check/uncheck controls, read element text, take screenshots, and close it. Locator kinds include accessible role, label, visible text, placeholder, test ID, and CSS. Role and label selectors are preferred; CSS is available for applications with incomplete accessibility metadata.

Browser interaction activities may also declare up to ten explicit `selectorFallbacks` (`selectorKind`, `selector`, and optional `exact`). The engine first requires the primary locator to resolve to exactly one control. If it does not, a fallback is accepted only when exactly one configured alternative resolves uniquely and none is ambiguous. It does not fuzzy-match, infer, or click a “similar” element. Hidden/detached waits and hidden assertions preserve their expected absence semantics and do not use fallbacks. Fallback use is recorded by activity ID and alternative index; selector text and page content are excluded from audit events.

The desktop Studio's **Inspect Web UI** tool opens a visible browser session only while the explicit network permission is enabled. Authors can navigate the page themselves, refresh a bounded list of visible named controls, then add click, fill, select, check/uncheck, or read-text activities. Generated activities use accessible role/name or test-id/placeholder selectors and enter the normal workflow editor for review. Ambiguous selectors cannot be added from the picker. This is an element picker, not an interaction recorder; it does not capture arbitrary user gestures or persist page content.

Inspection uses standard HTTP(S) ports and blocks non-public DNS answers on initial navigation and intercepted requests. The context blocks service workers, downloads, and WebSocket connections. Chromium performs its own DNS lookup, so DNS rebinding remains a residual limitation. Page JavaScript runs in the visible browser; inspect only sites you trust. Inspector history records the host and permission grant, not the full URL or page contents. Closing the inspector closes its browser context.

## Desktop

### Windows UI Automation

Install the optional `desktop` extra. On Windows this includes pywinauto's Microsoft UI Automation (UIA) backend. **Inspect UI → Inspect Desktop UIA** lists visible top-level windows and a bounded set of named interactive controls. The inspector records identity metadata only: accessible name, Automation ID, control type, match count and enabled state. It never reads field values and excludes password controls.

The picker creates normal editable activities: `desktop_ui_click`, `desktop_ui_fill`, `desktop_ui_text` and `desktop_ui_wait`. Selectors include an exact top-level window title, optional process ID, and an accessible name and/or Automation ID, optionally constrained by control type. Interactions require the explicit desktop permission. Ambiguous control matches are rejected; add an Automation ID or control type to disambiguate. Set Text only targets an Edit control. Reading password controls is blocked; use a credential-vault activity for secrets. Wait polls every 200 ms and checks cancellation between UIA queries. A single COM/UIA operation may still block until that call returns.

The UIA adapter was exercised against a local WinForms fixture: the workflow waited for an Edit control, set its text, clicked a button, and read the resulting label text. The engine returned `succeeded` and the expected value. This validates the adapter against a controlled Windows app; it does not prove compatibility with every target framework. Some applications expose incomplete UIA metadata or custom controls.

### Coordinate fallback

PyAutoGUI activities can click coordinates, type into the current focus, press keys/hotkeys, and capture screenshots. These operations depend on screen layout and foreground focus. The desktop action capability must be enabled for each run. PyAutoGUI's fail-safe remains enabled.

### Linux AT-SPI

On Linux, the same permission-gated desktop inspector and editable click, set-text, read-text and wait activities use AT-SPI through the distribution's `python3-pyatspi` bindings and an active AT-SPI D-Bus session. The adapter resolves exact accessible window names and control names or `id` attributes, rejects ambiguous matches, and uses AT-SPI Action, EditableText and Text interfaces. Protected/password entries are excluded from inspection and cannot be read or written. Linux editable controls use the workflow `controlType: "Entry"`; Windows UIA continues to use `"Edit"`.

Install the platform packages with your distribution. On Debian or Ubuntu, install `python3-pyatspi`, `gir1.2-atspi-2.0` and `at-spi2-core`; run the engine with a Python interpreter that can import those system bindings and has access to the graphical user's D-Bus session. The bundled Windows bridge is unaffected; Linux currently launches the system `python3`, which can use distribution-managed AT-SPI bindings.

Live Linux acceptance ran on Ubuntu 22.04 under WSL with the GTK3 toolkit, AT-SPI D-Bus registry and Xvfb. The native GTK fixture exposed a window, an editable Entry, buttons and a Label; the inspector excluded a GTK password entry. A saved workflow ran through `openrpa.bridge`, waited for the Entry, set text, invoked Save and read back `Saved Northshire Council`. All four activities succeeded; run ID: `cc30318d-6e73-4092-9b46-a604e6927ad9`. This verifies the GTK3/Ubuntu path only; other desktop environments, GTK versions, Qt applications and WSL configurations need separate acceptance. The runtime probe reports the missing dependency or bus instead of claiming support when unavailable.

## Availability and limits

An absent optional dependency returns `runtime-unavailable` on the activity that needs it. The engine never converts an unavailable adapter into a successful no-op. Linux desktop control additionally depends on an active graphical session and its security model. Browser and desktop adapters are optional and do not change the deterministic core format. The limited browser preview cannot use Playwright, UIA, desktop, filesystem, or network adapters; these require the desktop engine.
