import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DistinctRowsEditor } from './DistinctRowsEditor';

describe('DistinctRowsEditor',()=>{
  it('shows key, keep-order and bounded output settings',()=>{
    const html=renderToStaticMarkup(createElement(DistinctRowsEditor,{activity:{id:'distinct',type:'distinct_rows',rows:'records',keys:['buyer_id','supplier_id'],keep:'last',maxRows:5000,result:'uniqueRecords'},onChange:()=>undefined}));
    expect(html).toContain('DUPLICATE KEYS');expect(html).toContain('buyer_id');expect(html).toContain('supplier_id');expect(html).toContain('last');expect(html).toContain('5000');expect(html).toContain('uniqueRecords');
  });
});
