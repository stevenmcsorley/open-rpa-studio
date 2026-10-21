import { Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import type { Activity } from './types';

type Aggregation={field?:string;operation:string;as:string};
const OPERATIONS:[string,string][]=[['count_rows','Count rows'],['count_values','Count non-null values'],['sum','Sum'],['average','Average'],['min','Minimum'],['max','Maximum']];

export function GroupRowsEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const groupBy=Array.isArray(activity.groupBy)?activity.groupBy as string[]:[];
  const aggregations=Array.isArray(activity.aggregations)?activity.aggregations as Aggregation[]:[];
  const [pending,setPending]=useState('');
  const addField=()=>{const field=pending.trim();if(field&&!groupBy.includes(field)&&groupBy.length<100){onChange({groupBy:[...groupBy,field]});setPending('')}};
  const patchAggregation=(index:number,patch:Partial<Aggregation>)=>onChange({aggregations:aggregations.map((aggregation,i)=>i===index?{...aggregation,...patch}:aggregation)});
  return <section className="filter-rows-editor" aria-label="Group Rows settings">
    <div className="field"><label>Rows source<input aria-label="Rows source" value={String(activity.rows??'rows')} onChange={event=>onChange({rows:event.target.value})}/></label></div>
    <div className="filter-rows-heading"><strong>GROUP BY</strong><span>{groupBy.length}/100</span></div>
    <p className="filter-rows-help">Each unique combination of selected scalar fields becomes one output record. Missing and null group values are combined.</p>
    <div className="group-rows-add"><input aria-label="New group field" placeholder="e.g. department" value={pending} maxLength={256} onChange={event=>setPending(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();addField()}}}/><button type="button" className="toolbar-btn" disabled={!pending.trim()||groupBy.length>=100} onClick={addField}><Plus size={13}/> Add field</button></div>
    <div className="group-rows-fields">{groupBy.map((field,index)=><div className="group-rows-field" key={`${field}-${index}`}><span>{field}</span><button type="button" className="tiny-icon" aria-label={`Remove group field ${field}`} title="Remove group field" onClick={()=>onChange({groupBy:groupBy.filter((_,i)=>i!==index)})}><Trash2 size={13}/></button></div>)}</div>
    <div className="filter-rows-heading"><strong>AGGREGATIONS</strong><span>{aggregations.length}/100</span></div>
    {aggregations.map((aggregation,index)=><div className="group-rows-aggregation" key={index}>
      <div className="group-rows-aggregation-head"><label>Operation<select aria-label={`Aggregation ${index+1} operation`} value={aggregation.operation} onChange={event=>patchAggregation(index,{operation:event.target.value,...(event.target.value==='count_rows'?{}:{field:aggregation.field||'amount'})})}>{OPERATIONS.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label><button type="button" className="tiny-icon" aria-label={`Remove aggregation ${index+1}`} title="Remove aggregation" onClick={()=>onChange({aggregations:aggregations.filter((_,i)=>i!==index)})}><Trash2 size={13}/></button></div>
      <div className="group-rows-aggregation-fields">{aggregation.operation!=='count_rows'&&<label>Input field<input aria-label={`Aggregation ${index+1} input field`} value={aggregation.field??''} maxLength={256} onChange={event=>patchAggregation(index,{field:event.target.value})}/></label>}<label>Output field<input aria-label={`Aggregation ${index+1} output field`} value={aggregation.as??''} maxLength={256} onChange={event=>patchAggregation(index,{as:event.target.value})}/></label></div>
    </div>)}
    <button type="button" className="toolbar-btn filter-add" disabled={aggregations.length>=100} onClick={()=>onChange({aggregations:[...aggregations,{field:'amount',operation:'sum',as:`sum${aggregations.length+1}`}]})}><Plus size={13}/> Add aggregation</button>
    <div className="filter-rows-top"><label>Maximum groups<input aria-label="Maximum groups" type="number" min={1} max={100000} value={Number(activity.maxGroups??100000)} onChange={event=>onChange({maxGroups:Number(event.target.value)})}/></label><label>Result variable<input aria-label="Grouped result variable" value={String(activity.result??'groupedRows')} onChange={event=>onChange({result:event.target.value})}/></label></div>
    <p className="field-hint">Sum and average require finite numeric values; missing and null fields are ignored. Min and max accept consistently numeric or text values. Output is limited to 100,000 groups.</p>
  </section>;
}
