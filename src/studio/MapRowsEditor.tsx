import { Plus, Trash2 } from 'lucide-react';
import type { Activity } from './types';

type Mapping={field:string;expression:string};
export function MapRowsEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const mappings=Array.isArray(activity.mappings)?activity.mappings as Mapping[]:[];
  const patchMapping=(index:number,patch:Partial<Mapping>)=>onChange({mappings:mappings.map((mapping,i)=>i===index?{...mapping,...patch}:mapping)});
  return <section className="filter-rows-editor" aria-label="Map Rows settings">
    <div className="field"><label>Rows source<input aria-label="Map Rows rows source" value={String(activity.rows??'rows')} onChange={event=>onChange({rows:event.target.value})}/></label></div>
    <div className="filter-rows-heading"><strong>OUTPUT FIELDS</strong><span>{mappings.length}/100</span></div>
    <p className="filter-rows-help">Each result is a new record containing only these fields. Expressions use safe values from <code>row</code>, zero-based <code>rowIndex</code>, JSON literals and pure functions: upper, lower, str, int, float, bool, len.</p>
    {mappings.map((mapping,index)=><div className="map-rows-mapping" key={`${mapping.field}-${index}`}>
      <label><span>Output field</span><input aria-label={`Map Rows output field ${index+1}`} maxLength={256} value={mapping.field} onChange={event=>patchMapping(index,{field:event.target.value})}/></label>
      <label><span>Safe expression</span><input aria-label={`Map Rows expression ${index+1}`} maxLength={4096} value={mapping.expression} onChange={event=>patchMapping(index,{expression:event.target.value})}/></label>
      <button type="button" className="tiny-icon" aria-label={`Remove mapping ${index+1}`} title="Remove mapping" onClick={()=>onChange({mappings:mappings.filter((_,i)=>i!==index)})}><Trash2 size={13}/></button>
    </div>)}
    <button type="button" className="toolbar-btn filter-add" disabled={mappings.length>=100} onClick={()=>onChange({mappings:[...mappings,{field:'',expression:'row.'}]})}><Plus size={13}/> Add output field</button>
    <div className="filter-rows-top"><label>Maximum input rows<input aria-label="Map Rows maximum input rows" type="number" min={1} max={100000} value={Number(activity.maxRows??100000)} onChange={event=>onChange({maxRows:Number(event.target.value)})}/></label><label>Result variable<input aria-label="Map Rows result variable" value={String(activity.result??'mappedRows')} onChange={event=>onChange({result:event.target.value})}/></label></div>
  </section>;
}
