import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { AiModelPicker } from './AiModelPicker';

describe('AiModelPicker',()=>{
  it('offers discovered models while allowing an exact model ID to be entered',()=>{
    const html=renderToStaticMarkup(createElement(AiModelPicker,{models:['local/qwen','openai/gpt-model'],value:'custom/model-v2',onChange:vi.fn()}));
    expect(html).toContain('aria-label="Model identifier"');
    expect(html).toContain('value="custom/model-v2"');
    expect(html).toContain('<option value="local/qwen"></option>');
    expect(html).toContain('<option value="openai/gpt-model"></option>');
    expect(html).toContain('catalogue is unavailable or filtered');
  });

  it('keeps a saved model usable when the provider returns no catalogue',()=>{
    const html=renderToStaticMarkup(createElement(AiModelPicker,{models:[],value:'tenant-model-2026',onChange:vi.fn()}));
    expect(html).toContain('value="tenant-model-2026"');
    expect(html).toContain('Enter the exact model ID exposed by this endpoint');
  });
});
