import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FilterRowsEditor } from './FilterRowsEditor';

describe('FilterRowsEditor',()=>{
  it('renders typed rules, combination mode and values as editable controls',()=>{
    const html=renderToStaticMarkup(createElement(FilterRowsEditor,{activity:{id:'filter',type:'filter_rows',rows:'orders',result:'openOrders',match:'any',conditions:[
      {field:'status',operator:'equals',value:'open',ignoreCase:true},
      {field:'total',operator:'greater_or_equal',value:25000},
      {field:'tags',operator:'is_empty'},
    ]},onChange:()=>undefined}));
    expect(html).toContain('aria-label="Rows source"');
    expect(html).toContain('value="orders"');
    expect(html).toContain('aria-label="Condition matching mode"');
    expect(html).toContain('Any (OR)');
    expect(html).toContain('aria-label="Condition 1 JSON value"');
    expect(html).toContain('&quot;open&quot;');
    expect(html).toContain('25000');
    expect(html).toContain('Add condition');
    expect(html.match(/aria-label="Remove condition/g)).toHaveLength(3);
  });
});
