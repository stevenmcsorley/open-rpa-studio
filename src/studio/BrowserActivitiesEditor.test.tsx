import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe,expect,it } from 'vitest';
import { BrowserLaunchEditor } from './BrowserLaunchEditor';
import { BrowserRecordsEditor } from './BrowserRecordsEditor';
import { SelectorHealingEditor } from './SelectorHealingEditor';

describe('browser activity editors',()=>{
  it('offers browser engine and visible-window settings',()=>{
    const html=renderToStaticMarkup(createElement(BrowserLaunchEditor,{activity:{id:'launch',type:'browser_launch',browserType:'chromium',channel:'chromium',headless:false},onChange:()=>{}}));
    expect(html).toContain('Playwright Chromium');
    expect(html).toContain('Google Chrome');
    expect(html).toContain('Microsoft Edge');
    expect(html).toContain('Firefox');
    expect(html).toContain('WebKit');
    expect(html).toContain('Show browser window while running');
    expect(html).toContain('Persistent session profile (optional)');
    expect(html).toContain('separate from your normal browser and project exports');
  });

  it('shows custom executable path only for selected custom Chromium',()=>{
    const html=renderToStaticMarkup(createElement(BrowserLaunchEditor,{activity:{id:'launch',type:'browser_launch',browserType:'chromium',channel:'custom',executablePath:'C:\\Apps\\Brave\\brave.exe'},onChange:()=>{}}));
    expect(html).toContain('Browser executable path');
    expect(html).toContain('C:\\Apps\\Brave\\brave.exe');
    expect(html).toContain('Chromium-based browsers');
  });

  it('reports detection for the selected engine and distinguishes detected from launch-verified',()=>{
    const status={engines:{chromium:{available:true},firefox:{available:false},webkit:{available:true}},channels:{chromium:{available:false},chrome:{available:true},msedge:{available:false}}};
    const chrome=renderToStaticMarkup(createElement(BrowserLaunchEditor,{activity:{id:'launch',type:'browser_launch',browserType:'chromium',channel:'chrome'},browserStatus:status,onChange:()=>{}}));
    const firefox=renderToStaticMarkup(createElement(BrowserLaunchEditor,{activity:{id:'launch',type:'browser_launch',browserType:'firefox'},browserStatus:status,onChange:()=>{}}));
    expect(chrome).toContain('Executable detected. Compatibility is confirmed when the browser launches.');
    expect(firefox).toContain('This runtime was not detected.');
  });

  it('offers detected Chromium browsers as named choices without requiring a path lookup',()=>{
    const status={engines:{chromium:{available:true}},channels:{chromium:{available:false},chrome:{available:false},msedge:{available:false},brave:{available:true,executable:'C:\\Apps\\Brave\\brave.exe',name:'Brave'},vivaldi:{available:true,executable:'C:\\Apps\\Vivaldi\\vivaldi.exe',name:'Vivaldi'}}};
    const html=renderToStaticMarkup(createElement(BrowserLaunchEditor,{activity:{id:'launch',type:'browser_launch',browserType:'chromium',channel:'custom',executablePath:'C:\\Apps\\Brave\\brave.exe'},browserStatus:status,onChange:()=>{}}));
    expect(html).toContain('Detected installed browsers');
    expect(html).toContain('Brave');
    expect(html).toContain('Vivaldi');
    expect(html).toContain('value="installed:brave" selected=""');
    expect(html).toContain('Brave detected; compatibility is checked when the workflow launches it.');
  });

  it('explains conservative selector recovery as an explicit opt-in',()=>{
    const html=renderToStaticMarkup(createElement(SelectorHealingEditor,{enabled:false,supported:true,onChange:()=>{}}));
    expect(html).toContain('Enable conservative accessible selector recovery');
    expect(html).toContain('same-role control with a strong unique name match');
    expect(html).toContain('CSS, text, and test-ID selectors are never repaired.');
  });

  it('displays the editable repeated-card field schema and bounded result options',()=>{
    const html=renderToStaticMarkup(createElement(BrowserRecordsEditor,{activity:{id:'extract',type:'browser_extract_records',fields:[{name:'title',selector:'h3 a',source:'text',required:true}]},onChange:()=>{}}));
    expect(html).toContain('RECORD FIELDS');
    expect(html).toContain('relative to its card');
    expect(html).toContain('h3 a');
    expect(html).toContain('Visible text');
    expect(html).toContain('HTML attribute');
    expect(html).toContain('Add field');
    expect(html).toContain('Required and non-empty');
    expect(html).not.toContain('Field mappings (JSON)');
  });

  it('shows attribute and class-token controls only for attribute mappings',()=>{
    const html=renderToStaticMarkup(createElement(BrowserRecordsEditor,{activity:{id:'extract',type:'browser_extract_records',fields:[{name:'rating',selector:'p.star-rating',source:'attribute',attribute:'class',tokenIndex:1,required:true}]},onChange:()=>{}}));
    expect(html).toContain('aria-label="Field 1 attribute"');
    expect(html).toContain('value="class"');
    expect(html).toContain('aria-label="Field 1 token index"');
    expect(html).toContain('value="1"');
    expect(html).toContain('star-rating Three');
  });

  it('exposes bounded page accumulation only when append mode is enabled',()=>{
    const html=renderToStaticMarkup(createElement(BrowserRecordsEditor,{activity:{id:'extract',type:'browser_extract_records',append:true,maxTotalRecords:1200,maxTotalOutputChars:750000,fields:[{name:'title',selector:'h2',source:'text'}]},onChange:()=>{}}));
    expect(html).toContain('Append this page to the existing result');
    expect(html).toContain('Maximum combined records');
    expect(html).toContain('value="1200"');
    expect(html).toContain('Maximum combined text');
    expect(html).toContain('value="750000"');
    expect(html).toContain('partial combined result is removed');
  });

  it('allows append-mode record deduplication by stable mapped fields',()=>{
    const html=renderToStaticMarkup(createElement(BrowserRecordsEditor,{activity:{id:'extract',type:'browser_extract_records',append:true,deduplicateBy:['url'],fields:[{name:'title',selector:'h2',source:'text'},{name:'url',selector:'a',source:'attribute',attribute:'href'}]},onChange:()=>{}}));
    expect(html).toContain('DEDUPLICATE BY MAPPED FIELDS');
    expect(html).toContain('stable identifier such as item URL or SKU');
    expect(html).toContain('aria-label="Deduplicate by url"');
    expect(html).toContain('checked=""');
    expect(html).toContain('records with all selected values blank are retained separately');
  });
});
