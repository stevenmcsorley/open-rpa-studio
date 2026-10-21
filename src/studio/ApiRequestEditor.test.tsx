import { describe,expect,it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ApiRequestEditor } from './ApiRequestEditor';

describe('API Request response mapping editor',()=>{
  it('renders editable pointers, output fields, and row limits for a configured mapping',()=>{
    const html=renderToStaticMarkup(createElement(ApiRequestEditor,{
      activity:{id:'fetch',type:'api_request',connectionId:'profile',responseMapping:{responseCode:'200',itemsPointer:'/data/items',fields:[{name:'orderId',path:'/id'},{name:'customerName',path:'/customer/name'}],result:'orders',maxItems:500}},
      connections:[],onChange:()=>{},onImportOperation:()=>{}
    }));
    expect(html).toContain('JSON response mapping');
    expect(html).toContain('Array JSON Pointer');
    expect(html).toContain('/data/items');
    expect(html).toContain('Mapped rows result variable');
    expect(html).toContain('Maximum mapped response rows');
    expect(html).toContain('customerName');
    expect(html).toContain('/customer/name');
    expect(html).toContain('raw HTTP response remains in its own variable');
  });
});
