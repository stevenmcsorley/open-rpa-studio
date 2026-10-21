import type { Activity, Workflow } from './types';

export type WorkflowSearchResult = {
  workflowName: string;
  targetId: string;
  title: string;
  context: string;
  matchedIn: string;
  preview: string;
};

const SECRET_FIELD = /password|secret|token|credential|authorization|cookie|api.?key/i;
const CONTROL_FIELDS = new Set(['then', 'else', 'body', 'catch', 'finally', 'cases', 'default']);
const MAX_RESULTS = 100;

function values(value: unknown, path: string, query: string, depth = 0): { field: string; text: string }[] {
  if (depth > 8 || SECRET_FIELD.test(path.split('.').at(-1) ?? '')) return [];
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    const text = String(value);
    return text.toLowerCase().includes(query) ? [{ field: path, text }] : [];
  }
  if (Array.isArray(value)) return value.flatMap((item, index) => values(item, `${path}[${index}]`, query, depth + 1));
  if (!value || typeof value !== 'object') return [];
  return Object.entries(value).flatMap(([key, item]) => SECRET_FIELD.test(key) ? [] : values(item, path ? `${path}.${key}` : key, query, depth + 1));
}

export function searchWorkflows(workflows: Record<string, Workflow>, rawQuery: string, limit = MAX_RESULTS): WorkflowSearchResult[] {
  const query = rawQuery.trim().toLowerCase();
  if (query.length < 2) return [];
  const resultLimit = Math.min(Math.max(limit, 1), MAX_RESULTS);
  const results: WorkflowSearchResult[] = [];
  const add = (workflowName: string, targetId: string, title: string, context: string, fields: Record<string, unknown>) => {
    if (results.length >= resultLimit) return;
    const matches = values(fields, '', query);
    if (!matches.length) return;
    const first = matches[0];
    results.push({ workflowName, targetId, title, context, matchedIn: first.field || 'text', preview: first.text.replace(/\s+/g, ' ').slice(0, 180) });
  };

  const walk = (workflowName: string, items: Activity[], parent: string) => {
    if (results.length >= resultLimit) return;
    for (const activity of items) {
      if (results.length >= resultLimit) return;
      const label = String(activity.label ?? activity.type ?? 'Activity');
      const title = `${label} · ${activity.type}`;
      const context = parent || 'Sequence';
      const fields: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(activity)) if (!CONTROL_FIELDS.has(key)) fields[key] = value;
      if (activity.type === 'switch' && Array.isArray(activity.cases))
        fields.cases = activity.cases.map(entry => entry && typeof entry === 'object' ? (entry as Record<string, unknown>).value : undefined);
      add(workflowName, activity.id, title, context, fields);
      for (const branch of ['then', 'else', 'body', 'catch', 'finally'] as const) {
        const children = activity[branch];
        if (Array.isArray(children)) walk(workflowName, children as Activity[], `${context} / ${label} / ${branch}`);
      }
      if (activity.type === 'switch' && Array.isArray(activity.cases)) {
        activity.cases.forEach((entry, index) => {
          if (results.length >= resultLimit) return;
          if (entry && typeof entry === 'object' && Array.isArray(entry.activities))
            walk(workflowName, entry.activities as Activity[], `${context} / ${label} / case ${index + 1}`);
        });
      }
      if (Array.isArray(activity.default)) walk(workflowName, activity.default as Activity[], `${context} / ${label} / default`);
    }
  };

  for (const [workflowName, workflow] of Object.entries(workflows)) {
    if (results.length >= resultLimit) break;
    add(workflowName, '', `Workflow · ${workflow.name}`, 'Project', { name: workflow.name, executionModel: workflow.executionModel ?? 'sequence' });
    add(workflowName, '', 'Variables and arguments', 'Project configuration', {
      variables: workflow.variables.map(({ name, type }) => ({ name, type })),
      arguments: workflow.arguments.map(({ name, type, direction }) => ({ name, type, direction })),
    });
    if (workflow.executionModel === 'flowchart' && workflow.flowchart) {
      for (const node of workflow.flowchart.nodes) {
        if (results.length >= resultLimit) break;
        if (node.kind === 'action' && node.activity) {
          add(workflowName, node.activity.id, `${node.label ?? node.activity.label ?? node.activity.type} · ${node.activity.type}`, `Flowchart node ${node.id}`, { id: node.id, label: node.label, kind: node.kind });
          walk(workflowName, [node.activity], `Flowchart node ${node.id}`);
        } else add(workflowName, node.id, `${node.label ?? node.kind} · ${node.kind}`, 'Flowchart', node as unknown as Record<string, unknown>);
      }
      for (const edge of workflow.flowchart.transitions) {
        if (results.length >= resultLimit) break;
        add(workflowName, edge.from, `Transition · ${edge.from} → ${edge.to}`, 'Flowchart', edge as unknown as Record<string, unknown>);
      }
    } else if (workflow.executionModel === 'state_machine' && workflow.stateMachine) {
      for (const state of workflow.stateMachine.states) {
        if (results.length >= resultLimit) break;
        add(workflowName, state.id, `State · ${state.label}`, 'State machine', state as unknown as Record<string, unknown>);
        walk(workflowName, state.activities, `State ${state.label}`);
      }
      for (const edge of workflow.stateMachine.transitions) {
        if (results.length >= resultLimit) break;
        add(workflowName, edge.from, `Transition · ${edge.from} → ${edge.to}`, 'State machine', edge as unknown as Record<string, unknown>);
      }
    } else walk(workflowName, workflow.activities, 'Sequence');
    if (results.length >= resultLimit) break;
  }
  return results;
}
