import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { AiDraftEvent } from './bridge';
import { AiDraftActivityMonitor } from './AiDraftActivityMonitor';

const event = (type: string, metadata: Record<string, unknown> = {}, phase = 'generating'): AiDraftEvent => ({
  requestId: 'draft-1', type, timestamp: 1_797_000_000_000, phase, metadata,
});

function render(events: AiDraftEvent[], busy = true) {
  return renderToStaticMarkup(createElement(AiDraftActivityMonitor, {
    events, busy, provider: 'deepseek', model: 'deepseek-chat', executionModel: 'sequence',
    elapsedSeconds: 4, firstOutputMs: 1200, outputText: '{"activities":[]}',
  }));
}

describe('AI workflow build monitor', () => {
  it('shows real lifecycle milestones and explains why no activity is visible yet', () => {
    const html = render([event('request.preparing'), event('provider.connecting'), event('generation.started'), event('model.capabilities_checked', { streaming: 'supported' })]);
    expect(html).toContain('WORKFLOW BUILD');
    expect(html).toContain('Prepare');
    expect(html).toContain('Generate');
    expect(html).toContain('Waiting for the first complete activity');
    expect(html).toContain('0 chars');
  });

  it('animates a discovered activity while its validation state is visible', () => {
    const html = render([
      event('workflow.activity_discovered', { activityId: 'read-1', activityType: 'CSV Read' }, 'validating'),
      event('workflow.activity_validated', { activityId: 'read-1', activityType: 'CSV Read', activity: { id: 'read-1', type: 'csv_read' } }, 'validating'),
    ]);
    expect(html).toContain('node-valid');
    expect(html).toContain('CSV Read');
    expect(html).toContain('Inspect configured step');
    expect(html).toContain('sequence-building');
  });

  it('surfaces invalid activities when final validation fails', () => {
    const html = render([
      event('workflow.validation_failed', { activityId: 'if-1', activityType: 'If', problems: [{ code: 'expression', message: 'Invalid condition' }] }, 'validation'),
    ], false);
    expect(html).toContain('node-invalid');
    expect(html).toContain('Needs attention');
    expect(html).toContain('Invalid condition');
  });

  it('marks the final build validated when the complete workflow passes', () => {
    const html = render([event('workflow.completed', { activityCount: 1, valid: true }, 'complete')], false);
    expect(html).toContain('Validated');
    expect(html).toContain('Workflow is valid');
  });
});
