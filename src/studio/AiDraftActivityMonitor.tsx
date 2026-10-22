import { AlertCircle, Check, LoaderCircle } from 'lucide-react';
import type { AiDraftEvent } from './bridge';

type Props = {
  events: AiDraftEvent[];
  busy: boolean;
  provider: string;
  model: string;
  executionModel: 'sequence' | 'flowchart' | 'state_machine';
  elapsedSeconds: number;
  firstOutputMs: number | null;
  outputText: string;
};

const eventLabels: Record<string, string> = {
  'request.preparing': 'Preparing request',
  'model.capabilities_checked': 'Checking model capabilities',
  'provider.connecting': 'Connecting to provider',
  'provider.connected': 'Provider connected',
  'generation.started': 'Asking model to draft workflow',
  'generation.output_received': 'Receiving draft output',
  'generation.fallback': 'Changing output mode',
  'generation.completed': 'Draft received',
  'workflow.parsing': 'Reading workflow structure',
  'workflow.activity_discovered': 'Found an activity',
  'workflow.activity_validated': 'Activity passed validation',
  'workflow.validation_failed': 'Validation needs attention',
  'workflow.completed': 'Workflow is valid',
  'draft.failed': 'Draft failed',
  'draft.cancelled': 'Draft stopped',
};

const milestones = [
  { label: 'Prepare', done: (events: AiDraftEvent[]) => events.some(e => e.type === 'request.preparing') },
  { label: 'Connect', done: (events: AiDraftEvent[]) => events.some(e => e.type === 'provider.connected') },
  { label: 'Generate', done: (events: AiDraftEvent[]) => events.some(e => e.type === 'generation.completed') },
  { label: 'Parse', done: (events: AiDraftEvent[]) => events.some(e => e.type === 'workflow.parsing') },
  { label: 'Validate', done: (events: AiDraftEvent[]) => events.some(e => e.type === 'workflow.completed' || e.type === 'workflow.validation_failed') },
  { label: 'Preview', done: (events: AiDraftEvent[]) => events.some(e => e.type === 'workflow.completed') },
];

function currentMilestone(events: AiDraftEvent[]): number {
  if (events.some(e => e.type === 'draft.failed' || e.type === 'draft.cancelled')) return milestones.length - 1;
  for (let index = 0; index < milestones.length; index++) if (!milestones[index].done(events)) return index;
  return milestones.length - 1;
}

function activityRows(events: AiDraftEvent[]) {
  const rows = new Map<string, { activityId: string; activityType: string; activity?: unknown; state: 'checking' | 'valid' | 'invalid'; problems?: unknown }>();
  for (const event of events) {
    if (event.type !== 'workflow.activity_discovered' && event.type !== 'workflow.activity_validated' && event.type !== 'workflow.validation_failed') continue;
    const id = String(event.metadata.activityId ?? `activity-${rows.size + 1}`);
    const previous = rows.get(id);
    const activityType = String(event.metadata.activityType ?? previous?.activityType ?? 'Activity');
    if (event.type === 'workflow.activity_validated') rows.set(id, { activityId: id, activityType, activity: event.metadata.activity, state: 'valid' });
    else if (event.type === 'workflow.validation_failed' && event.metadata.activityId) rows.set(id, { activityId: id, activityType, activity: previous?.activity, state: 'invalid', problems: event.metadata.problems });
    else if (!previous) rows.set(id, { activityId: id, activityType, state: 'checking' });
  }
  return [...rows.values()];
}

