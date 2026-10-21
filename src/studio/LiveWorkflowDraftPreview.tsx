import type { LiveWorkflowDraft } from './types';
import { Check, Eye, X } from 'lucide-react';
import './LiveWorkflowDraftPreview.css';

/** A non-modal status bar. The actual draft is rendered by the normal workflow canvas. */
export function LiveWorkflowDraftPreview({draft,dirty,onApply,onDismiss}:{draft:LiveWorkflowDraft;dirty:boolean;onApply:()=>void;onDismiss:()=>void}){
  const model=draft.workflow.executionModel??'sequence';
  const count=model==='flowchart'?draft.workflow.flowchart?.nodes.length??0:model==='state_machine'?draft.workflow.stateMachine?.states.length??0:draft.workflow.activities.length;
  const plural=model==='flowchart'?'nodes':model==='state_machine'?'states':'activities';
  const noun=count===1?(model==='flowchart'?'node':model==='state_machine'?'state':'activity'):plural;
  return <div className="live-draft-banner" role="status" aria-live="polite" aria-label="Live MCP workflow build">
    <span className="live-draft-pulse" aria-hidden="true"/>
    <div className="live-draft-banner-copy"><strong><Eye size={14}/> MCP is building {draft.name}</strong><small>{count} {noun} · {model.replace('_',' ')} · unsaved preview · updated {new Date(draft.updatedAt*1000).toLocaleTimeString()}</small></div>
    <span className="live-draft-canvas-hint">The workflow canvas is showing this live snapshot.</span>
    <button type="button" className="toolbar-btn primary" disabled={dirty} title={dirty?'Save or discard local edits before inserting the MCP draft':'Keep this draft in the Studio editor'} onClick={onApply}><Check size={14}/> Insert</button>
    <button type="button" className="tiny-icon" aria-label="Dismiss live MCP workflow preview" title="Dismiss preview" onClick={onDismiss}><X size={16}/></button>
  </div>
}
