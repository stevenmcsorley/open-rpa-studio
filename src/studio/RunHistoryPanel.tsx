import { AlertCircle, Clock3, Hash, LoaderCircle } from 'lucide-react';
import type { RunHistoryDetail, RunHistorySummary } from './bridge';

function date(value:string|null|undefined):string{return value?new Date(value).toLocaleString(): '—'}
function statusClass(value:string):string{return value==='succeeded'?'success':value==='failed'?'failed':value==='interrupted'?'interrupted':value==='cancelled'?'cancelled':'neutral'}

export function RunHistoryPanel({runs,selectedId,detail,loading,onSelect}:{runs:RunHistorySummary[];selectedId:string;detail:RunHistoryDetail|null;loading:boolean;onSelect:(id:string)=>void}){
  return <div className="run-history-view">
    <aside className="run-history-list" aria-label="Saved workflow runs">
      {runs.length?runs.map(item=><button key={item.runId} className={selectedId===item.runId?'selected':''} aria-pressed={selectedId===item.runId} onClick={()=>onSelect(item.runId)}>
        <span className={`run-status-dot ${statusClass(item.status)}`}/><span className="run-history-primary"><strong>{item.projectName} / {item.workflow}</strong><small>{date(item.startedAt)}</small></span><code>{item.runId.slice(0,8)}</code>
      </button>):<div className="run-history-empty"><Clock3 size={15}/> No saved runs yet</div>}
    </aside>
    <section className="run-history-detail" aria-label="Run details">
      {loading?<div className="run-history-empty"><LoaderCircle className="spin" size={16}/> Loading run record…</div>:!detail?<div className="run-history-empty"><Clock3 size={15}/> Select a run to inspect its saved evidence.</div>:<>
        <header className="run-detail-heading"><div><span className={`run-status-pill ${statusClass(detail.status)}`}>{detail.status.toUpperCase()}</span><strong>{detail.projectName} / {detail.workflow}</strong></div><small>{date(detail.startedAt)}{detail.endedAt?` → ${date(detail.endedAt)}`:' · still open at shutdown'}</small></header>
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
