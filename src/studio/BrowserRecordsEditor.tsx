import { Plus, Trash2 } from 'lucide-react';
import type { Activity } from './types';

type Field={name:string;selector:string;source:'text'|'attribute';attribute?:string;required?:boolean;tokenIndex?:number};
const asFields=(value:unknown):Field[]=>Array.isArray(value)?value.filter((item):item is Field=>!!item&&typeof item==='object'&&typeof (item as Field).name==='string'&&typeof (item as Field).selector==='string').map(item=>({...item,source:item.source==='attribute'?'attribute':'text'})):[];

export function BrowserRecordsEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const fields=asFields(activity.fields);
  function update(index:number,patch:Partial<Field>){const previousName=fields[index]?.name;const nextFields=fields.map((field,position)=>position===index?{...field,...patch}:field);const deduplicateBy=Array.isArray(activity.deduplicateBy)?activity.deduplicateBy.filter((value):value is string=>typeof value==='string'):[];onChange({fields:nextFields,...(patch.name!==undefined&&patch.name!==previousName?{deduplicateBy:deduplicateBy.map(name=>name===previousName?patch.name!:name)}:{})});}
  function add(){
    let suffix=fields.length+1,name=`field_${suffix}`;
    const names=new Set(fields.map(field=>field.name.toLocaleLowerCase()));
    while(names.has(name.toLocaleLowerCase()))name=`field_${++suffix}`;
    onChange({fields:[...fields,{name,selector:'',source:'text',required:false}]});
  }
  function remove(index:number){const removedName=fields[index]?.name;const deduplicateBy=Array.isArray(activity.deduplicateBy)?activity.deduplicateBy.filter((value):value is string=>typeof value==='string'&&value!==removedName):[];onChange({fields:fields.filter((_,position)=>position!==index),deduplicateBy});}
  function setDeduplicate(fieldName:string,enabled:boolean){const current=Array.isArray(activity.deduplicateBy)?activity.deduplicateBy.filter((value):value is string=>typeof value==='string'):[];const deduplicateBy=enabled?[...current,fieldName]:current.filter(name=>name!==fieldName);onChange({deduplicateBy});}
  const deduplicateBy=Array.isArray(activity.deduplicateBy)?activity.deduplicateBy.filter((value):value is string=>typeof value==='string'):[];
  return <section className="selector-fallback-editor browser-records-editor">
    <div className="browser-records-heading"><div><strong>RECORD FIELDS</strong><small>{fields.length} of 50 fields</small></div><button className="toolbar-btn" type="button" onClick={add} disabled={fields.length>=50}><Plus size={12}/> Add field</button></div>
    <p>Every item matching the card selector becomes one record. Each field selector is relative to its card. Use an attribute field for a link URL or a class token for values such as star ratings.</p>
    {!fields.length&&<div className="browser-records-empty">No fields yet. Add a field to define the records this activity extracts.</div>}
    {fields.map((field,index)=><article className="browser-record-field" key={index}>
      <div className="browser-record-field-heading"><strong>FIELD {String(index+1).padStart(2,'0')}</strong><button className="tiny-icon" type="button" aria-label={`Remove field ${field.name||index+1}`} title="Remove field" onClick={()=>remove(index)}><Trash2 size={13}/></button></div>
      <div className="browser-record-field-grid">
        <label>Record column<input aria-label={`Field ${index+1} name`} value={field.name} maxLength={100} placeholder="title" onChange={event=>update(index,{name:event.target.value})}/></label>
        <label>Relative CSS selector<input aria-label={`Field ${index+1} selector`} value={field.selector} maxLength={2048} spellCheck={false} placeholder="h3 a" onChange={event=>update(index,{selector:event.target.value})}/></label>
        <label>Extract<select aria-label={`Field ${index+1} source`} value={field.source} onChange={event=>update(index,event.target.value==='attribute'?{source:'attribute',attribute:field.attribute||'href'}:{source:'text',attribute:undefined,tokenIndex:undefined})}><option value="text">Visible text</option><option value="attribute">HTML attribute</option></select></label>
        {field.source==='attribute'&&<label>Attribute name<input aria-label={`Field ${index+1} attribute`} value={field.attribute||''} maxLength={128} placeholder="href" onChange={event=>update(index,{attribute:event.target.value})}/></label>}
      </div>
      <div className="browser-record-field-options">
        <label><input type="checkbox" checked={field.required===true} onChange={event=>update(index,{required:event.target.checked})}/> Required and non-empty</label>
        {field.source==='attribute'&&<label>Whitespace token index<input aria-label={`Field ${index+1} token index`} type="number" min={0} max={20} step={1} value={field.tokenIndex??''} placeholder="Off" onChange={event=>update(index,{tokenIndex:event.target.value===''?undefined:Number(event.target.value)})}/><small>For class values such as <code>star-rating Three</code>, use index 1.</small></label>}
      </div>
    </article>)}
    <div className="browser-record-append">
      <label><input type="checkbox" checked={activity.append===true} onChange={event=>onChange({append:event.target.checked,...(!event.target.checked?{deduplicateBy:[]}:{})})}/> Append this page to the existing result</label>
      {activity.append===true&&<div className="browser-record-total-limits">
        <label>Maximum combined records<input aria-label="Maximum combined records" type="number" min={1} max={50000} step={1} value={Number(activity.maxTotalRecords??10000)} onChange={event=>onChange({maxTotalRecords:event.target.value===''?1:Number(event.target.value)})}/></label>
        <label>Maximum combined text · characters<input aria-label="Maximum combined text" type="number" min={1} max={10000000} step={1000} value={Number(activity.maxTotalOutputChars??5000000)} onChange={event=>onChange({maxTotalOutputChars:event.target.value===''?1:Number(event.target.value)})}/></label>
        <small>Use this after pagination or gradual scrolling. If any page fails or a limit is exceeded, the partial combined result is removed.</small>
        <div className="browser-record-dedupe"><strong>DEDUPLICATE BY MAPPED FIELDS</strong><small>Choose a stable identifier such as item URL or SKU. Values are compared exactly; records with all selected values blank are retained separately.</small>{fields.map(field=><label key={field.name}><input type="checkbox" aria-label={`Deduplicate by ${field.name||'unnamed field'}`} checked={deduplicateBy.includes(field.name)} disabled={!field.name} onChange={event=>setDeduplicate(field.name,event.target.checked)}/>{field.name||'(name this field first)'}</label>)}</div>
      </div>}
    </div>
    <small className="field-hint">Limits: 50 mapped fields, 5,000 cards and 10 MB of extracted text. Selectors must match at most one element inside each card; required fields fail the activity when missing or blank.</small>
  </section>;
}
