import { FormEvent, useState } from 'react';
import { Eye, Plus, X } from 'lucide-react';
import type { DebugWatchResult } from './bridge';

export function DebugWatchesPanel({expressions,results,paused,onAdd,onRemove}:{expressions:string[];results:Record<string,DebugWatchResult>;paused:boolean;onAdd:(expression:string)=>void;onRemove:(expression:string)=>void}){
  const [draft,setDraft]=useState('');
  function submit(event:FormEvent){event.preventDefault();const value=draft.trim();if(value){onAdd(value);setDraft('')}}
  return <section className="debug-watches" aria-label="Debugger watch expressions">
    <header><div><Eye size={13}/><strong>WATCH EXPRESSIONS</strong><span>{expressions.length}</span></div><small>{paused?'Evaluated against live scope while paused':'Pause the debugger to inspect values'}</small></header>
    <form onSubmit={submit}><input aria-label="Watch expression" value={draft} onChange={event=>setDraft(event.target.value)} maxLength={2048} placeholder="e.g. len(rows) or order.total" disabled={!paused}/><button className="tiny-icon" type="submit" aria-label="Add watch expression" title="Add watch expression" disabled={!paused||!draft.trim()||expressions.length>=50}><Plus size={14}/></button></form>
    <small className="watch-privacy">Uses the safe workflow expression language. Values stay in the local debug session; registered credentials are redacted.</small>
    {expressions.length>0&&<div className="watch-list">{expressions.map(expression=>{const result=results[expression];return <div className="watch-row" key={expression}><code>{expression}</code><span className={result?.status==='error'?'watch-error':''}>{!paused?'Paused to evaluate':!result?'Evaluating…':result.status==='error'?result.error:JSON.stringify(result.value)}</span><button className="tiny-icon" aria-label={`Remove watch ${expression}`} onClick={()=>onRemove(expression)}><X size={12}/></button></div>})}</div>}
  </section>
}
