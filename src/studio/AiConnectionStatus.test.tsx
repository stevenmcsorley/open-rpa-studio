import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AiConnectionStatus } from './AiConnectionStatus';

describe('AiConnectionStatus', () => {
  it('distinguishes a successful provider check from an empty model list', () => {
    const connected = renderToStaticMarkup(createElement(AiConnectionStatus, { state: { status: 'connected', modelCount: 2, durationMs: 84 } }));
    const empty = renderToStaticMarkup(createElement(AiConnectionStatus, { state: { status: 'empty', durationMs: 51 } }));
    expect(connected).toContain('Connected · 2 models · 84 ms');
    expect(empty).toContain('listed no models');
  });

  it('announces checks and failures accessibly', () => {
    const checking = renderToStaticMarkup(createElement(AiConnectionStatus, { state: { status: 'checking' } }));
    const failed = renderToStaticMarkup(createElement(AiConnectionStatus, { state: { status: 'failed', message: 'Provider request failed with HTTP 401' } }));
    expect(checking).toContain('role="status"');
    expect(failed).toContain('role="alert"');
    expect(failed).toContain('HTTP 401');
  });
});
