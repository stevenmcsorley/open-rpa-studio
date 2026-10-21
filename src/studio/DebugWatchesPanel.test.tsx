import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DebugWatchesPanel } from './DebugWatchesPanel';

describe('DebugWatchesPanel',()=>{
  it('renders safe watch results and updates only while paused',()=>{
    const html=renderToStaticMarkup(createElement(DebugWatchesPanel,{expressions:['len(rows)','denied()'],results:{'len(rows)':{status:'ok',type:'int',value:4},'denied()':{status:'error',error:'ExpressionError: not allowed'}},paused:true,onAdd:()=>undefined,onRemove:()=>undefined}));
    expect(html).toContain('len(rows)');expect(html).toContain('4');expect(html).toContain('ExpressionError: not allowed');
    expect(html).toContain('safe workflow expression language');
  });

  it('disables adding expressions while running and announces the pause requirement',()=>{
    const html=renderToStaticMarkup(createElement(DebugWatchesPanel,{expressions:['count'],results:{},paused:false,onAdd:()=>undefined,onRemove:()=>undefined}));
    expect(html).toContain('Pause the debugger to inspect values');
    expect(html).toContain('disabled=""');
  });
});
