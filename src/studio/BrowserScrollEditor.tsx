import type { Activity } from './types';

export function BrowserScrollEditor({activity,onChange}:{activity:Activity;onChange:(patch:Record<string,unknown>)=>void}){
  const toBottom=activity.toBottom===true;
  const target=String(activity.containerSelector??'');
  return <section className="selector-fallback-editor browser-scroll-editor">
    <div className="selector-fallback-heading"><strong>SCROLL TARGET</strong></div>
    <div className="field"><label htmlFor="scroll-target">Target type</label><select id="scroll-target" value={target?'container':'page'} onChange={event=>onChange({containerSelector:event.target.value==='container'?(target||''):''})}><option value="page">Whole page</option><option value="container">Scrollable element</option></select></div>
    {target!==''&&<div className="field"><label htmlFor="scroll-container-selector">Container CSS selector</label><input id="scroll-container-selector" maxLength={2048} spellCheck={false} placeholder=".product-results" value={target} onChange={event=>onChange({containerSelector:event.target.value})}/><small className="field-hint">Must match exactly one visible element. The pointer is moved over it so normal wheel and lazy-load behavior can run.</small></div>}
    <div className="field"><label htmlFor="scroll-direction">Direction</label><select id="scroll-direction" value={String(activity.direction??'down')} onChange={event=>onChange({direction:event.target.value})}><option value="down">Down</option><option value="up">Up</option></select></div>
    <div className="field"><label htmlFor="scroll-distance">Distance per step · pixels</label><input id="scroll-distance" type="number" min={50} max={2000} step={50} value={Number(activity.distancePx??600)} onChange={event=>onChange({distancePx:event.target.value===''?50:Number(event.target.value)})}/></div>
    <div className="field"><label htmlFor="scroll-delay">Pause after each step · milliseconds</label><input id="scroll-delay" type="number" min={0} max={5000} step={100} value={Number(activity.delayMilliseconds??700)} onChange={event=>onChange({delayMilliseconds:event.target.value===''?0:Number(event.target.value)})}/></div>
    <div className="field"><label className="checkbox-field"><input type="checkbox" checked={toBottom} onChange={event=>onChange({toBottom:event.target.checked})}/>{toBottom?'Continue until the target end':'Scroll once'}</label></div>
    {toBottom&&<div className="field"><label htmlFor="scroll-max-steps">Maximum steps</label><input id="scroll-max-steps" type="number" min={1} max={500} step={1} value={Number(activity.maxSteps??100)} onChange={event=>onChange({maxSteps:event.target.value===''?1:Number(event.target.value)})}/><small className="field-hint">Progress reports after each step. Cancellation is checked between steps; the run stops at this bound even if a feed keeps loading.</small></div>}
    <small className="field-hint">Result contains step count, end reached, scroll position, target size and percentage. Container selectors must identify one element.</small>
  </section>;
}