export function AiDraftActivityMonitor({ events, busy, provider, model, executionModel, elapsedSeconds, firstOutputMs, outputText }: Props) {
  const latest = events.at(-1);
  const latestType = String(latest?.type ?? '');
  const failed = events.some(event => event.type === 'draft.failed') || (!events.some(event => event.type === 'workflow.completed') && events.some(event => event.type === 'workflow.validation_failed'));
  const cancelled = events.some(event => event.type === 'draft.cancelled');
  const complete = events.some(event => event.type === 'workflow.completed');
  const activeMilestone = currentMilestone(events);
  const rows = activityRows(events);
  const outputChars = Number([...events].reverse().find(event => event.type === 'generation.output_received')?.metadata.outputCharacters ?? 0);
  const capabilities = events.find(event => event.type === 'model.capabilities_checked')?.metadata;
  const streamSupported = capabilities?.streaming === 'supported';
  const canPreviewIncrementally = executionModel === 'sequence' && streamSupported;
  const modeLabel = executionModel === 'state_machine' ? 'state machine' : executionModel;

  return <section className="ai-activity-monitor" aria-live="polite" aria-label="AI workflow build progress">
    <header><div><strong>WORKFLOW BUILD</strong><span className={failed ? 'monitor-failed' : cancelled ? 'monitor-cancelled' : complete ? 'monitor-complete' : ''}>{failed ? 'Needs attention' : cancelled ? 'Stopped' : complete ? 'Validated' : busy ? canPreviewIncrementally ? 'Building live' : 'Building' : 'Draft ready'}</span></div><small>{provider} · {model || 'model not selected'} · {modeLabel}</small></header>
    <div className="ai-build-milestones" aria-label="Workflow build stages">
      {milestones.map((milestone, index) => {
        const done = milestone.done(events);
        const active = busy && index === activeMilestone && !done;
        const state = done ? 'done' : active ? 'active' : 'pending';
        return <div className={`ai-build-stage stage-${state}`} key={milestone.label} aria-current={active ? 'step' : undefined}>
          <span>{done ? <Check size={12}/> : active ? <LoaderCircle size={12}/> : index + 1}</span><small>{milestone.label}</small>
        </div>;
      })}
    </div>
    <div className="ai-monitor-stats">
      <div><small>WHAT IT'S DOING</small><strong>{eventLabels[latestType] ?? (busy ? 'Waiting for provider response' : 'Ready for review')}</strong></div>
      <div><small>ELAPSED</small><strong>{elapsedSeconds}s</strong></div>
      <div><small>RECEIVED</small><strong>{outputChars.toLocaleString()} chars</strong></div>
      <div><small>FIRST OUTPUT</small><strong>{firstOutputMs === null ? 'Waiting' : `${(firstOutputMs / 1000).toFixed(1)}s`}</strong></div>
      <div><small>VALID STEPS</small><strong>{rows.filter(row => row.state === 'valid').length}</strong></div>
    </div>
    {busy && !rows.length && <div className="ai-monitor-indeterminate"><LoaderCircle size={14}/><span>{executionModel !== 'sequence' ? 'This graph model is parsed as a complete document; its visual preview appears when generation finishes.' : streamSupported ? 'Waiting for the first complete activity. Partial JSON is held back until it is safe to validate.' : 'This provider returns a complete response; the step preview will appear after generation finishes.'}</span></div>}
    <div className="ai-monitor-layout">
      <div><h4>BUILD TIMELINE</h4><ol className="ai-event-list">{events.filter(event => event.type !== 'generation.output_received').slice(-24).map((event, index) => <li key={`${event.timestamp}-${index}`} className={`event-${event.phase}`}><span>{eventLabels[event.type] ?? event.type.replaceAll('.', ' · ')}</span><time>{new Date(event.timestamp).toLocaleTimeString()}</time>{typeof event.metadata.message === 'string' && <small>{String(event.metadata.message)}</small>}</li>)}</ol></div>
      <div><h4>WORKFLOW STEPS <small>{complete ? 'validated preview' : 'validated as they arrive'}</small></h4>
        {rows.length ? <div className={`ai-live-sequence ${busy ? 'sequence-building' : ''}`}>{rows.map((row, index) => <div className="ai-live-node-wrap" key={`${row.activityId}-${index}`}>
          <article className={`ai-live-node node-${row.state}`}><span className="ai-node-index">{index + 1}</span><div><strong>{row.activityType}</strong><small>{row.activityId}</small></div>{row.state === 'valid' ? <Check size={14}/> : row.state === 'checking' ? <LoaderCircle size={14} className="node-spinner"/> : <AlertCircle size={14}/>}<details><summary>{row.state === 'valid' ? 'Inspect configured step' : row.state === 'checking' ? 'Being checked' : 'Validation details'}</summary><pre>{JSON.stringify(row.state === 'invalid' ? row.problems : row.activity ?? { status: 'Waiting for a complete activity definition' }, null, 2)}</pre></details></article>
          {index < rows.length - 1 && <i aria-hidden="true"/>}
        </div>)}</div> : <p className="ai-monitor-empty">{busy ? 'The model is working. A step appears here once its complete definition arrives and passes validation.' : failed ? 'No complete, valid steps were received. Review the timeline and diagnostics.' : 'The validated workflow steps will appear here.'}</p>}
        {outputText && <details className="ai-output-details"><summary>Raw generated text ({outputText.length.toLocaleString()} chars retained)</summary><pre>{outputText}</pre></details>}
      </div>
    </div>
  </section>;
}
