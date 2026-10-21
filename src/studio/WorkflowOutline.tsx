import { useMemo,useState } from 'react';
import type { CSSProperties } from 'react';
import type { Activity } from './types';
import { flattenWorkflowOutline } from './workflowOutlineModel';

export function WorkflowOutline({activities,selected,onSelect}:{activities:Activity[];selected:string;onSelect:(id:string)=>void}){
  const [open,setOpen]=useState(false);
  const entries=useMemo(()=>flattenWorkflowOutline(activities),[activities]);
  return <aside className={`workflow-outline ${open?'open':''}`} aria-label="Workflow outline">
    <div className="workflow-outline-head"><strong>WORKFLOW OUTLINE</strong><span>{entries.length} ACTIVITIES</span><button type="button" aria-expanded={open} aria-label={open?'Collapse workflow outline':'Expand workflow outline'} onClick={()=>setOpen(value=>!value)}>{open?'Hide':'Outline'}</button></div>
    {open&&<nav className="workflow-outline-list" aria-label="Activities and nested branches">{entries.length?entries.map(entry=><button type="button" key={entry.id} className={selected===entry.id?'selected':''} style={{'--outline-depth':Math.min(entry.depth,8)} as CSSProperties} title={entry.context?`${entry.context} · ${entry.label}`:entry.label} aria-current={selected===entry.id?'true':undefined} onClick={()=>{onSelect(entry.id);requestAnimationFrame(()=>document.getElementById(`activity-${encodeURIComponent(entry.id)}`)?.scrollIntoView({behavior:'smooth',block:'center'}))}}><span className="outline-branch">{entry.context||'WORKFLOW'}</span><span className="outline-activity">{entry.label}</span><small>{entry.kind}</small></button>):<p>No activities in this workflow.</p>}</nav>}
  </aside>;
}
