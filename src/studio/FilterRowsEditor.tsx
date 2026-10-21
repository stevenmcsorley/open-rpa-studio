import { useEffect, useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import type { Activity } from './types';

const OPERATORS=[
  ['equals','Equals'],['not_equals','Does not equal'],['contains','Contains'],['not_contains','Does not contain'],
  ['starts_with','Starts with'],['ends_with','Ends with'],['greater_than','Greater than'],['greater_or_equal','At least'],
  ['less_than','Less than'],['less_or_equal','At most'],['is_empty','Is empty'],['is_not_empty','Is not empty'],
] as const;
type Condition={field:string;operator:string;value?:unknown;ignoreCase?:boolean};
const defaultCondition=():Condition=>({field:'status',operator:'equals',value:'active'});
function encode(value:unknown):string{return JSON.stringify(value,null,2)??'null'}

export function FilterRowsEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const conditions=Array.isArray(activity.conditions)?activity.conditions as Condition[]:[];
  const conditionKey=useMemo(()=>encode(conditions),[conditions]);
  const [valueDrafts,setValueDrafts]=useState<string[]>(()=>conditions.map(condition=>encode(condition.value)));
  const [valueErrors,setValueErrors]=useState<Record<number,string>>({});
  useEffect(()=>{setValueDrafts(conditions.map(condition=>encode(condition.value)));setValueErrors({})},[conditionKey]);
  const patchCondition=(index:number,patch:Partial<Condition>)=>onChange({conditions:conditions.map((condition,i)=>i===index?{...condition,...patch}:condition)});
  const unary=(operator:string)=>operator==='is_empty'||operator==='is_not_empty';
  function editValue(index:number,text:string){
    setValueDrafts(current=>current.map((value,i)=>i===index?text:value));
    try{const parsed=JSON.parse(text);if(typeof parsed==='number'&&!Number.isFinite(parsed)){setValueErrors(current=>({...current,[index]:'Numbers must be finite JSON values.'}));return}setValueErrors(current=>{const next={...current};delete next[index];return next});patchCondition(index,{value:parsed})}
    catch{setValueErrors(current=>({...current,[index]:'Enter a valid JSON value; text values need quotation marks.'}))}
  }
  return <section className="filter-rows-editor" aria-label="Filter Rows settings">
    <div className="filter-rows-top"><label>Rows<input aria-label="Rows source" value={String(activity.rows??'rows')} onChange={event=>onChange({rows:event.target.value})}/></label><label>Result variable<input aria-label="Filtered result variable" value={String(activity.result??'filteredRows')} onChange={event=>onChange({result:event.target.value})}/></label></div>
    <div className="filter-rows-heading"><strong>CONDITIONS</strong><label>Match<select aria-label="Condition matching mode" value={String(activity.match??'all')} onChange={event=>onChange({match:event.target.value})}><option value="all">All (AND)</option><option value="any">Any (OR)</option></select></label></div>
    <p className="filter-rows-help">Keep records whose fields satisfy the selected conditions. Values use JSON types, and expressions such as <code>{'{{ minimum }}'}</code> are evaluated safely.</p>
    {conditions.map((condition,index)=><div className="filter-condition" key={index}>
      <div className="filter-condition-fields"><input aria-label={`Condition ${index+1} field`} placeholder="Field name" value={condition.field??''} onChange={event=>patchCondition(index,{field:event.target.value})}/><select aria-label={`Condition ${index+1} operator`} value={condition.operator??'equals'} onChange={event=>patchCondition(index,{operator:event.target.value})}>{OPERATORS.map(([value,label])=><option value={value} key={value}>{label}</option>)}</select><button type="button" className="tiny-icon" aria-label={`Remove condition ${index+1}`} title="Remove condition" onClick={()=>onChange({conditions:conditions.filter((_,i)=>i!==index)})}><Trash2 size={13}/></button></div>
      {!unary(condition.operator)&&<><textarea aria-label={`Condition ${index+1} JSON value`} rows={2} spellCheck={false} value={valueDrafts[index]??encode(condition.value)} aria-invalid={Boolean(valueErrors[index])} onChange={event=>editValue(index,event.target.value)}/>{valueErrors[index]&&<small role="alert" className="filter-value-error">{valueErrors[index]}</small>}</>}
      <label className="filter-ignore-case"><input type="checkbox" checked={condition.ignoreCase===true} disabled={!['equals','not_equals','contains','not_contains','starts_with','ends_with'].includes(condition.operator)} onChange={event=>patchCondition(index,{ignoreCase:event.target.checked})}/> Ignore letter case</label>
    </div>)}
    <button type="button" className="toolbar-btn filter-add" disabled={conditions.length>=100} onClick={()=>onChange({conditions:[...conditions,defaultCondition()]})}><Plus size={13}/> Add condition</button>
  </section>;
}
