import { Plus, Workflow as WorkflowIcon, X } from 'lucide-react';

type Props = {
  tabs: string[];
  workflows: string[];
  active: string;
  live?: boolean;
  dirty: (name: string) => boolean;
  onSelect: (name: string) => void;
  onClose: (name: string) => void;
  onNew: () => void;
  onOpen: (name: string) => void;
};

export function WorkflowTabs({ tabs, workflows, active, live = false, dirty, onSelect, onClose, onNew, onOpen }: Props) {
  const closed = workflows.filter(name => !tabs.includes(name));
  return <div className="tabbar" role="tablist" aria-label="Open workflows">
    <div className="workflow-tab-list">
      {tabs.map(name => <div className={`tab${name === active ? ' active' : ''}`} role="presentation" key={name}>
        <button className="workflow-tab-select" role="tab" aria-selected={name === active} onClick={() => onSelect(name)} title={name}>
          <WorkflowIcon size={14}/><span>{name}</span>{live && name === active && <span className="workflow-live-indicator" role="status" aria-label="Workflow is updating" title="Live workflow updates"/>}{dirty(name) && <span className="unsaved" title="Unsaved changes">●</span>}
        </button>
        <button className="workflow-tab-close" aria-label={`Close ${name} workflow tab`} title="Close tab" onClick={() => onClose(name)}><X size={13}/></button>
      </div>)}
    </div>
    <button className="tab-add" aria-label="New workflow" title="New workflow" onClick={onNew}><Plus size={15}/></button>
    <select className="workflow-tab-open" aria-label="Open workflow" value="" disabled={!closed.length} onChange={event => { if (event.target.value) onOpen(event.target.value); }}>
      <option value="">Open workflow…</option>{closed.map(name => <option value={name} key={name}>{dirty(name) ? '● ' : ''}{name}</option>)}
    </select>
  </div>;
}
