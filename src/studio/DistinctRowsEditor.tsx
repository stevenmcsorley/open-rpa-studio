import { Plus, Trash2 } from 'lucide-react';
import type { Activity } from './types';

export function DistinctRowsEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const keys=Array.isArray(activity.keys)?activity.keys as string[]:[];
  return <section className="filter-rows-editor" aria-label="Distinct Rows settings">
    <div className="field"><label>Rows source<input aria-label="Distinct Rows rows source" value={String(activity.rows??'rows')} onChange={event=>onChange({rows:event.target.value})}/></label></div>
    <div className="filter-rows-heading"><strong>DUPLICATE KEYS</strong><span>{keys.length}/100</span></div>
    <p className="filter-rows-help">Rows match only when all key values match by type. Missing fields and nulls are equivalent. Kept records stay in source order; non-finite and complex key values are rejected.</p>
    {keys.map((key,index)=><div className="distinct-rows-key" key={`${key}-${index}`}>
      <label><span>Key field {index+1}</span><input aria-label={`Distinct Rows key field ${index+1}`} maxLength={256} value={key} onChange={event=>onChange({keys:keys.map((value,i)=>i===index?event.target.value:value)})}/></label>
      <button type="button" className="tiny-icon" aria-label={`Remove key field ${index+1}`} title="Remove key field" onClick={()=>onChange({keys:keys.filter((_,i)=>i!==index)})}><Trash2 size={13}/></button>
    </div>)}
    <button type="button" className="toolbar-btn filter-add" disabled={keys.length>=100} onClick={()=>onChange({keys:[...keys,'']})}><Plus size={13}/> Add key field</button>
    <div className="filter-rows-top"><label>Keep occurrence<select aria-label="Distinct Rows keep occurrence" value={String(activity.keep??'first')} onChange={event=>onChange({keep:event.target.value})}><option value="first">First</option><option value="last">Last</option></select></label><label>Maximum input rows<input aria-label="Distinct Rows maximum input rows" type="number" min={1} max={100000} value={Number(activity.maxRows??100000)} onChange={event=>onChange({maxRows:Number(event.target.value)})}/></label></div>
    <div className="field"><label>Result variable<input aria-label="Distinct Rows result variable" value={String(activity.result??'distinctRows')} onChange={event=>onChange({result:event.target.value})}/></label></div>
  </section>;
}
