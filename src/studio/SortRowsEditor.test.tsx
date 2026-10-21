import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SortRowsEditor } from './SortRowsEditor';

describe('SortRowsEditor',()=>{
  it('shows ordered typed keys, null placement and limits',()=>{
    const html=renderToStaticMarkup(createElement(SortRowsEditor,{activity:{id:'sort',type:'sort_rows',rows:'orders',keys:[{field:'date',direction:'descending',nulls:'first'}],maxRows:1200,result:'ordered'},onChange:()=>undefined}));
    expect(html).toContain('aria-label="Sort key 1 field"');expect(html).toContain('Descending');expect(html).toContain('Nulls');expect(html).toContain('Ties keep their original order');expect(html).toContain('Maximum input rows');expect(html).toContain('value="ordered"');
  });
});
