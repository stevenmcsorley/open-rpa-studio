import { describe, expect, it } from 'vitest';
import type { Workflow } from './types';
import { searchWorkflows } from './workflowSearch';

const base = (values: Partial<Workflow>): Workflow => ({
  format: 'openrpa.workflow', formatVersion: 1, name: 'Main', variables: [], arguments: [], activities: [], ...values,
});

describe('project-wide workflow search', () => {
  it('finds nested activity settings and includes their branch path', () => {
    const workflow = base({ activities: [{ id: 'guard', type: 'if', condition: 'approved', then: [
      { id: 'http-call', type: 'http_request', url: 'https://example.test/orders', method: 'POST' },
    ], else: [] }] });
    const results = searchWorkflows({ Main: workflow }, 'example.test');
    expect(results).toHaveLength(1);
    expect(results[0]).toMatchObject({ targetId: 'http-call', title: 'http_request · http_request', context: 'Sequence / if / then', matchedIn: 'url' });
  });

  it('searches graph conditions, state labels and multiple workflows', () => {
    const flow = base({ executionModel: 'flowchart', flowchart: { start: 'start', nodes: [
      { id: 'start', kind: 'start' }, { id: 'review', kind: 'decision', condition: 'order_total > 1000' }, { id: 'end', kind: 'end' },
    ], transitions: [{ from: 'start', to: 'review' }, { from: 'review', to: 'end', when: 'true' }, { from: 'review', to: 'end', when: 'false' }] } });
    const machine = base({ executionModel: 'state_machine', stateMachine: { initial: 'approve', states: [
      { id: 'approve', label: 'Approve purchase', activities: [] }, { id: 'done', label: 'Complete', final: true, activities: [] },
    ], transitions: [{ from: 'approve', to: 'done', condition: 'is_approved' }] } });
    expect(searchWorkflows({ Orders: flow, Approvals: machine }, '1000')[0]).toMatchObject({ workflowName: 'Orders', targetId: 'review' });
    expect(searchWorkflows({ Orders: flow, Approvals: machine }, 'approve purchase')[0]).toMatchObject({ workflowName: 'Approvals', targetId: 'approve' });
  });

  it('searches switch case labels while keeping each nested action navigable', () => {
    const workflow = base({ activities: [{ id: 'route', type: 'switch', expression: 'region', cases: [
      { value: 'North West', activities: [{ id: 'north', type: 'log', message: 'route north' }] },
    ], default: [] }] });
    expect(searchWorkflows({ Main: workflow }, 'north west')[0]).toMatchObject({ targetId: 'route', matchedIn: 'cases[0]' });
    expect(searchWorkflows({ Main: workflow }, 'route north')[0]).toMatchObject({ targetId: 'north', context: 'Sequence / switch / case 1' });
  });

  it('does not search or expose secret-like fields or variable default values', () => {
    const workflow = base({
      variables: [{ name: 'api_token', type: 'string', value: 'do-not-find-this-secret' }],
      activities: [{ id: 'auth', type: 'http_request', authorization: 'Bearer do-not-find-this-secret', apiKey: 'do-not-find-this-secret', url: 'https://example.test' }],
    });
    expect(searchWorkflows({ Main: workflow }, 'do-not-find-this-secret')).toEqual([]);
  });

  it('requires a two-character query and caps results at 100', () => {
    const activities = Array.from({ length: 120 }, (_, index) => ({ id: `log-${index}`, type: 'log', message: 'repeatable marker' }));
    const workflow = base({ activities });
    expect(searchWorkflows({ Main: workflow }, 'r')).toEqual([]);
    expect(searchWorkflows({ Main: workflow }, 'repeatable')).toHaveLength(100);
  });
});
