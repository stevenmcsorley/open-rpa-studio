import { useEffect,useMemo,useState } from 'react';
import type { CSSProperties } from 'react';
import type { Activity } from './types';
import { flattenWorkflowOutline } from './workflowOutlineModel';

export function WorkflowOutline({activities,selected,onSelect,title='WORKFLOW OUTLINE'}:{activities:Activity[];selected:string;onSelect:(id:string)=>void;title?:string}){
  const [open,setOpen]=useState(false);
  const [anchor,setAnchor]=useState<{top:number;right:number}|null>(null);
  const entries=useMemo(()=>flattenWorkflowOutline(activities),[activities]);
  useEffect(()=>{
    const canvas=document.querySelector('.workflow-canvas');
    if(!canvas)return;
    const update=()=>{const rect=canvas.getBoundingClientRect();setAnchor({top:rect.top+12,right:Math.max(8,window.innerWidth-rect.right+14)})};
    update();
    const observer=new ResizeObserver(update);observer.observe(canvas);
    window.addEventListener('resize',update);
    return()=>{observer.disconnect();window.removeEventListener('resize',update)};
  },[]);
  return <aside className={`workflow-outline ${open?'open':''}`} style={anchor??undefined} aria-label="Workflow outline">
    <div className="workflow-outline-head"><strong title={title}>{title}</strong><span>{entries.length} ACTIVITIES</span><button type="button" aria-expanded={open} aria-label={open?'Collapse workflow outline':'Expand workflow outline'} onClick={()=>setOpen(value=>!value)}>{open?'Hide':'Outline'}</button></div>
    {open&&<nav className="workflow-outline-list" aria-label="Activities and nested branches">{entries.length?entries.map(entry=><button type="button" key={entry.id} className={selected===entry.id?'selected':''} style={{'--outline-depth':Math.min(entry.depth,8)} as CSSProperties} title={entry.context?`${entry.context} · ${entry.label}`:entry.label} aria-current={selected===entry.id?'true':undefined} onClick={()=>{onSelect(entry.id);requestAnimationFrame(()=>document.getElementById(`activity-${encodeURIComponent(entry.id)}`)?.scrollIntoView({behavior:'smooth',block:'center'}))}}><span className="outline-branch">{entry.context||'WORKFLOW'}</span><span className="outline-activity">{entry.label}</span><small>{entry.kind}</small></button>):<p>No activities in this workflow.</p>}</nav>}
  </aside>;
}
