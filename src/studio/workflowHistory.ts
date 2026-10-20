export type WorkflowHistory<T> = { past: T[]; future: T[] };
export const emptyWorkflowHistory = <T>(): WorkflowHistory<T> => ({ past: [], future: [] });

/** Record one immutable workflow edit, keeping a bounded undo stack. */
export function recordWorkflowChange<T>(history: WorkflowHistory<T>, current: T, limit = 100): WorkflowHistory<T> {
  const boundedLimit = Math.max(1, Math.floor(limit));
  return { past: [...history.past, current].slice(-boundedLimit), future: [] };
}

/** Move the current value to the redo stack and return the preceding snapshot. */
export function undoWorkflowChange<T>(history: WorkflowHistory<T>, current: T, limit = 100): { history: WorkflowHistory<T>; value: T } | null {
  if (!history.past.length) return null;
  const boundedLimit = Math.max(1, Math.floor(limit));
  return {
    history: { past: history.past.slice(0, -1), future: [current, ...history.future].slice(0, boundedLimit) },
    value: history.past[history.past.length - 1],
  };
}

/** Reapply the most recently undone value. */
export function redoWorkflowChange<T>(history: WorkflowHistory<T>, current: T, limit = 100): { history: WorkflowHistory<T>; value: T } | null {
  if (!history.future.length) return null;
  const boundedLimit = Math.max(1, Math.floor(limit));
  return {
    history: { past: [...history.past, current].slice(-boundedLimit), future: history.future.slice(1) },
    value: history.future[0],
  };
}
