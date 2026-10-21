import { useMemo, useState } from 'react';
import { Ban, Clock3, RefreshCw, Workflow } from 'lucide-react';
import type { QueuedJob } from './bridge';
import './JobQueuePanel.css';

function date(value:string|null|undefined):string{return value?new Date(value).toLocaleString():'—'}
const canCancel=(status:string)=>status==='queued'||status==='scheduled'||status==='running';

export function JobQueuePanel({jobs,onRefresh,onCancel,loading}:{jobs:QueuedJob[];onRefresh:()=>void;onCancel:(id:string)=>void;loading:boolean}){
  const [filter,setFilter]=useState('all');
  const visible=useMemo(()=>filter==='all'?jobs:jobs.filter(job=>job.status===filter),[jobs,filter]);
  const active=jobs.filter(job=>['queued','scheduled','running'].includes(job.status)).length;
  return <section className="job-queue-view" aria-label="Automation job queue">
    <header className="job-queue-header"><div><strong>LOCAL JOB QUEUE</strong><span>{active} active · {jobs.length} recent jobs</span></div><div className="job-queue-controls"><label><span>STATUS</span><select aria-label="Filter jobs by status" value={filter} onChange={event=>setFilter(event.target.value)}><option value="all">All jobs</option><option value="queued">Queued</option><option value="scheduled">Scheduled</option><option value="running">Running</option><option value="succeeded">Succeeded</option><option value="failed">Failed</option><option value="cancelled">Cancelled</option><option value="interrupted">Interrupted</option></select></label><button type="button" onClick={onRefresh} disabled={loading} title="Refresh queue"><RefreshCw size={13} className={loading?'spin':''}/> Refresh</button></div></header>
    <div className="job-queue-list" role="list">
      {visible.map(job=><article className="job-row" key={job.jobId} role="listitem">
        <span className={`job-status-mark ${job.status}`}/><div className="job-main"><div className="job-title"><Workflow size={14}/><strong>{job.workflow}</strong><span className={`job-status ${job.status}`}>{job.status.replaceAll('_',' ').toUpperCase()}</span>{job.cancelRequested&&<span className="job-cancel-pending">STOP REQUESTED</span>}</div><div className="job-meta"><span><Clock3 size={11}/> Submitted {date(job.submittedAt)}</span>{job.status==='scheduled'&&<span>Run at {date(job.availableAt)}</span>}{job.startedAt&&<span>Started {date(job.startedAt)}</span>}{job.runId&&<span>Run <code>{job.runId.slice(0,8)}</code></span>}</div>{job.error&&<div className="job-error"><strong>{String(job.error.code??'Job failed')}</strong> {String(job.error.message??'')}</div>}</div>
        {canCancel(job.status)&&<button type="button" className="job-cancel" onClick={()=>onCancel(job.jobId)} title={job.status==='running'?'Request safe cancellation':'Cancel queued job'}><Ban size={13}/>{job.status==='running'?'Stop':'Cancel'}</button>}
      </article>)}
      {!visible.length&&<div className="job-queue-empty"><Workflow size={17}/><span>{jobs.length?'No jobs match this status':'No queued jobs yet. Submit a workflow with the Open RPA MCP to run or schedule it locally.'}</span></div>}
    </div>
    <footer className="job-queue-footer">Single local worker · Runs link to History · Interrupted jobs are never replayed · Automatic retries are disabled</footer>
  </section>
}
