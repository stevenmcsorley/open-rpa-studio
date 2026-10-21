import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { JoinRowsEditor } from './JoinRowsEditor';

describe('JoinRowsEditor',()=>{
  it('exposes join inputs, keys, join mode and safety limit',()=>{
    const html=renderToStaticMarkup(createElement(JoinRowsEditor,{activity:{id:'join',type:'join_rows',left:'orders',right:'buyers',leftKey:'buyerId',rightKey:'id',joinType:'left',rightPrefix:'buyer_',maxRows:25000,result:'enriched'},onChange:()=>undefined}));
    expect(html).toContain('aria-label="Left rows"');expect(html).toContain('value="orders"');expect(html).toContain('aria-label="Right key"');expect(html).toContain('Left: keep every left record');expect(html).toContain('aria-label="Output row limit"');expect(html).toContain('Duplicate keys produce one output row per match');
  });
});
