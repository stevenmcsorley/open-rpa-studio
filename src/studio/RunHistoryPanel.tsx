import { useState } from 'react';
import { AlertCircle, Clock3, Download, Hash, LoaderCircle, Search, X } from 'lucide-react';
import type { RunHistoryDetail, RunHistorySummary } from './bridge';
import './RunHistoryPanel.css';

function date(value:string|null|undefined):string{return value?new Date(value).toLocaleString(): '—'}
function statusClass(value:string):string{return value==='succeeded'?'success':value==='failed'?'failed':value==='interrupted'?'interrupted':value==='cancelled'?'cancelled':'neutral'}

export function filterRunHistory(runs:RunHistorySummary[],query:string,status:string):RunHistorySummary[]{
  const needle=query.trim().toLocaleLowerCase();
  return runs.filter(run=>{
    if(status!=='all'&&run.status!==status)return false;
    if(!needle)return true;
    const error=run.error&&typeof run.error==='object'?Object.values(run.error).join(' '):'';
    return [run.projectName,run.workflow,run.runId,run.status,error].join(' ').toLocaleLowerCase().includes(needle);
  });
}

export function RunHistoryPanel({runs,selectedId,detail,loading,onSelect,onExport}:{runs:RunHistorySummary[];selectedId:string;detail:RunHistoryDetail|null;loading:boolean;onSelect:(id:string)=>void;onExport?:(id:string)=>void}){
  const [query,setQuery]=useState('');
  const [status,setStatus]=useState('all');
  const filteredRuns=filterRunHistory(runs,query,status);
  return <div className="run-history-view">
    <aside className="run-history-sidebar" aria-label="Run history browser">
      <div className="run-history-toolbar"><div className="run-history-title"><strong>RUN HISTORY</strong><small>{filteredRuns.length} of {runs.length} runs</small></div><label className="run-history-search"><Search size={13}/><input aria-label="Search run history" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Workflow, run ID, error"/><button type="button" aria-label="Clear run history search" title="Clear search" disabled={!query} onClick={()=>setQuery('')}><X size={12}/></button></label><label className="run-history-status"><span>STATUS</span><select aria-label="Filter run history by status" value={status} onChange={event=>setStatus(event.target.value)}><option value="all">All statuses</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="interrupted">Interrupted</option><option value="cancelled">Cancelled</option><option value="running">Running</option></select></label></div>
      <div className="run-history-list" aria-label="Saved workflow runs">
      {filteredRuns.length?filteredRuns.map(item=><button key={item.runId} className={selectedId===item.runId?'selected':''} aria-pressed={selectedId===item.runId} onClick={()=>onSelect(item.runId)}>
        <span className={`run-status-dot ${statusClass(item.status)}`}/><span className="run-history-primary"><strong>{item.projectName} / {item.workflow}</strong><small>{date(item.startedAt)}</small></span><code>{item.runId.slice(0,8)}</code>
      </button>):<div className="run-history-empty"><Clock3 size={15}/>{runs.length?'No runs match these filters':'No saved runs yet'}</div>}
      </div>
    </aside>
    <section className="run-history-detail" aria-label="Run details">
      {loading?<div className="run-history-empty"><LoaderCircle className="spin" size={16}/> Loading run record…</div>:!detail?<div className="run-history-empty"><Clock3 size={15}/> Select a run to inspect its saved evidence.</div>:<>
        <header className="run-detail-heading"><div><span className={`run-status-pill ${statusClass(detail.status)}`}>{detail.status.toUpperCase()}</span><strong>{detail.projectName} / {detail.workflow}</strong></div><div className="run-detail-actions"><small>{date(detail.startedAt)}{detail.endedAt?` → ${date(detail.endedAt)}`:' · still open at shutdown'}</small>{onExport&&<button type="button" className="run-evidence-export" onClick={()=>onExport(detail.runId)} title="Export this run as a versioned JSON evidence file"><Download size={12}/> Export evidence</button>}</div></header>
        {detail.recoveryNote&&<div className="run-recovery-warning"><AlertCircle size={15}/><span><strong>Interrupted run</strong>{detail.recoveryNote} External side effects may already have occurred. Inspect target systems before manually starting this workflow again.</span></div>}
        {detail.error&&<div className="run-detail-error"><strong>{String(detail.error.code??'Execution error')}</strong><span>{String(detail.error.message??'No error message was saved.')}</span></div>}
        <div className="run-detail-meta"><span><Hash size={12}/> Workflow SHA-256 <code>{detail.workflowSha256}</code></span><span>{detail.events.length} saved events</span></div>
        <div className="run-activity-list">{Object.entries(detail.result?.activities??{}).map(([id,activity])=><div className="run-activity-row" key={id}><span className={`run-status-dot ${statusClass(activity.status)}`}/><strong>{activity.type}</strong><code>{id}</code><span>{activity.durationMs===undefined?'—':`${activity.durationMs.toFixed(1)} ms`}</span>{activity.error&&<small>{activity.error}</small>}</div>)}</div>
        <div className="run-event-list" aria-label="Execution events">{detail.events.map((event,index)=><div className={`run-event-row ${String(event.event).includes('failed')?'failed':''}`} key={`${event.event}-${event.activityId??''}-${index}`}><time>{typeof event.recordedAt==='string'?date(event.recordedAt):''}</time><strong>{String(event.event??'event').replaceAll('-',' ')}</strong><code>{String(event.type??event.activityId??'')}</code><span>{String(event.message??event.error??event.nextNode??event.nextState??'')}</span></div>)}</div>
        {detail.recoveryNote&&<div className="run-recovery-footnote">Recovery is inspection only. Open and review the workflow and external system state; this record cannot establish which external side effects completed.</div>}
      </>}
    </section>
  </div>
}
