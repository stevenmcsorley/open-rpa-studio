import { Plus, Trash2 } from 'lucide-react';
import type { Activity } from './types';

type SortKey={field:string;direction:'ascending'|'descending';nulls:'first'|'last'};
export function SortRowsEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const keys=Array.isArray(activity.keys)?activity.keys as SortKey[]:[];
  const patchKey=(index:number,patch:Partial<SortKey>)=>onChange({keys:keys.map((key,i)=>i===index?{...key,...patch}:key)});
  return <section className="filter-rows-editor" aria-label="Sort Rows settings">
    <div className="field"><label>Rows source<input aria-label="Rows source" value={String(activity.rows??'rows')} onChange={event=>onChange({rows:event.target.value})}/></label></div>
    <div className="filter-rows-heading"><strong>SORT PRIORITY</strong><span>{keys.length}/50</span></div>
    <p className="filter-rows-help">Keys are applied in order. Ties keep their original order. Null placement is independent of sort direction; mixed non-null types in a field are rejected.</p>
    {keys.map((key,index)=><div className="sort-rows-key" key={`${key.field}-${index}`}>
      <label><span>#{index+1} Field</span><input aria-label={`Sort key ${index+1} field`} value={key.field} maxLength={256} onChange={event=>patchKey(index,{field:event.target.value})}/></label>
      <label><span>Direction</span><select aria-label={`Sort key ${index+1} direction`} value={key.direction} onChange={event=>patchKey(index,{direction:event.target.value as SortKey['direction']})}><option value="ascending">Ascending</option><option value="descending">Descending</option></select></label>
      <label><span>Nulls</span><select aria-label={`Sort key ${index+1} nulls`} value={key.nulls} onChange={event=>patchKey(index,{nulls:event.target.value as SortKey['nulls']})}><option value="first">First</option><option value="last">Last</option></select></label>
      <button type="button" className="tiny-icon" aria-label={`Remove sort key ${index+1}`} title="Remove sort key" onClick={()=>onChange({keys:keys.filter((_,i)=>i!==index)})}><Trash2 size={13}/></button>
    </div>)}
    <button type="button" className="toolbar-btn filter-add" disabled={keys.length>=50} onClick={()=>onChange({keys:[...keys,{field:'',direction:'ascending',nulls:'last'}]})}><Plus size={13}/> Add sort key</button>
    <div className="filter-rows-top"><label>Maximum input rows<input aria-label="Sort Rows maximum input rows" type="number" min={1} max={100000} value={Number(activity.maxRows??100000)} onChange={event=>onChange({maxRows:Number(event.target.value)})}/></label><label>Result variable<input aria-label="Sorted result variable" value={String(activity.result??'sortedRows')} onChange={event=>onChange({result:event.target.value})}/></label></div>
  </section>;
}
