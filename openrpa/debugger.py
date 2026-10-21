"""Thread-safe activity-boundary debugger controls for a single workflow run."""
from __future__ import annotations

import threading
import json
from typing import Any, Callable
from .expressions import evaluate


class DebugController:
    """Pause and single-step a workflow without interrupting an active activity.

    Step-over completes the current activity and any nested work before pausing
    at the next boundary. Step-into pauses before the first nested activity when
    the current activity is a container, or after the current activity otherwise.
    External actions are never replayed when resuming.
    """

    def __init__(self, breakpoints: set[str] | None = None, start_paused: bool = True,
                 conditional_breakpoints: dict[str, str] | None = None):
        self.breakpoints = set(breakpoints or ())
        self.conditional_breakpoints = dict(conditional_breakpoints or {})
        self._condition = threading.Condition()
        self._pause_requested = start_paused  # Debug usually starts before the first activity.
        self._paused = False
        self._current_id: str | None = None
        self._current_depth = 0
        self._step_over_depth: int | None = None
        self._step_into_depth: int | None = None
        self._step_out_depth: int | None = None
        self._live_variables: dict[str,Any] | None = None
        self._edit_validator: Callable[[str,Any],None] | None = None
        self._watch_redactor: Callable[[Any],Any] | None = None

    def evaluate_watch(self, expression: str) -> dict[str, Any]:
        """Evaluate a bounded, safe watch against the live scope while paused."""
        if not isinstance(expression, str) or not expression.strip() or len(expression) > 2048:
            raise ValueError("Watch expressions must contain 1–2048 characters")
        with self._condition:
            if not self._paused or self._live_variables is None:
                raise ValueError("Watch expressions can be evaluated only while paused at an activity boundary")
            variables = self._watch_redactor(self._live_variables) if self._watch_redactor else self._live_variables
            try:
                value = evaluate(expression, variables)
                if self._watch_redactor:
                    value = self._watch_redactor(value)
                encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, default=str, separators=(",", ":"))
                if len(encoded.encode("utf-8")) > 16384:
                    preview = encoded[:1024]
                    return {"status": "ok", "type": type(value).__name__, "value": {"truncated": True, "preview": preview}}
                return {"status": "ok", "type": type(value).__name__, "value": value}
            except Exception as exc:
                return {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:512]}

    def set_variable(self, name: str, value: Any) -> dict[str,str]:
        """Edit an existing live value only while stopped at an activity boundary."""
        if not isinstance(name,str) or not name or len(name)>256:
            raise ValueError("Variable name must contain 1–256 characters")
        try:
            encoded=json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(",",":"))
        except (TypeError,ValueError,RecursionError) as exc:
            raise ValueError("Debugger values must be finite JSON data") from exc
        if len(encoded.encode("utf-8"))>65536:
            raise ValueError("Debugger values are limited to 64 KiB")
        with self._condition:
            if not self._paused or self._live_variables is None:
                raise ValueError("Variables can be edited only while paused at an activity boundary")
            if name not in self._live_variables:
                raise ValueError(f"Variable '{name}' is not present in the current workflow scope")
            if self._edit_validator:
                self._edit_validator(name,value)
            self._live_variables[name]=value
            return {"name":name,"type":type(value).__name__}

    @property
    def paused(self) -> bool:
        with self._condition:
            return self._paused

    def pause(self) -> None:
        with self._condition:
            self._pause_requested = True

    def resume(self) -> None:
        with self._condition:
            self._pause_requested = False
            self._step_over_depth = None
            self._step_into_depth = None
            self._step_out_depth = None
            self._paused = False
            self._condition.notify_all()

    def step_over(self) -> None:
        with self._condition:
            if not self._paused:
                raise ValueError("Step controls are available only while the debugger is paused")
            self._step_over_depth = self._current_depth
            self._step_into_depth = None
            self._step_out_depth = None
            self._pause_requested = False
            self._paused = False
            self._condition.notify_all()

    def step_into(self) -> None:
        with self._condition:
            if not self._paused:
                raise ValueError("Step controls are available only while the debugger is paused")
            self._step_into_depth = self._current_depth + 1
            self._step_over_depth = None
            self._step_out_depth = None
            self._pause_requested = False
            self._paused = False
            self._condition.notify_all()

    def step_out(self) -> None:
        with self._condition:
            if not self._paused:
                raise ValueError("Step controls are available only while the debugger is paused")
            self._step_out_depth=max(0,self._current_depth-1)
            self._step_over_depth=None
            self._step_into_depth=None
            self._pause_requested=False
            self._paused=False
            self._condition.notify_all()

    def wake_for_cancel(self) -> None:
        with self._condition:
            self._paused = False
            self._condition.notify_all()

    def before_activity(self, activity_id: str, depth: int, variables: dict[str, Any], cancelled: Callable[[], bool], emit: Callable[[dict[str, Any]], None],
                        snapshot: Callable[[dict[str,Any]],dict[str,Any]] | None = None,
                        editable: Callable[[dict[str,Any]],list[str]] | None = None,
                        validate_edit: Callable[[str,Any],None] | None = None,
                        redact: Callable[[Any],Any] | None = None) -> None:
        with self._condition:
            self._current_id = activity_id
            self._current_depth = depth
            self._live_variables=variables
            self._edit_validator=validate_edit
            self._watch_redactor=redact
            step_into = self._step_into_depth is not None and depth >= self._step_into_depth
            if step_into:
                self._step_into_depth = None
                self._pause_requested = True
            if self._step_over_depth is not None and depth <= self._step_over_depth:
                # A fallback for empty branches or leaf activities.
                self._step_over_depth = None
                self._pause_requested = True
            if self._step_out_depth is not None and depth <= self._step_out_depth:
                self._step_out_depth=None
                self._pause_requested=True
            stop = self._pause_requested or activity_id in self.breakpoints
            breakpoint_error = None
            condition = self.conditional_breakpoints.get(activity_id)
            if condition:
                try:
                    outcome = evaluate(condition, variables)
                    if type(outcome) is not bool:
                        raise ValueError("Breakpoint condition must evaluate to true or false")
                    stop = stop or outcome
                except Exception as exc:
                    # Fail closed: pause so a typo cannot silently skip a breakpoint.
                    stop = True
                    breakpoint_error = f"{type(exc).__name__}: {exc}"[:512]
            if not stop:
                return
            self._pause_requested = False
            self._paused = True
            visible=snapshot(variables) if snapshot else variables
            event={"event":"debug.paused","activityId":activity_id,"depth":depth,"variables":visible}
            if breakpoint_error: event["breakpointError"] = breakpoint_error
            if editable: event["editableVariables"]=editable(variables)
            emit(event)
            while self._paused and not cancelled():
                self._condition.wait(timeout=0.1)
            if cancelled():
                self._live_variables=None
                self._edit_validator=None
                self._watch_redactor=None
                return
            emit({"event":"debug.resumed","activityId":activity_id,"depth":depth})
            self._live_variables=None
            self._edit_validator=None
            self._watch_redactor=None

    def after_activity(self, activity_id: str, depth: int) -> None:
        with self._condition:
            if self._step_over_depth is not None and depth == self._step_over_depth:
                self._step_over_depth = None
                self._pause_requested = True
            elif self._step_into_depth is not None and depth <= self._current_depth:
                # No nested activity was entered (e.g. an empty branch).
                self._step_into_depth = None
                self._pause_requested = True
            elif self._step_out_depth is not None and depth <= self._step_out_depth:
                self._step_out_depth=None
                self._pause_requested=True

