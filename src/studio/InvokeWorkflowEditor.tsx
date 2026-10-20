import type { Activity, Workflow } from './types';

type Props = {
  activity: Activity;
  workflows: Record<string, Workflow>;
  currentWorkflow: string;
  onPatch: (patch: Record<string, unknown>) => void;
};

function displayValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value === undefined) return '';
  return JSON.stringify(value);
}

function bindingValue(raw: string, type: string): unknown {
  if (raw.includes('{{') || type === 'string' || type === 'any') return raw;
  try { return JSON.parse(raw); } catch { return raw; }
}

export function InvokeWorkflowEditor({ activity, workflows, currentWorkflow, onPatch }: Props) {
  const target = typeof activity.workflow === 'string' ? activity.workflow : '';
  const child = workflows[target];
  const inputs = activity.inputs && typeof activity.inputs === 'object' ? activity.inputs as Record<string, unknown> : {};
  const outputs = activity.outputs && typeof activity.outputs === 'object' ? activity.outputs as Record<string, unknown> : {};
  const args = child?.arguments ?? [];

  function setBinding(name: string, raw: string, type: string) {
    const next = { ...inputs };
    if (!raw.trim()) delete next[name];
    else next[name] = bindingValue(raw, type);
    onPatch({ inputs: next });
  }
  function setOutput(name: string, raw: string) {
    const next = { ...outputs };
    if (!raw.trim()) delete next[name];
    else next[name] = raw.trim();
    onPatch({ outputs: next });
  }

  return <section className="invoke-workflow-editor" aria-label="Reusable workflow bindings">
    <div className="field">
      <label>Reusable workflow</label>
      <select aria-label="Reusable workflow target" value={target} onChange={event => {
        const name = event.target.value;
        const selected = workflows[name];
        const inputNames = new Set((selected?.arguments ?? []).filter(arg => arg.direction !== 'out').map(arg => arg.name));
        const outputNames = new Set((selected?.arguments ?? []).filter(arg => arg.direction !== 'in').map(arg => arg.name));
        onPatch({ workflow: name, inputs: Object.fromEntries(Object.entries(inputs).filter(([key]) => inputNames.has(key))), outputs: Object.fromEntries(Object.entries(outputs).filter(([key]) => outputNames.has(key))) });
      }}>
        <option value="">Choose a workflow…</option>
        {Object.keys(workflows).filter(name => name !== currentWorkflow).map(name => <option key={name} value={name}>{name}</option>)}
      </select>
      <small className="field-hint">Select a project workflow to map its declared arguments.</small>
    </div>
    {target && !child && <div className="ai-error">The target workflow “{target}” is not available in this project.</div>}
    {child && <>
      <div className="invoke-section-title">INPUT ARGUMENTS</div>
      {args.filter(arg => arg.direction !== 'out').map(arg => <div className="field invoke-binding" key={`in-${arg.name}`}>
        <label htmlFor={`invoke-in-${activity.id}-${arg.name}`}>{arg.name} <span>{arg.type} · {arg.required === false || 'default' in arg ? 'optional' : 'required'}</span></label>
        <input id={`invoke-in-${activity.id}-${arg.name}`} aria-label={`Input ${arg.name}`} value={displayValue(inputs[arg.name])} placeholder={arg.type === 'string' ? 'Text or {{expression}}' : 'JSON value or {{expression}}'} onChange={event => setBinding(arg.name, event.target.value, arg.type)} />
        {arg.required !== false && !('default' in arg) && inputs[arg.name] === undefined && <small className="field-hint">Required before this workflow can run.</small>}
      </div>)}
      {!args.some(arg => arg.direction !== 'out') && <p className="empty-variable">No input arguments declared.</p>}

      <div className="invoke-section-title">OUTPUT ARGUMENTS</div>
      {args.filter(arg => arg.direction !== 'in').map(arg => <div className="field invoke-binding" key={`out-${arg.name}`}>
        <label htmlFor={`invoke-out-${activity.id}-${arg.name}`}>{arg.name} <span>{arg.type} · {arg.direction}</span></label>
        <input id={`invoke-out-${activity.id}-${arg.name}`} aria-label={`Output ${arg.name} caller variable`} value={String(outputs[arg.name] ?? arg.target ?? arg.name)} onChange={event => setOutput(arg.name, event.target.value)} />
      </div>)}
      <div className="field">
        <label>Collect new child variables</label>
        <input aria-label="Collect reusable workflow result variable" value={String(activity.resultTarget ?? '')} placeholder="Optional result variable" onChange={event => onPatch({ resultTarget: event.target.value || undefined })} />
      </div>
      <div className="field-note"><span>Use <code>{'{{ variableName }}'}</code> to pass a typed expression. Literal non-string values use JSON (for example <code>42</code> or <code>true</code>). Output targets are caller variable names.</span></div>
    </>}
  </section>;
}
