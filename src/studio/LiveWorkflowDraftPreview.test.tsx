import { describe,expect,it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { LiveWorkflowDraftPreview } from './LiveWorkflowDraftPreview';
import type { CatalogEntry,LiveWorkflowDraft } from './types';

const catalog:CatalogEntry[]=[{type:'log',title:'Log Message',category:'Workflow',description:'Log text',defaults:{}}];
const draft=(activities:LiveWorkflowDraft['workflow']['activities']):LiveWorkflowDraft=>({format:'openrpa.live-workflow-draft',formatVersion:1,draftId:'current',name:'Stock Lookup',updatedAt:1,workflow:{format:'openrpa.workflow',formatVersion:1,name:'Stock Lookup',variables:[],arguments:[],activities}});

describe('MCP live workflow preview',()=>{
  it('renders successive snapshots as a live, explicitly unsaved activity list',()=>{
    const first=renderToStaticMarkup(createElement(LiveWorkflowDraftPreview,{draft:draft([{id:'open',type:'log',message:'Open browser'}]),catalog,dirty:false,onApply:()=>{},onDismiss:()=>{}}));
    const next=renderToStaticMarkup(createElement(LiveWorkflowDraftPreview,{draft:draft([{id:'open',type:'log',message:'Open browser'},{id:'search',type:'log',message:'Search ticker'}]),catalog,dirty:false,onApply:()=>{},onDismiss:()=>{}}));
    expect(first).toContain('Open browser');expect(first).not.toContain('Search ticker');
    expect(next).toContain('Open browser');expect(next).toContain('Search ticker');expect(next).toContain('not yet saved to the project');
  });
  it('prevents inserting a draft over unsaved local editor changes',()=>{
    const html=renderToStaticMarkup(createElement(LiveWorkflowDraftPreview,{draft:draft([]),catalog,dirty:true,onApply:()=>{},onDismiss:()=>{}}));
    expect(html).toContain('disabled=""');expect(html).toContain('Save or discard your local edits');
  });
});
