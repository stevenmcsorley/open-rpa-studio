import { describe,expect,it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ApiRequestEditor,paginationPatchFromHint } from './ApiRequestEditor';
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
    expect(html).toContain('Maximum mapped output bytes');
    expect(html).toContain('value="5000000"');
    expect(html).toContain('nested objects and arrays');
    expect(html).toContain('customerName');
    expect(html).toContain('/customer/name');
    expect(html).toContain('raw HTTP response remains in its own variable');
  });
  it('renders safe per-record mapping expressions alongside JSON Pointers',()=>{
    const html=renderToStaticMarkup(createElement(ApiRequestEditor,{
      activity:{id:'fetch',type:'api_request',connectionId:'profile',responseMapping:{responseCode:'200',itemsPointer:'/items',fields:[{name:'normalizedStatus',expression:'lower(item["status"])'}],result:'orders',maxItems:500}},
      connections:[],onChange:()=>{},onImportOperation:()=>{}
    }));
    expect(html).toContain('Output field mapping mode 1');
    expect(html).toContain('<option value="pointer">JSON Pointer</option>');
    expect(html).toContain('<option value="expression" selected="">Expression</option>');
    expect(html).toContain('Output field expression 1');
    expect(html).toContain('lower(item[&quot;status&quot;])');
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
  it('offers value-free response field discovery only for an authorized saved GET connection',()=>{
    const disabled=renderToStaticMarkup(createElement(ApiRequestEditor,{activity:{id:'fetch',type:'api_request',method:'GET'},connections:[],onChange:()=>{},onImportOperation:()=>{},desktop:true,allowNetwork:false}));
    const enabled=renderToStaticMarkup(createElement(ApiRequestEditor,{activity:{id:'fetch',type:'api_request',method:'GET',connectionId:'orders'},connections:[{id:'orders',name:'Orders',baseUrl:'https://api.example/v1',authType:'none',apiKeyHeader:'X-API-Key',headers:{},minIntervalSeconds:0,authorizationUrl:'',tokenUrl:'',clientId:'',scope:'',audience:'',clientAuthMethod:'none'}],onChange:()=>{},onImportOperation:()=>{},desktop:true,allowNetwork:true}));
    expect(disabled).toContain('Discover response fields');
    expect(disabled).toContain('disabled=""');
    expect(enabled).toContain('Discover fields');
    expect(enabled).toContain('response values are discarded');
    expect(enabled).toContain('not a guaranteed API schema');
  });
  it('turns a pagination hint into editable bounded settings and reuses a matching query name',()=>{
    const settings=paginationPatchFromHint(
      {itemsPointer:'/data/items',stablePointer:true,observedRows:20,sampledRows:20,fields:[],fieldsTruncated:false},
      {strategy:'cursor',pointer:'/meta/next_cursor',queryParam:'cursor',kind:'cursor',confidence:'heuristic'},
      {after:'old-value'},
      {maxPages:7,result:'orders',metadataResult:'orders',maxItems:500,maxTotalBytes:2500000},
    );
    expect(settings).toMatchObject({strategy:'cursor',itemsPointer:'/data/items',cursorPointer:'/meta/next_cursor',cursorParam:'after',maxPages:7,maxItems:500,maxTotalBytes:2500000,result:'orders',metadataResult:'apiPageInfo'});
    expect(settings).not.toHaveProperty('nextLinkPointer');
  });
  it('turns a next-link hint into bounded pagination without retaining an unrelated cursor',()=>{
    const settings=paginationPatchFromHint(
      {itemsPointer:'/items',stablePointer:true,observedRows:1,sampledRows:1,fields:[],fieldsTruncated:false},
      {strategy:'next_link',pointer:'/links/next',queryParam:'',kind:'next link',confidence:'heuristic'},
      {},
      {cursorPointer:'/meta/cursor',cursorParam:'after',result:'items',metadataResult:'pageInfo'},
    );
    expect(settings).toMatchObject({strategy:'next_link',itemsPointer:'/items',nextLinkPointer:'/links/next',maxPages:10,maxItems:10000,maxTotalBytes:5000000,result:'items',metadataResult:'pageInfo'});
    expect(settings).not.toHaveProperty('cursorPointer');
  });
});
