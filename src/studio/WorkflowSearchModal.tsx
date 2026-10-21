import { useMemo, useState } from 'react';
import { ArrowRight, Search, X } from 'lucide-react';
import type { Workflow } from './types';
import { searchWorkflows } from './workflowSearch';
import type { WorkflowSearchResult } from './workflowSearch';

export function WorkflowSearchModal({ workflows, onClose, onNavigate }: {
  workflows: Record<string, Workflow>;
  onClose: () => void;
  onNavigate: (result: WorkflowSearchResult) => void;
}) {
  const [query, setQuery] = useState('');
  const results = useMemo(() => searchWorkflows(workflows, query), [workflows, query]);
  return <div className="modal-backdrop workflow-search-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="workflow-search-modal" role="dialog" aria-modal="true" aria-labelledby="workflow-search-title">
      <header><div><Search size={17}/><strong id="workflow-search-title">Find in project</strong></div><button className="tiny-icon" aria-label="Close project search" onClick={onClose}><X size={16}/></button></header>
      <label className="workflow-search-input"><Search size={16}/><input autoFocus aria-label="Search workflows" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search activities, expressions, paths and labels"/><kbd>Esc</kbd></label>
      <div className="workflow-search-summary" aria-live="polite">{query.trim().length < 2 ? 'Type at least two characters to search this project.' : `${results.length} result${results.length === 1 ? '' : 's'} across ${Object.keys(workflows).length} workflow${Object.keys(workflows).length === 1 ? '' : 's'}`}</div>
      <div className="workflow-search-results" role="listbox" aria-label="Project search results">
        {query.trim().length >= 2 && results.length === 0 && <p className="workflow-search-empty">No matching workflow content.</p>}
        {results.map((result, index) => <button type="button" role="option" aria-selected="false" key={`${result.workflowName}:${result.targetId}:${result.matchedIn}:${index}`} onClick={() => onNavigate(result)}>
          <span className="workflow-search-result-copy"><strong>{result.title}</strong><small>{result.workflowName} · {result.context} · {result.matchedIn}</small><code>{result.preview}</code></span><ArrowRight size={15}/>
        </button>)}
      </div>
      <footer><span><kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>F</kbd> to search · Results are limited to 100.</span><button className="toolbar-btn" onClick={onClose}>Close</button></footer>
    </section>
  </div>;
}
