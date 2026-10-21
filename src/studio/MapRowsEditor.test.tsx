import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { MapRowsEditor } from './MapRowsEditor';

describe('MapRowsEditor',()=>{
  it('shows projected mappings, safe expression guidance and result limits',()=>{
    const html=renderToStaticMarkup(createElement(MapRowsEditor,{activity:{id:'map',type:'map_rows',rows:'orders',mappings:[{field:'label',expression:'upper(row.name)'}],maxRows:2500,result:'labels'},onChange:()=>undefined}));
    expect(html).toContain('Map Rows settings');expect(html).toContain('upper(row.name)');expect(html).toContain('rowIndex');expect(html).toContain('2500');expect(html).toContain('labels');
  });
});
