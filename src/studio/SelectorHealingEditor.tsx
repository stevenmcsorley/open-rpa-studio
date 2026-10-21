export function SelectorHealingEditor({enabled,supported,onChange}:{enabled:boolean;supported:boolean;onChange:(enabled:boolean)=>void}){
  return <section className="selector-fallback-editor">
    <div className="selector-fallback-heading"><strong>SELECTOR RECOVERY</strong></div>
    <label className="checkbox-field"><input aria-label="Enable conservative accessible selector recovery" type="checkbox" checked={enabled} disabled={!supported&&!enabled} onChange={event=>onChange(event.target.checked)}/>{enabled&&!supported?'Recovery is incompatible with this selector; turn it off':enabled?'Attempt recovery when the exact role/name is missing':supported?'Recovery disabled':'Available only for exact role selectors'}</label>
    <small className="field-hint">Opt-in and limited to exact accessibility-role selectors. Recovery requires one visible, enabled same-role control with a strong unique name match; ambiguity fails safely. CSS, text, and test-ID selectors are never repaired.</small>
  </section>;
}
