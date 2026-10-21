import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,expect,it} from 'vitest';
import {BrowserResponseEditor} from './BrowserResponseEditor';

describe('browser response editor',()=>{
  it('shows metadata-only response matching controls with an optional status filter',()=>{
    const html=renderToStaticMarkup(createElement(BrowserResponseEditor,{activity:{id:'wait',type:'browser_wait_response',urlContains:'/api/orders',method:'get',status:null,maxAgeSeconds:30,timeoutSeconds:15,result:'response'},onChange:()=>{}}));
    expect(html).toContain('URL path contains');
    expect(html).toContain('Request method');
    expect(html).toContain('Accept responses from the last');
    expect(html).toContain('Without mapping, only method, status, and content type are returned.');
    expect(html).toContain('Query strings and fragments are never stored.');
    expect(html).not.toContain('Expected response status');
  });

  it('exposes an input when a response status is configured',()=>{
    const html=renderToStaticMarkup(createElement(BrowserResponseEditor,{activity:{id:'wait',type:'browser_wait_response',urlContains:'/api/orders',method:'get',status:201,result:'response'},onChange:()=>{}}));
    expect(html).toContain('Expected response status');
    expect(html).toContain('value="201"');
  });

  it('offers opt-in bounded scalar mapping without displaying response bodies',()=>{
    const html=renderToStaticMarkup(createElement(BrowserResponseEditor,{activity:{id:'wait',type:'browser_wait_response',urlContains:'/api/orders',maxResponseBytes:100000,jsonMapping:{itemsPointer:'/data/items',result:'orders',maxItems:100,fields:[{name:'id',path:'/id'},{name:'title',path:'/title'}]}},onChange:()=>{}}));
    expect(html).toContain('Bounded JSON field mapping');
    expect(html).toContain('value="/data/items"');
    expect(html).toContain('value="orders"');
    expect(html).toContain('Browser response maximum bytes');
    expect(html).toContain('Browser response field 2 pointer');
    expect(html).toContain('Only selected scalar fields enter the mapped result');
    expect(html).toContain('may be saved in run history');
    expect(html).not.toContain('Response bodies, query strings, and fragments are never captured.');
  });

  it('offers value-free schema discovery as a separate opt-in mode',()=>{
    const html=renderToStaticMarkup(createElement(BrowserResponseEditor,{activity:{id:'wait',type:'browser_wait_response',urlContains:'/api/orders',discoverJsonSchema:true,schemaResult:'shape'},onChange:()=>{}}));
    expect(html).toContain('Value-free JSON schema discovery');
    expect(html).toContain('object keys, JSON types, and object-array pointers are returned');
    expect(html).toContain('value="shape"');
    expect(html).not.toContain('Configure bounded JSON field mapping');
  });
});
