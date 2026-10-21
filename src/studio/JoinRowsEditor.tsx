import { Layers } from 'lucide-react';
import type { Activity } from './types';

export function JoinRowsEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const field=(key:string,label:string,placeholder:string)=> <label>{label}<input aria-label={label} value={String(activity[key]??'')} placeholder={placeholder} onChange={event=>onChange({[key]:event.target.value})}/></label>;
  return <section className="filter-rows-editor" aria-label="Join Rows settings">
    <div className="filter-rows-top">{field('left','Left rows','orders')}{field('right','Right rows','customers')}</div>
    <div className="filter-rows-top">{field('leftKey','Left key','customerId')}{field('rightKey','Right key','id')}</div>
    <div className="field"><label>Join type</label><select aria-label="Join type" value={String(activity.joinType??'inner')} onChange={event=>onChange({joinType:event.target.value})}><option value="inner">Inner: matching records only</option><option value="left">Left: keep every left record</option></select></div>
    <div className="filter-rows-top">{field('rightPrefix','Right field prefix','right_')}<label>Output row limit<input aria-label="Output row limit" type="number" min={1} max={100000} value={Number(activity.maxRows??100000)} onChange={event=>onChange({maxRows:Number(event.target.value)})}/></label></div>
    <div className="field"><label>Result variable</label><input aria-label="Joined result variable" value={String(activity.result??'joinedRows')} onChange={event=>onChange({result:event.target.value})}/></div>
    <p className="field-hint"><Layers size={13}/> Duplicate keys produce one output row per match. Right-side fields are prefixed to prevent name collisions. Inputs are limited to 100,000 rows and 2,000 fields per record.</p>
  </section>;
}
