import type { Activity, CatalogEntry, LiveWorkflowDraft, Workflow } from './types';
import { Check, Eye, X } from 'lucide-react';
import './LiveWorkflowDraftPreview.css';

function labelFor(activity:Activity,catalog:CatalogEntry[]):string{
  const entry=catalog.find(item=>item.type===activity.type);
  return String(activity.label??entry?.title??activity.type.replaceAll('_',' '));
}

function childrenOf(activity:Activity):{label:string;items:Activity[]}[]{
  const result:{label:string;items:Activity[]}[]=[];
  for(const key of ['then','else','body','catch','finally','default']){
    const items=activity[key];if(Array.isArray(items)&&items.length)result.push({label:key==='then'?'Then':key==='else'?'Else':key[0].toUpperCase()+key.slice(1),items:items as Activity[]});
  }
  if(Array.isArray(activity.cases))for(const [index,item]of (activity.cases as {value?:unknown;activities?:Activity[]}[]).entries())if(Array.isArray(item.activities)&&item.activities.length)result.push({label:`Case ${String(item.value??index+1)}`,items:item.activities});
  return result;
}

function flatten(workflow:Workflow):{activity:Activity;context:string}[]{
  const rows:{activity:Activity;context:string}[]=[];
  const walk=(items:Activity[],context:string)=>{for(const activity of items){rows.push({activity,context});for(const branch of childrenOf(activity))walk(branch.items,`${context} / ${branch.label}`)}};
  if(workflow.executionModel==='flowchart'&&workflow.flowchart){for(const node of workflow.flowchart.nodes)if(node.activity)walk([node.activity],`Flowchart · ${node.label??node.id}`);}
  else if(workflow.executionModel==='state_machine'&&workflow.stateMachine){for(const state of workflow.stateMachine.states)walk(state.activities,`State · ${state.label}`)}
  else walk(workflow.activities,'Sequence');
  return rows;
}

function summary(activity:Activity):string{
  const pairs=Object.entries(activity).filter(([key,value])=>!['id','type','label','then','else','body','catch','finally','default','cases','breakpoint','breakpointCondition'].includes(key)&&['string','number','boolean'].includes(typeof value));
  return pairs.slice(0,3).map(([key,value])=>`${key}: ${String(value).slice(0,90)}`).join(' · ')||'Configured activity';
}

export function LiveWorkflowDraftPreview({draft,catalog,dirty,onApply,onDismiss}:{draft:LiveWorkflowDraft;catalog:CatalogEntry[];dirty:boolean;onApply:()=>void;onDismiss:()=>void}){
  const rows=flatten(draft.workflow);
  const model=draft.workflow.executionModel??'sequence';
  return <div className="live-draft-backdrop"><section className="live-draft-dialog" role="dialog" aria-modal="true" aria-labelledby="live-draft-title">
    <header><div className="live-draft-heading"><span className="live-draft-pulse"/><div><strong id="live-draft-title">LIVE MCP WORKFLOW PREVIEW</strong><small>Validated snapshot · not yet saved to the project</small></div></div><button type="button" className="tiny-icon" aria-label="Dismiss live workflow preview" onClick={onDismiss}><X size={17}/></button></header>
    <div className="live-draft-meta"><span>{draft.name}</span><span>{model.replace('_',' ').toUpperCase()}</span><span>{rows.length} activities</span><time>Updated {new Date(draft.updatedAt*1000).toLocaleTimeString()}</time></div>
    <div className="live-draft-list" aria-live="polite">{rows.length?rows.map(({activity,context},index)=><article className="live-draft-row" key={`${activity.id}-${index}`}><span className="live-draft-index">{String(index+1).padStart(2,'0')}</span><div><strong>{labelFor(activity,catalog)}</strong><small>{context} · {activity.type}</small><code>{summary(activity)}</code></div></article>):<div className="live-draft-empty"><Eye size={19}/><span>The workflow is valid so far and has no activities yet. New staged steps will appear here.</span></div>}</div>
    <footer><p>Each new staged snapshot refreshes this preview. The saved workflow stays unchanged until you insert it or the agent commits it.</p><div><button type="button" className="toolbar-btn" onClick={onDismiss}>Dismiss</button><button type="button" className="toolbar-btn primary" disabled={dirty} title={dirty?'Save or discard your local edits before applying the MCP draft':'Insert this draft into the Studio editor'} onClick={onApply}><Check size={14}/> Insert into Studio</button></div></footer>
  </section></div>
}
