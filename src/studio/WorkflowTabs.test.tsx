import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { WorkflowTabs } from './WorkflowTabs';

const render = (tabs: string[], workflows: string[], active: string, live = false) => renderToStaticMarkup(createElement(WorkflowTabs, {
  tabs, workflows, active, live, dirty: name => name === 'Main',
  onSelect: () => {}, onClose: () => {}, onNew: () => {}, onOpen: () => {},
}));

describe('workflow tabs', () => {
  it('shows multiple open workflows with close controls and a create action', () => {
    const html = render(['Main', 'Hello MCP'], ['Main', 'Hello MCP', 'Closed workflow'], 'Hello MCP');
    expect(html).toContain('Main');
    expect(html).toContain('Hello MCP');
    expect(html).toContain('aria-label="Close Hello MCP workflow tab"');
    expect(html).toContain('New workflow');
    expect(html).toContain('Closed workflow');
  });

  it('indicates live updates on the active workflow without a separate preview banner', () => {
    const html = render(['Main', 'Hello MCP'], ['Main', 'Hello MCP'], 'Hello MCP', true);
    expect(html).toContain('Workflow is updating');
    expect(html).not.toContain('preview target');
    expect(html).not.toContain('MCP is building');
  });
});
