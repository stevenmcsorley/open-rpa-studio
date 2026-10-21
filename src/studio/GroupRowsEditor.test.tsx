import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { GroupRowsEditor } from './GroupRowsEditor';

describe('GroupRowsEditor',()=>{
  it('shows group fields and configurable aggregation rows',()=>{
    const html=renderToStaticMarkup(createElement(GroupRowsEditor,{activity:{id:'group',type:'group_rows',rows:'orders',groupBy:['department','region'],aggregations:[{field:'amount',operation:'sum',as:'total'},{operation:'count_rows',as:'records'}],maxGroups:25000,result:'summary'},onChange:()=>undefined}));
    expect(html).toContain('aria-label="Rows source"');expect(html).toContain('value="orders"');expect(html).toContain('aria-label="New group field"');expect(html).toContain('department');expect(html).toContain('aria-label="Aggregation 1 operation"');expect(html).toContain('Average');expect(html).toContain('aria-label="Aggregation 2 output field"');expect(html).toContain('Maximum groups');expect(html).toContain('Sum and average require finite numeric values');
  });
});
