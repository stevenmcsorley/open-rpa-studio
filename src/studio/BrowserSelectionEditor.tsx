import { useEffect, useState } from 'react';
import type { Activity } from './types';

export function BrowserSelectionEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const values=Array.isArray(activity.values)?activity.values.filter((value):value is string=>typeof value==='string'):[];
  const [draft,setDraft]=useState(values.join('\n'));
  useEffect(()=>setDraft(values.join('\n')),[activity.id,JSON.stringify(values)]);
  return <section className="filter-rows-editor" aria-label="Select multiple web options">
    <div className="field"><label>Option values or accessible names<textarea aria-label="Web option values" rows={5} spellCheck={false} placeholder={'books\nmusic'} value={draft} onChange={event=>{setDraft(event.target.value);onChange({values:event.target.value.split(/\r?\n/).filter(value=>value.length>0)})}}/></label><small className="field-hint">Enter one exact HTML option value per line, or exact accessible option names for a custom ARIA listbox. Custom listboxes must expose aria-multiselectable="true" and uniquely named options.</small></div>
    <div className="field"><label>Selected options result variable<input aria-label="Selected options result variable" value={String(activity.result??'selectedValues')} onChange={event=>onChange({result:event.target.value})}/></label></div>
  </section>;
}
