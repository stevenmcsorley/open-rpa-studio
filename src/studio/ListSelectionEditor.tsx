import { useEffect, useState } from 'react';
import type { Activity } from './types';

export function ListSelectionEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const values=Array.isArray(activity.values)?activity.values.filter((value):value is string=>typeof value==='string'):[];
  const [draft,setDraft]=useState(values.join('\n'));
  useEffect(()=>setDraft(values.join('\n')),[activity.id,JSON.stringify(values)]);
  return <section className="filter-rows-editor" aria-label="Set UI List Selection settings">
    <div className="field"><label>Selection mode<select aria-label="List selection mode" value={String(activity.mode??'replace')} onChange={event=>onChange({mode:event.target.value})}><option value="replace">Replace current selection</option><option value="add">Add to current selection</option><option value="remove">Remove from current selection</option></select></label></div>
    <div className="field"><label>Accessible option names<textarea aria-label="List option names" rows={5} spellCheck={false} placeholder={'Ready\nQueued'} value={draft} onChange={event=>{setDraft(event.target.value);onChange({values:event.target.value.split(/\r?\n/).filter(value=>value.length>0)})}}/></label><small className="field-hint">Enter one exact accessible item name per line. Names must be unique within the list. Use an empty list with Replace to clear all selections.</small></div>
    <div className="field"><label>Selected items result variable<input aria-label="List selection result variable" value={String(activity.result??'selectedItems')} onChange={event=>onChange({result:event.target.value})}/></label></div>
  </section>;
}
