import type { Workflow } from './types';

export type RepairFailure = {
  code: string;
  workflow?: string;
  activityId?: string;
  workflowStack?: { workflow: string; activityId: string; targetWorkflow: string }[];
};

export type DraftValidationProblem = { code: string; activityId?: string };

const SENSITIVE_KEY = /(?:secret|password|token|api.?key|authorization|credential|cookie)/i;

function sanitize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitize);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value as Record<string, unknown>)
    .filter(([key]) => !SENSITIVE_KEY.test(key))
    .map(([key, child]) => [key, sanitize(child)]));
}

/** Build a provider prompt without runtime state, variable values, argument defaults, or error text. */
export function createAiRepairPrompt(workflow: Workflow, failure: RepairFailure): string {
  const definition = structuredClone(workflow);
  definition.variables = definition.variables.map(({ name, type }) => ({ name, type, value: undefined }));
  definition.arguments = definition.arguments.map(({ name, type, direction, required }) => ({ name, type, direction, required }));
  const safeDefinition = sanitize(definition);
  const diagnostic = {
    code: failure.code,
    workflow: failure.workflow,
    activityId: failure.activityId,
    workflowStack: failure.workflowStack,
  };
  return [
    'Repair the workflow definition below so it passes validation and avoids the reported execution failure.',
    'Preserve its intended behavior and use only supported activities. Do not invent credentials or external destinations.',
    'The diagnostic contains identifiers and an error code only; runtime values and error text were intentionally omitted.',
    'Return a complete replacement workflow in the requested schema.',
    `Failure diagnostic:\n${JSON.stringify(diagnostic, null, 2)}`,
    `Workflow definition (configured literals such as paths, URLs, selectors, and strings may be included):\n${JSON.stringify(safeDefinition, null, 2)}`,
  ].join('\n\n');
}

/** Build a bounded repair request from validation codes and activity identifiers only. */
export function createAiDraftRepairPrompt(workflow: Workflow, problems: DraftValidationProblem[]): string {
  const safeProblems = problems.slice(0, 50).map(problem => ({
    code: String(problem.code).slice(0, 100),
    ...(problem.activityId ? { activityId: String(problem.activityId).slice(0, 128) } : {}),
  }));
  const base = createAiRepairPrompt(workflow, {
    code: safeProblems.map(problem => problem.code).join(', ').slice(0, 1000) || 'WORKFLOW_VALIDATION_FAILED',
    activityId: safeProblems.find(problem => problem.activityId)?.activityId,
  });
  return [
    'This is a targeted repair of a generated workflow that failed Studio validation.',
    'Correct the listed validation issues while preserving the requested behavior. Do not add unrelated activities.',
    'Use only the supported workflow schema and activity properties. Return the complete corrected workflow.',
    `Validation issue codes and activity IDs (error messages and runtime values are intentionally excluded):\n${JSON.stringify(safeProblems, null, 2)}`,
    base,
  ].join('\n\n');
}
