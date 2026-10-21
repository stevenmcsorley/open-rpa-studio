import { describe,expect,it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { LiveWorkflowDraftPreview } from './LiveWorkflowDraftPreview';
import type { LiveWorkflowDraft } from './types';
const draft=(activities:LiveWorkflowDraft['workflow']['activities']):LiveWorkflowDraft=>({format:'openrpa.live-workflow-draft',formatVersion:1,draftId:'current',name:'Stock Lookup',updatedAt:1,workflow:{format:'openrpa.workflow',formatVersion:1,name:'Stock Lookup',variables:[],arguments:[],activities}});

describe('MCP live workflow preview',()=>{
  it('shows a non-modal live-build banner with the current snapshot size',()=>{
    const first=renderToStaticMarkup(createElement(LiveWorkflowDraftPreview,{draft:draft([{id:'open',type:'log',message:'Open browser'}]),dirty:false,onApply:()=>{},onDismiss:()=>{}}));
    const next=renderToStaticMarkup(createElement(LiveWorkflowDraftPreview,{draft:draft([{id:'open',type:'log',message:'Open browser'},{id:'search',type:'log',message:'Search ticker'}]),dirty:false,onApply:()=>{},onDismiss:()=>{}}));
    expect(first).toContain('MCP is building Stock Lookup');expect(first).toContain('1 activity');
    expect(next).toContain('MCP is building Stock Lookup');expect(next).toContain('2 activities');
    expect(next).toContain('workflow canvas is showing this live snapshot');expect(next).not.toContain('aria-modal="true"');
  });
  it('prevents inserting a draft over unsaved local editor changes',()=>{
    const html=renderToStaticMarkup(createElement(LiveWorkflowDraftPreview,{draft:draft([]),dirty:true,onApply:()=>{},onDismiss:()=>{}}));
    expect(html).toContain('disabled=""');expect(html).toContain('Save or discard local edits');
  });
});
