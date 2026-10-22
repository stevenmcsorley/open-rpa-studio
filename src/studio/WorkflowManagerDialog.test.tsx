import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { WorkflowManagerDialog } from './WorkflowManagerDialog';

const render=()=>renderToStaticMarkup(createElement(WorkflowManagerDialog,{workflows:{Main:{activities:[]},'Daily Import':{activities:[{},{}]},'Monthly Report':{executionModel:'flowchart',flowchart:{nodes:[{},{}]}}},active:'Daily Import',dirty:name=>name==='Daily Import',schedules:[],schedulesLoading:false,onRefreshSchedules:()=>{},onCreateSchedule:()=>{},onToggleSchedule:()=>{},onDeleteSchedule:()=>{},onClose:()=>{},onOpen:()=>{},onSave:()=>{},onSaveAs:()=>{},onRename:()=>{},onDelete:()=>{},onNew:()=>{},onChain:()=>{}}));

describe('workflow manager',()=>{
 it('shows saved workflows, editor status, and lifecycle actions',()=>{const html=render();expect(html).toContain('Workflow Manager');expect(html).toContain('Daily Import');expect(html).toContain('Monthly Report');expect(html).toContain('UNSAVED');expect(html).toContain('Save project');expect(html).toContain('Save As / duplicate workflow');expect(html).toContain('Rename workflow');expect(html).toContain('Delete workflow')});
 it('offers chain and recurring schedule management in the active project',()=>{const html=render();expect(html).toContain('Build chain');expect(html).toContain('Schedules');expect(html).toContain('active project');expect(html).toContain('Closing a tab keeps its workflow in the project')});
});
