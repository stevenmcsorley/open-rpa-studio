import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import type { Argument } from './types';

const TYPES = ['string', 'integer', 'number', 'boolean', 'object', 'array', 'any'];

export function argumentDefaultError(value: unknown, type: string): string | null {
  if (type === 'any') return null;
  if (type === 'string' && typeof value === 'string') return null;
  if (type === 'integer' && typeof value === 'number' && Number.isSafeInteger(value)) return null;
  if (type === 'number' && typeof value === 'number' && Number.isFinite(value)) return null;
  if (type === 'boolean' && typeof value === 'boolean') return null;
  if (type === 'object' && value !== null && typeof value === 'object' && !Array.isArray(value)) return null;
  if (type === 'array' && Array.isArray(value)) return null;
  return `Default must be a ${type} value.`;
}

function serializeDefault(value: unknown, type: string): string {
  return type === 'string' && typeof value === 'string' ? JSON.stringify(value) : JSON.stringify(value, null, 2) ?? 'null';
}

export function ArgumentRow({ value, onChange, onRemove }: { value: Argument; onChange: (x: Argument) => void; onRemove: () => void }) {
  const [draft, setDraft] = useState(() => Object.hasOwn(value, 'default') ? serializeDefault(value.default, value.type) : '');
  const [defaultError, setDefaultError] = useState('');

  useEffect(() => {
    setDraft(Object.hasOwn(value, 'default') ? serializeDefault(value.default, value.type) : '');
    setDefaultError('');
  }, [value.default, value.type]);

  function updateDefault(text: string) {
    setDraft(text);
    try {
      const parsed: unknown = JSON.parse(text);
      const error = argumentDefaultError(parsed, value.type);
      if (error) { setDefaultError(error); return; }
      setDefaultError('');
      onChange({ ...value, default: parsed });
    } catch {
      setDefaultError('Enter a valid JSON value. Strings need quotation marks.');
    }
  }

  function toggleDefault(enabled: boolean) {
    if (!enabled) {
      const { default: _default, ...rest } = value;
      onChange(rest);
      setDraft('');
      setDefaultError('');
      return;
    }
    const initial: Record<string, unknown> = { string: '', integer: 0, number: 0, boolean: false, object: {}, array: [], any: null };
    const next = initial[value.type] ?? null;
    onChange({ ...value, default: next });
    setDraft(serializeDefault(next, value.type));
    setDefaultError('');
  }

  return <div className="argument-editor" data-testid="argument-editor">
    <div className="argument-row">
      <input aria-label="Argument name" value={value.name} onChange={e => onChange({ ...value, name: e.target.value })} />
      <select aria-label="Argument type" value={value.type} onChange={e => onChange({ ...value, type: e.target.value })}>{TYPES.map(type => <option key={type}>{type}</option>)}</select>
      <select aria-label="Argument direction" value={value.direction} onChange={e => onChange({ ...value, direction: e.target.value as Argument['direction'] })}><option>in</option><option>out</option><option>inout</option></select>
      <button className="tiny-icon" title="Remove argument" onClick={onRemove}><X size={12} /></button>
    </div>
    <div className="argument-options">
      <label title="A required input must be provided when the workflow runs and has no default."><input aria-label="Argument required" type="checkbox" checked={value.required !== false} disabled={value.direction === 'out'} onChange={e => onChange({ ...value, required: e.target.checked })} /> Required</label>
      <label title="Use this typed JSON value when the caller omits this argument."><input aria-label="Argument has default" type="checkbox" checked={Object.hasOwn(value, 'default')} onChange={e => toggleDefault(e.target.checked)} /> Default value</label>
    </div>
    {Object.hasOwn(value, 'default') && <div className="argument-default">
      <textarea aria-label="Argument default JSON" rows={2} spellCheck={false} value={draft} onChange={e => updateDefault(e.target.value)} aria-invalid={Boolean(defaultError)} />
      <small className={defaultError ? 'argument-default-error' : ''} role={defaultError ? 'alert' : undefined}>{defaultError || `JSON ${value.type} · applied when the caller omits “${value.name || 'this argument'}”`}</small>
    </div>}
  </div>;
}
