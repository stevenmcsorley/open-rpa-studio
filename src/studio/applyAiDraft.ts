import type { Project, Workflow } from './types';

export type AiDraftInsertion = {
  project: Project;
  workflows: Record<string, Workflow>;
  workflow: Workflow;
  blankWorkflow: Workflow;
  name: string;
};

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'workflow';
}

/** Add an AI result as a separate workflow while preserving every existing workflow. */
export function addAiDraftWorkflow(
  project: Project,
  workflows: Record<string, Workflow>,
  draft: Workflow,
  reservedNames: string[] = [],
): AiDraftInsertion {
  const names = new Set([...Object.keys(workflows), ...reservedNames]);
  const paths = new Set(Object.values(project.workflows));
  let name = 'AI Draft';
  let index = 2;
  while (names.has(name)) name = `AI Draft ${index++}`;

  let path = `workflows/${slug(name)}.workflow.json`;
  while (paths.has(path)) {
    name = `AI Draft ${index++}`;
    path = `workflows/${slug(name)}.workflow.json`;
  }

  const workflow = structuredClone({ ...draft, name });
  const blankWorkflow: Workflow = {
    format: 'openrpa.workflow', formatVersion: 1, name,
    variables: [], arguments: [], activities: [],
  };
  return {
    name,
    workflow,
    blankWorkflow,
    project: { ...project, workflows: { ...project.workflows, [name]: path } },
    workflows: { ...workflows, [name]: workflow },
  };
}
