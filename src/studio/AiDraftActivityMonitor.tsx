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
  for (let index = 0; index < milestones.length; index++) if (!milestones[index].done(events)) return index;
  return milestones.length - 1;
}

function failedMilestone(events: AiDraftEvent[]): number | null {
  const failureIndex = events.findIndex(event => event.type === 'draft.failed' || event.type === 'workflow.validation_failed');
  if (failureIndex < 0) return null;
  const preceding = events.slice(0, failureIndex);
  if (events[failureIndex].type === 'workflow.validation_failed') return 4;
  if (preceding.some(event => event.type === 'workflow.parsing')) return 3;
  if (preceding.some(event => event.type === 'provider.connected')) return 2;
  if (preceding.some(event => event.type === 'provider.connecting')) return 1;
  if (preceding.some(event => event.type === 'generation.started')) return 2;
  return 0;
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

function issueRows(events: AiDraftEvent[]) {
  const issues = new Map<string, { kind: 'warning' | 'error'; code?: string; activityId?: string; message: string }>();
  for (const event of events) {
    if (event.type === 'generation.fallback') {
      const message = event.metadata.message;
      if (typeof message === 'string' && message.trim()) issues.set(`warning:${message}`, { kind: 'warning', message: message.slice(0, 500) });
    }
    if (event.type === 'draft.failed') {
      const message = event.metadata.message;
      issues.set(`error:${String(message ?? 'Draft generation failed')}`, { kind: 'error', message: typeof message === 'string' ? message.slice(0, 1000) : 'Draft generation failed. Check the provider and request settings.' });
    }
    if (event.type !== 'workflow.validation_failed') continue;
    const activityId = typeof event.metadata.activityId === 'string' ? event.metadata.activityId.slice(0, 128) : '';
    const problems = Array.isArray(event.metadata.problems) ? event.metadata.problems : [];
    if (!problems.length) {
      const message = `Workflow validation failed${Number.isFinite(event.metadata.problemCount) ? ` (${event.metadata.problemCount} issue${event.metadata.problemCount === 1 ? '' : 's'})` : ''}.`;
      issues.set(`error:${activityId}:${message}`, { kind: 'error', activityId, message });
      continue;
    }
    for (const problem of problems.slice(0, 50)) {
      if (!problem || typeof problem !== 'object') continue;
      const item = problem as Record<string, unknown>;
      const code = typeof item.code === 'string' ? item.code.slice(0, 100) : '';
      const message = typeof item.message === 'string' ? item.message.slice(0, 500) : 'Workflow validation issue.';
      const itemActivityId = typeof item.activityId === 'string' ? item.activityId.slice(0, 128) : activityId;
      const key = `error:${code}:${itemActivityId}:${message}`;
      issues.set(key, { kind: 'error', code, activityId: itemActivityId, message });
    }
  }
  return [...issues.values()].slice(0, 50);
}

export function AiDraftActivityMonitor({ events, busy, provider, model, executionModel, elapsedSeconds, firstOutputMs, outputText }: Props) {
  const latest = events.at(-1);
  const latestType = String(latest?.type ?? '');
  const failed = events.some(event => event.type === 'draft.failed') || (!events.some(event => event.type === 'workflow.completed') && events.some(event => event.type === 'workflow.validation_failed'));
  const cancelled = events.some(event => event.type === 'draft.cancelled');
  const complete = events.some(event => event.type === 'workflow.completed');
  const activeMilestone = currentMilestone(events);
  const failureStage = failedMilestone(events);
  const rows = activityRows(events);
  const issues = issueRows(events);
  const outputChars = Number([...events].reverse().find(event => event.type === 'generation.output_received')?.metadata.outputCharacters ?? 0);
  const capabilities = events.find(event => event.type === 'model.capabilities_checked')?.metadata;
  const streamSupported = capabilities?.streaming === 'supported';
  const providerConnected = events.some(event => event.type === 'provider.connected');
  const canPreviewIncrementally = executionModel === 'sequence' && streamSupported;
  const modeLabel = executionModel === 'state_machine' ? 'state machine' : executionModel;
  const statusLabel = busy && providerConnected && outputChars === 0
    ? 'Connected · waiting for first output'
    : busy && outputChars > 0 && rows.length === 0
      ? 'Receiving output · waiting for a complete step'
      : busy && rows.length > 0 && latestType === 'generation.output_received'
        ? `Receiving output · ${rows.length} validated step${rows.length === 1 ? '' : 's'}`
        : eventLabels[latestType] ?? (busy ? 'Waiting for provider response' : 'Ready for review');
  const waitingMessage = executionModel !== 'sequence'
    ? 'This graph model is parsed as a complete document; its visual preview appears when generation finishes.'
    : !providerConnected
      ? 'Connecting to the provider. No model output or workflow activities have arrived yet.'
      : !streamSupported
        ? 'This provider returns a complete response; the step preview will appear after generation finishes.'
        : outputChars === 0
          ? 'The provider is connected, but has not sent output yet. No activity has started; the first step will appear after a complete definition passes validation.'
          : 'Waiting for the first complete activity. Partial JSON is held back until it is safe to validate.';

  return <section className="ai-activity-monitor" aria-live="polite" aria-label="AI workflow build progress">
    <header><div><strong>WORKFLOW BUILD</strong><span className={failed ? 'monitor-failed' : cancelled ? 'monitor-cancelled' : complete ? 'monitor-complete' : ''}>{failed ? 'Needs attention' : cancelled ? 'Stopped' : complete ? 'Validated' : busy ? canPreviewIncrementally ? 'Building live' : 'Building' : 'Draft ready'}</span></div><small>{provider} · {model || 'model not selected'} · {modeLabel}</small></header>
    <div className="ai-build-milestones" aria-label="Workflow build stages">
      {milestones.map((milestone, index) => {
        const done = milestone.done(events);
        const failedStage = index === failureStage;
        const active = busy && index === activeMilestone && !done;
        const state = failedStage ? 'failed' : done ? 'done' : active ? 'active' : 'pending';
        return <div className={`ai-build-stage stage-${state}`} key={milestone.label} aria-current={active ? 'step' : undefined}>
          <span>{failedStage ? <AlertCircle size={12}/> : done ? <Check size={12}/> : active ? <LoaderCircle size={12}/> : index + 1}</span><small>{milestone.label}{failedStage ? ' failed' : ''}</small>
        </div>;
      })}
    </div>
    <div className="ai-monitor-stats">
      <div><small>WHAT IT'S DOING</small><strong>{statusLabel}</strong></div>
      <div><small>ELAPSED</small><strong>{elapsedSeconds}s</strong></div>
      <div><small>RECEIVED</small><strong>{outputChars.toLocaleString()} chars</strong></div>
      <div><small>FIRST OUTPUT</small><strong>{firstOutputMs === null ? 'Waiting' : `${(firstOutputMs / 1000).toFixed(1)}s`}</strong></div>
      <div><small>VALID STEPS</small><strong>{rows.filter(row => row.state === 'valid').length}</strong></div>
    </div>
    {busy && !rows.length && <div className="ai-monitor-indeterminate"><LoaderCircle size={14}/><span className="ai-monitor-indeterminate-message">{waitingMessage}</span></div>}
    <div className="ai-monitor-layout">
      <div><h4>BUILD TIMELINE</h4><ol className="ai-event-list">{events.filter(event => event.type !== 'generation.output_received').slice(-24).map((event, index) => <li key={`${event.timestamp}-${index}`} className={`event-${event.phase}`}><span>{eventLabels[event.type] ?? event.type.replaceAll('.', ' · ')}</span><time>{new Date(event.timestamp).toLocaleTimeString()}</time>{typeof event.metadata.message === 'string' && <small>{String(event.metadata.message)}</small>}</li>)}</ol>
        {issues.length > 0 && <section className="ai-monitor-diagnostics" aria-label="Warnings and errors"><h4>WARNINGS &amp; ERRORS <small>{issues.length}</small></h4><ul>{issues.map((issue, index) => <li className={`issue-${issue.kind}`} key={`${issue.code}-${issue.activityId}-${index}`}><strong>{issue.kind === 'error' ? 'Error' : 'Warning'}{issue.code ? ` · ${issue.code}` : ''}{issue.activityId ? ` · ${issue.activityId}` : ''}</strong><span>{issue.message}</span></li>)}</ul></section>}
      </div>
      <div><h4>WORKFLOW STEPS <small>{complete ? 'validated preview' : 'validated as they arrive'}</small></h4>
        {rows.length ? <div className={`ai-live-sequence ${busy ? 'sequence-building' : ''}`}>{rows.map((row, index) => <div className="ai-live-node-wrap" key={`${row.activityId}-${index}`}>
          <article className={`ai-live-node node-${row.state}`}><span className="ai-node-index">{index + 1}</span><div><strong>{row.activityType}</strong><small>{row.activityId}</small></div>{row.state === 'valid' ? <Check size={14}/> : row.state === 'checking' ? <LoaderCircle size={14} className="node-spinner"/> : <AlertCircle size={14}/>}<details><summary>{row.state === 'valid' ? 'Inspect configured step' : row.state === 'checking' ? 'Being checked' : 'Validation details'}</summary><pre>{JSON.stringify(row.state === 'invalid' ? row.problems : row.activity ?? { status: 'Waiting for a complete activity definition' }, null, 2)}</pre></details></article>
          {index < rows.length - 1 && <i aria-hidden="true"/>}
        </div>)}{busy && <div className="ai-live-next-step"><i aria-hidden="true"/><div><strong>Next activity</strong><small>Waiting for a complete definition from the model</small></div><LoaderCircle size={14}/></div>}</div> : <p className="ai-monitor-empty">{busy ? 'The model is connected. No complete activity has arrived yet, so there is no workflow step to animate. Studio will add each step after it is received and validated.' : failed ? 'No complete, valid steps were received. Review the highlighted failed stage and diagnostics.' : 'The validated workflow steps will appear here.'}</p>}
        {outputText && <details className="ai-output-details"><summary>Raw generated text ({outputText.length.toLocaleString()} chars retained)</summary><pre>{outputText}</pre></details>}
      </div>
    </div>
  </section>;
}
