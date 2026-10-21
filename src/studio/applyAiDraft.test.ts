import { describe, expect, it } from 'vitest';
import type { Project, Workflow } from './types';
import { addAiDraftWorkflow } from './applyAiDraft';

const project: Project = {
  format: 'openrpa.project', formatVersion: 1, name: 'Example', main: 'Main',
  workflows: { Main: 'workflows/main.workflow.json', 'AI Draft': 'workflows/custom-ai-draft.workflow.json' },
};
const main: Workflow = {
  format: 'openrpa.workflow', formatVersion: 1, name: 'Main', variables: [], arguments: [],
  activities: [{ id: 'existing', type: 'log', message: 'keep this' }],
};
const draft: Workflow = {
  format: 'openrpa.workflow', formatVersion: 1, name: 'AI Draft', variables: [], arguments: [],
  activities: [{ id: 'generated', type: 'log', message: 'new workflow' }],
};

describe('addAiDraftWorkflow', () => {
  it('creates a uniquely named workflow without changing existing project entries', () => {
    const result = addAiDraftWorkflow(project, { Main: main, 'AI Draft': draft }, draft);
    expect(result.name).toBe('AI Draft 2');
    expect(result.project.workflows['AI Draft 2']).toBe('workflows/ai-draft-2.workflow.json');
    expect(result.workflows.Main).toBe(main);
    expect(result.workflows['AI Draft'].activities[0].id).toBe('generated');
    expect(result.workflow.name).toBe('AI Draft 2');
    expect(result.workflow.activities[0].message).toBe('new workflow');
    expect(result.blankWorkflow.activities).toEqual([]);
    expect(project.workflows).toEqual({ Main: 'workflows/main.workflow.json', 'AI Draft': 'workflows/custom-ai-draft.workflow.json' });
  });

  it('avoids a path collision and a reserved live-draft tab name', () => {
    const withCollision = { ...project, workflows: { ...project.workflows, 'AI Draft 2': 'workflows/ai-draft-3.workflow.json' } };
    const result = addAiDraftWorkflow(withCollision, { Main: main, 'AI Draft': draft }, draft, ['AI Draft 2']);
    expect(result.name).toBe('AI Draft 4');
    expect(result.project.workflows[result.name]).toBe('workflows/ai-draft-4.workflow.json');
  });
});
