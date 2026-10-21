import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ArgumentRow, argumentDefaultError } from './ArgumentRow';

describe('ArgumentRow', () => {
  it('offers optionality and a typed default editor', () => {
    const html = renderToStaticMarkup(createElement(ArgumentRow, {
      value: { name: 'limit', type: 'integer', direction: 'in', required: false, default: 25 },
      onChange: () => undefined,
      onRemove: () => undefined,
    }));
    expect(html).toContain('aria-label="Argument required"');
    expect(html).toContain('aria-label="Argument has default"');
    expect(html).toContain('aria-label="Argument default JSON"');
    expect(html).toContain('aria-label="Argument default JSON" rows="2" spellcheck="false" aria-invalid="false">25</textarea>');
  });

  it('validates JSON values against the declared input type', () => {
    expect(argumentDefaultError(1, 'integer')).toBeNull();
    expect(argumentDefaultError(1.5, 'integer')).toContain('integer');
    expect(argumentDefaultError(Number.POSITIVE_INFINITY, 'number')).toContain('number');
    expect(argumentDefaultError([], 'object')).toContain('object');
    expect(argumentDefaultError({ enabled: true }, 'object')).toBeNull();
    expect(argumentDefaultError('anything', 'any')).toBeNull();
  });
});
