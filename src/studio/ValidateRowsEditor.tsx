import { Plus, Trash2 } from 'lucide-react';
import type { Activity } from './types';

type Rule={field:string;type:'text'|'number'|'boolean'|'object'|'array';required:boolean;nonEmpty:boolean};
const newRule:Rule={field:'',type:'text',required:false,nonEmpty:false};
export function ValidateRowsEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const rules=Array.isArray(activity.rules)?activity.rules as Rule[]:[];
  const patchRule=(index:number,patch:Partial<Rule>)=>onChange({rules:rules.map((rule,i)=>i===index?{...rule,...patch}:rule)});
  return <section className="filter-rows-editor" aria-label="Validate Rows settings">
    <div className="field"><label>Rows source<input aria-label="Validate Rows source" value={String(activity.rows??'rows')} onChange={event=>onChange({rows:event.target.value})}/></label></div>
    <div className="filter-rows-heading"><strong>FIELD RULES</strong><span>{rules.length}/100</span></div>
    <p className="filter-rows-help">Types are checked as supplied; values are never coerced. Null or missing values pass optional rules. Invalid outputs retain the original row and include field, reason code and message.</p>
    {rules.map((rule,index)=><div className="validate-row-rule" key={`${rule.field}-${index}`}>
      <label><span>Field</span><input aria-label={`Validate Rows field ${index+1}`} maxLength={256} value={rule.field} onChange={event=>patchRule(index,{field:event.target.value})}/></label>
      <label><span>Type</span><select aria-label={`Validate Rows type ${index+1}`} value={rule.type} onChange={event=>patchRule(index,{type:event.target.value as Rule['type']})}>{['text','number','boolean','object','array'].map(type=><option key={type}>{type}</option>)}</select></label>
      <label className="validate-check"><input type="checkbox" aria-label={`Validate Rows required ${index+1}`} checked={rule.required} onChange={event=>patchRule(index,{required:event.target.checked})}/>Required</label>
      <label className="validate-check"><input type="checkbox" aria-label={`Validate Rows non-empty ${index+1}`} checked={rule.nonEmpty} onChange={event=>patchRule(index,{nonEmpty:event.target.checked})}/>Non-empty</label>
      <button type="button" className="tiny-icon" aria-label={`Remove validation rule ${index+1}`} onClick={()=>onChange({rules:rules.filter((_,i)=>i!==index)})}><Trash2 size={13}/></button>
    </div>)}
    <button type="button" className="toolbar-btn filter-add" disabled={rules.length>=100} onClick={()=>onChange({rules:[...rules,{...newRule}]})}><Plus size={13}/> Add field rule</button>
    <div className="filter-rows-top"><label>Valid rows variable<input aria-label="Validate Rows valid output" value={String(activity.validResult??'validRows')} onChange={event=>onChange({validResult:event.target.value})}/></label><label>Invalid rows variable<input aria-label="Validate Rows invalid output" value={String(activity.invalidResult??'invalidRows')} onChange={event=>onChange({invalidResult:event.target.value})}/></label></div>
    <div className="field"><label>Maximum input rows<input aria-label="Validate Rows maximum input" type="number" min={1} max={100000} value={Number(activity.maxRows??100000)} onChange={event=>onChange({maxRows:Number(event.target.value)})}/></label></div>
  </section>;
}
