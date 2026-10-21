import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,expect,it} from 'vitest';
import {AiUsageSummary} from './AiUsageSummary';

describe('AI usage summary',()=>{
  it('displays provider-reported token counts without implying a price',()=>{
    const html=renderToStaticMarkup(createElement(AiUsageSummary,{usage:{inputTokens:1234,outputTokens:56,totalTokens:1290}}));
    expect(html).toContain('input 1,234 · output 56 · total 1,290');
    expect(html).toContain('Monetary cost is not estimated');
  });
  it('explains when the provider gives no usage data',()=>{
    const html=renderToStaticMarkup(createElement(AiUsageSummary,{}));
    expect(html).toContain('did not report token usage');
  });
});
