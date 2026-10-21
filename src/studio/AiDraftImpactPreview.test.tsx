import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { buildExecutionPlan } from './executionPlan';
import { AiDraftImpactPreview } from './AiDraftImpactPreview';
import type { Workflow } from './types';

const base: Workflow = { format: 'openrpa.workflow', formatVersion: 1, name: 'AI Draft', variables: [], arguments: [], activities: [] };

describe('AI draft impact preview', () => {
  it('shows permission needs and configured external targets before insertion', () => {
    const plan = buildExecutionPlan({ ...base, activities: [
      { id: 'fetch', type: 'api_request', connectionId: 'bank-profile', method: 'GET', path: '/portfolio' },
      { id: 'remove', type: 'file_delete', path: 'old.csv' },
      { id: 'desktop', type: 'desktop_ui_click', windowTitle: 'Ledger', selector: 'Save' },
    ] });
    const html = renderToStaticMarkup(<AiDraftImpactPreview plan={plan}/>);
    expect(plan).toMatchObject({ needsNetwork: true, needsDesktop: true, hasDestructiveActions: true });
    expect(html).toContain('Network required');
    expect(html).toContain('Desktop control required');
    expect(html).toContain('Destructive actions');
    expect(html).toContain('GET bank-profile /portfolio');
    expect(html).toContain('old.csv');
    expect(html).toContain('Configured targets');
  });

  it('states when the draft contains only local workflow logic', () => {
    const plan = buildExecutionPlan({ ...base, activities: [{ id: 'log', type: 'log', message: 'hello' }] });
    const html = renderToStaticMarkup(<AiDraftImpactPreview plan={plan}/>);
    expect(html).toContain('No network');
    expect(html).toContain('No desktop control');
    expect(html).toContain('No file, network, browser, credential, or desktop effects identified.');
  });
});
