"""Verified multi-selection for native selects and accessible ARIA listboxes."""
from __future__ import annotations

from typing import Any, Callable

MAX_ARIA_OPTIONS = 500


def select_multiple_options(locator: Any, values: list[str], timeout_ms: int, check_cancel: Callable[[], None] | None = None) -> list[str]:
    """Replace a selection by native option values or exact ARIA option names."""
    metadata = locator.evaluate("""el => ({
      multiple: el.tagName.toLowerCase() === 'select' && el.multiple,
      role: el.getAttribute('role') || '',
      ariaMultiple: el.getAttribute('aria-multiselectable') === 'true'
    })""")
    if metadata["multiple"]:
        selected = locator.select_option(value=values, timeout=timeout_ms)
        if set(selected) != set(values):
            raise ValueError("Browser did not retain all requested selected values")
        return selected
    if metadata["role"] != "listbox" or not metadata["ariaMultiple"]:
        raise ValueError("Select Multiple requires a native multiple select or an accessible ARIA listbox with aria-multiselectable=true")

    options = locator.get_by_role("option")
    option_count = options.count()
    if option_count > MAX_ARIA_OPTIONS:
        raise ValueError(f"ARIA listbox has {option_count} options; the safe limit is {MAX_ARIA_OPTIONS}")

    def option_name(option: Any) -> str:
        return option.evaluate("""el => {
          const labelled = (el.getAttribute('aria-labelledby') || '').split(/\\s+/)
            .filter(Boolean).map(id => document.getElementById(id)?.innerText || '').join(' ');
          return String(el.getAttribute('aria-label') || labelled || el.innerText || el.textContent || el.getAttribute('title') || '')
            .replace(/\\s+/g, ' ').trim();
        }""")

    names: list[str] = []
    for index in range(option_count):
        if check_cancel is not None:
            check_cancel()
        name = option_name(options.nth(index))
        if not name:
            raise ValueError("ARIA listbox contains an option without a stable accessible name")
        names.append(name)
    if len(set(names)) != len(names):
        raise ValueError("ARIA listbox contains duplicate option names; select by a uniquely named option")
    if any(name not in names for name in values):
        raise ValueError("ARIA listbox does not contain every requested option name")

    for name in names:
        if check_cancel is not None:
            check_cancel()
        option = locator.get_by_role("option", name=name, exact=True)
        if option.count() != 1:
            raise ValueError("ARIA listbox option names changed or became ambiguous during selection")
        selected = option.get_attribute("aria-selected") == "true"
        if selected != (name in values):
            option.click(timeout=timeout_ms)

    selected_names: list[str] = []
    current = locator.get_by_role("option")
    current_count = current.count()
    if current_count > MAX_ARIA_OPTIONS:
        raise ValueError(f"ARIA listbox has {current_count} options; the safe limit is {MAX_ARIA_OPTIONS}")
    for index in range(current_count):
        if check_cancel is not None:
            check_cancel()
        option = current.nth(index)
        if option.get_attribute("aria-selected") == "true":
            selected_names.append(option_name(option))
    if set(selected_names) != set(values) or len(selected_names) != len(values):
        raise ValueError("Browser did not retain the requested ARIA listbox selection")
    return selected_names
