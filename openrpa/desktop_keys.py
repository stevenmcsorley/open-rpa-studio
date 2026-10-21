"""Bounded keyboard actions shared by the semantic desktop adapters."""
from __future__ import annotations

from typing import Any


_SINGLE_KEYS = {
    "Enter": "enter", "Tab": "tab", "Escape": "esc", "Space": "space",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    "Home": "home", "End": "end", "PageUp": "pageup", "PageDown": "pagedown",
    "Backspace": "backspace", "Delete": "delete", "Insert": "insert",
    **{f"F{number}": f"f{number}" for number in range(1, 13)},
}
_CHORDS = {
    "ctrl+a": ("ctrl", "a"), "ctrl+s": ("ctrl", "s"),
    "ctrl+z": ("ctrl", "z"), "ctrl+y": ("ctrl", "y"),
    "ctrl+f": ("ctrl", "f"), "ctrl+enter": ("ctrl", "enter"),
    "ctrl+shift+s": ("ctrl", "shift", "s"), "shift+tab": ("shift", "tab"),
    "alt+left": ("alt", "left"), "alt+right": ("alt", "right"),
}
_RECORDABLE_SINGLE_KEYS = frozenset({
    "Enter", "Tab", "Escape", "Up", "Down", "Left", "Right", "Home", "End", "PageUp", "PageDown",
})
_RECORDABLE_CHORDS = frozenset({
    "ctrl+a", "ctrl+s", "ctrl+f", "ctrl+enter", "ctrl+shift+s", "shift+tab", "alt+left", "alt+right",
})
SUPPORTED_DESKTOP_KEYS = frozenset(_SINGLE_KEYS) | frozenset(
    "+".join(part.title() if part not in {"ctrl", "alt", "shift"} else part.title()
             for part in chord.split("+"))
    for chord in _CHORDS
)


def normalize_key(key: Any) -> tuple[str, ...]:
    if not isinstance(key, str) or not key.strip() or len(key) > 32:
        raise ValueError("key must be one supported key name or chord")
    candidate = key.strip()
    single = next((value for name, value in _SINGLE_KEYS.items() if name.casefold() == candidate.casefold()), None)
    if single:
        return (single,)
    chord = _CHORDS.get(candidate.casefold())
    if chord:
        return chord
    supported = ", ".join(sorted(SUPPORTED_DESKTOP_KEYS))
    raise ValueError(f"Unsupported desktop key '{candidate}'. Choose one of: {supported}")


def send_key(key: Any, *, pyautogui_module: Any = None) -> None:
    keys = normalize_key(key)
    if pyautogui_module is None:
        try:
            import pyautogui as pyautogui_module
        except ImportError as exc:
            raise RuntimeError("Desktop keyboard actions require the optional PyAutoGUI runtime") from exc
    try:
        if len(keys) == 1:
            pyautogui_module.press(keys[0])
        else:
            pyautogui_module.hotkey(*keys)
    except Exception as exc:
        raise RuntimeError(f"Could not send desktop key action: {type(exc).__name__}: {exc}") from exc


def recordable_key_from_event(event: Any) -> str | None:
    """Return a canonical non-text key step, never the raw key event or text."""
    if getattr(event,"event_type",None)!="key down":
        return None
    aliases={"Return":"Enter","Esc":"Escape","Prior":"PageUp","Next":"PageDown"}
    current=aliases.get(str(getattr(event,"current_key","") or ""),str(getattr(event,"current_key","") or ""))
    pressed=getattr(event,"pressed_key",())
    if isinstance(pressed,str):pressed=(pressed,)
    elif not isinstance(pressed,(list,tuple,set)):pressed=()
    lowered={str(value).casefold() for value in pressed}
    modifiers=[]
    if lowered & {"lcontrol","rcontrol","control","ctrl"}:modifiers.append("Ctrl")
    if lowered & {"lshift","rshift","shift"}:modifiers.append("Shift")
    if lowered & {"lmenu","rmenu","menu","alt"}:modifiers.append("Alt")
    candidate="+".join((*modifiers,current)) if modifiers else current
    normalized="+".join(part.title() for part in candidate.split("+"))
    if candidate.casefold() in _RECORDABLE_CHORDS or (not modifiers and current in _RECORDABLE_SINGLE_KEYS):
        try:
            normalize_key(normalized)
            return normalized
        except ValueError:
            return None
    return None
