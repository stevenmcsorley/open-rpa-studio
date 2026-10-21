import type { ExecutionPlan } from './executionPlan';

export function AiDraftImpactPreview({ plan }: { plan: ExecutionPlan }) {
  return <section className="draft-impact" aria-label="AI draft execution impact">
    <strong>RUN IMPACT PREVIEW</strong>
    <div className="draft-impact-badges">
      <span>{plan.needsNetwork ? 'Network required' : 'No network'}</span>
      <span>{plan.needsDesktop ? 'Desktop control required' : 'No desktop control'}</span>
      {plan.hasDestructiveActions && <span className="draft-impact-danger">Destructive actions</span>}
    </div>
    {plan.actions.length ? <div className="draft-impact-actions">{plan.actions.map(action => <article
      className={`run-action risk-${action.risk}`} key={`${action.scope}:${action.id}`}>
      <span className="run-risk">{action.risk.toUpperCase()}</span>
      <div><strong>{action.label}<small className="run-action-scope">{action.scope}</small></strong><code>{action.detail}</code></div>
      <small>{action.id}</small>
    </article>)}</div> : <small>No file, network, browser, credential, or desktop effects identified.</small>}
    <small>Configured targets are visible here; expressions and runtime values can change them. Final run permissions are reviewed separately.</small>
  </section>;
}
