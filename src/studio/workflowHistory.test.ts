import { describe, expect, it } from 'vitest';
import { emptyWorkflowHistory, recordWorkflowChange, redoWorkflowChange, undoWorkflowChange } from './workflowHistory';

describe('workflow undo and redo history', () => {
  it('undoes and redoes edits in order without mutating prior snapshots', () => {
    const original = { activities: ['read'] };
    const edited = { activities: ['read', 'transform'] };
    const secondEdit = { activities: ['read', 'transform', 'write'] };
    let history = recordWorkflowChange(emptyWorkflowHistory<typeof original>(), original);
    history = recordWorkflowChange(history, edited);

    const firstUndo = undoWorkflowChange(history, secondEdit);
    expect(firstUndo?.value).toBe(edited);
    expect(firstUndo?.history.future).toEqual([secondEdit]);

    const secondUndo = undoWorkflowChange(firstUndo!.history, firstUndo!.value);
    expect(secondUndo?.value).toBe(original);
    expect(undoWorkflowChange(secondUndo!.history, secondUndo!.value)).toBeNull();

    const redo = redoWorkflowChange(secondUndo!.history, original);
    expect(redo?.value).toBe(edited);
    expect(redo?.history.past).toEqual([original]);
    expect(redoWorkflowChange(redo!.history, redo!.value)?.value).toBe(secondEdit);
    expect(original.activities).toEqual(['read']);
  });

  it('clears redo after a new edit and enforces the history limit', () => {
    const rows = Array.from({ length: 6 }, (_, value) => value);
    let history = emptyWorkflowHistory<number>();
    for (const row of rows) history = recordWorkflowChange(history, row, 3);
    expect(history.past).toEqual([3, 4, 5]);

    const undone = undoWorkflowChange(history, 6, 3)!;
    expect(undone.value).toBe(5);
    expect(undone.history.future).toEqual([6]);
    expect(recordWorkflowChange(undone.history, 5, 3).future).toEqual([]);
  });
});
