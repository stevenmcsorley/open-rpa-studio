import { describe,expect,it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ApiRequestEditor } from './ApiRequestEditor';
import { ApiConnectionsDialog } from './ApiConnectionsDialog';

describe('API Request response mapping editor',()=>{
  it('uses visual query and header rows and reserves credential headers for the connection vault',()=>{
    const html=renderToStaticMarkup(createElement(ApiRequestEditor,{
      activity:{id:'fetch',type:'api_request',query:{page:'{{ currentPage }}',limit:100},headers:{Accept:'application/json'}},
      connections:[],onChange:()=>{},onImportOperation:()=>{}
    }));
    expect(html).toContain('QUERY PARAMETERS');
    expect(html).toContain('aria-label="Query parameter 1 name"');
    expect(html).toContain('value="{{ currentPage }}"');
    expect(html).toContain('Add query parameter');
    expect(html).toContain('REQUEST HEADERS');
    expect(html).toContain('aria-label="Header 1 name"');
    expect(html).toContain('value="application/json"');
    expect(html).toContain('Authentication and credential headers are managed by the saved connection');
    expect(html).not.toContain('API query parameters JSON');
    expect(html).not.toContain('Request headers · JSON object');
  });

  it('uses the same visual editor for reusable connection headers',()=>{
    const html=renderToStaticMarkup(createElement(ApiConnectionsDialog,{profiles:[],onProfiles:()=>{},onClose:()=>{},allowNetwork:false}));
    expect(html).toContain('REQUEST HEADERS');
    expect(html).toContain('Add header');
    expect(html).toContain('Authentication and credential headers are managed by the saved connection');
    expect(html).not.toContain('API shared headers JSON');
  });

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
  it('renders cursor and next-link pagination controls with explicit bounds',()=>{
    const html=renderToStaticMarkup(createElement(ApiRequestEditor,{
      activity:{id:'fetch',type:'api_request',connectionId:'profile',method:'GET',pagination:{strategy:'cursor',itemsPointer:'/data/items',cursorPointer:'/meta/next',cursorParam:'after',maxPages:8,maxItems:3000,maxTotalBytes:2000000,result:'orders',metadataResult:'pageInfo'}},
      connections:[],onChange:()=>{},onImportOperation:()=>{}
    }));
    expect(html).toContain('Authenticated pagination');
    expect(html).toContain('Cursor parameter');
    expect(html).toContain('/meta/next');
    expect(html).toContain('Maximum API pages');
    expect(html).toContain('Total byte cap');
    expect(html).toContain('pageInfo');
  });
  it('renders combined pagination and projection outputs without implying the two are exclusive',()=>{
    const html=renderToStaticMarkup(createElement(ApiRequestEditor,{
      activity:{id:'fetch',type:'api_request',connectionId:'profile',method:'GET',pagination:{strategy:'cursor',itemsPointer:'/data/items',cursorPointer:'/meta/next',cursorParam:'after',maxPages:8,maxItems:3000,maxTotalBytes:2000000,result:'rawOrders',metadataResult:'pageInfo'},responseMapping:{responseCode:'200',itemsPointer:'/data/items',fields:[{name:'orderId',path:'/id'}],result:'orders',maxItems:500}},
      connections:[],onChange:()=>{},onImportOperation:()=>{}
    }));
    expect(html).toContain('Paginated record mapping');
    expect(html).toContain('disabled="" value="/data/items"');
    expect(html).toContain('Projected fields are gathered across every page');
    expect(html).not.toContain('cannot be combined with JSON response mapping');
  });
  it('offers URL based OpenAPI discovery only with desktop network permission',()=>{
    const disconnected=renderToStaticMarkup(createElement(ApiRequestEditor,{activity:{id:'fetch',type:'api_request'},connections:[],onChange:()=>{},onImportOperation:()=>{},desktop:true,allowNetwork:false}));
    const enabled=renderToStaticMarkup(createElement(ApiRequestEditor,{activity:{id:'fetch',type:'api_request'},connections:[],onChange:()=>{},onImportOperation:()=>{},desktop:true,allowNetwork:true}));
    expect(disconnected).toContain('OpenAPI specification URL');
    expect(disconnected).toContain('disabled=""');
    expect(disconnected).toContain('requires Allow network');
    expect(enabled).toContain('Fetch OpenAPI');
    expect(enabled).toContain('no redirects');
  });
});
