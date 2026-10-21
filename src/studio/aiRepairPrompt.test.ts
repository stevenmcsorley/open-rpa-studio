import { describe, expect, it } from 'vitest';
import { createAiRepairPrompt } from './aiRepairPrompt';
import type { Workflow } from './types';

const workflow: Workflow = {
  format: 'openrpa.workflow', formatVersion: 1, name: 'Import',
  variables: [{ name: 'rows', type: 'table', value: [{ customer: 'PRIVATE ROW' }] }],
  arguments: [{ name: 'apiToken', type: 'string', direction: 'in', default: 'PRIVATE DEFAULT' }],
  activities: [{ id: 'http-1', type: 'http_request', url: 'https://example.test', apiToken: 'PRIVATE TOKEN', body: 'configured literal' }],
};

describe('createAiRepairPrompt', () => {
  it('includes only identifiers and codes from failure diagnostics', () => {
    const prompt = createAiRepairPrompt(workflow, { code: 'HTTP_TIMEOUT', workflow: 'Import', activityId: 'http-1', workflowStack: [{ workflow: 'Main', activityId: 'call-1', targetWorkflow: 'Import' }] });
    expect(prompt).toContain('HTTP_TIMEOUT');
    expect(prompt).toContain('http-1');
    expect(prompt).not.toContain('PRIVATE ROW');
    expect(prompt).not.toContain('PRIVATE DEFAULT');
    expect(prompt).not.toContain('PRIVATE TOKEN');
  });

  it('keeps operational configuration and warns it may be sent to the provider', () => {
    const prompt = createAiRepairPrompt(workflow, { code: 'FILE_NOT_FOUND' });
    expect(prompt).toContain('https://example.test');
    expect(prompt).toContain('configured literal');
    expect(prompt).toContain('may be included');
  });

  it('does not mutate the source workflow', () => {
    const before = structuredClone(workflow);
    createAiRepairPrompt(workflow, { code: 'FAILED' });
    expect(workflow).toEqual(before);
  });
});
