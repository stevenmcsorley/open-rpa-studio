# Automation adapters

## Browser

Install the optional Playwright package and Chromium. A workflow can launch Chromium, navigate, click, fill, select an option, check/uncheck controls, read element text, take screenshots, and close it. Locator kinds include accessible role, label, visible text, placeholder, test ID, and CSS. Role and label selectors are preferred; CSS is available for applications with incomplete accessibility metadata.

The desktop Studio's **Inspect Web UI** tool opens a visible browser session only while the explicit network permission is enabled. Authors can navigate the page themselves, refresh a bounded list of visible named controls, then add click, fill, select, check/uncheck, or read-text activities. Generated activities use accessible role/name or test-id/placeholder selectors and enter the normal workflow editor for review. Ambiguous selectors cannot be added from the picker. This is an element picker, not an interaction recorder; it does not capture arbitrary user gestures or persist page content.

Inspection uses standard HTTP(S) ports and blocks non-public DNS answers on initial navigation and intercepted requests. The context blocks service workers, downloads, and WebSocket connections. Chromium performs its own DNS lookup, so DNS rebinding remains a residual limitation. Page JavaScript runs in the visible browser; inspect only sites you trust. Inspector history records the host and permission grant, not the full URL or page contents. Closing the inspector closes its browser context.

## Desktop

Install the optional PyAutoGUI package. Activities can click coordinates, type into the current focus, press keys/hotkeys, and capture screenshots. These are coordinate/focus-dependent operations; robust AT-SPI accessibility selectors and desktop recording are not implemented. The desktop action capability must be enabled for each run. PyAutoGUI's fail-safe remains enabled.

## Availability and limits

An absent optional dependency returns `runtime-unavailable` on the activity that needs it. The engine never converts an unavailable adapter into a successful no-op. Linux desktop control additionally depends on an active graphical session and its security model. Browser and desktop adapters are optional and do not change the deterministic core format. The limited browser preview cannot use Playwright, desktop, filesystem, or network adapters; these require the desktop engine.
