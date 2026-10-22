import type { ExecutionPlan } from './executionPlan';

export type RunTrust = {
  fingerprint: string;
  network: boolean;
  desktop: boolean;
  destructive: boolean;
};

const STORAGE_PREFIX = 'openrpa.run-trust.v1:';
const AUTO_RUN_KEY = 'openrpa.auto-run-trusted.v1';

export function runTrustStorageKey(projectRoot: string, workflowName: string): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(projectRoot)}:${encodeURIComponent(workflowName)}`;
}

export function runPlanFingerprint(plan: ExecutionPlan, workflows: unknown = {}): string {
  const material = JSON.stringify({
    actions: plan.actions.map(({ id, scope, type, detail, risk }) => ({ id, scope, type, detail, risk })),
    needsNetwork: plan.needsNetwork,
    needsDesktop: plan.needsDesktop,
    hasDestructiveActions: plan.hasDestructiveActions,
    workflows,
  });
  // This is a local change detector, not an authorization token or security boundary.
  let hash = 14695981039346656037n;
  const mask = (1n << 64n) - 1n;
  for (const byte of new TextEncoder().encode(material)) {
    hash ^= BigInt(byte);
    hash = (hash * 1099511628211n) & mask;
  }
  return hash.toString(16).padStart(16, '0');
}

export function readRunTrust(storage: Pick<Storage, 'getItem'>, projectRoot: string, workflowName: string): RunTrust | null {
  try {
    const raw = storage.getItem(runTrustStorageKey(projectRoot, workflowName));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<RunTrust>;
    if (typeof value.fingerprint !== 'string' || typeof value.network !== 'boolean' || typeof value.desktop !== 'boolean' || typeof value.destructive !== 'boolean') return null;
    return value as RunTrust;
  } catch {
    return null;
  }
}

export function saveRunTrust(storage: Pick<Storage, 'setItem'>, projectRoot: string, workflowName: string, trust: RunTrust): void {
  storage.setItem(runTrustStorageKey(projectRoot, workflowName), JSON.stringify(trust));
}

export function isAutoRunTrusted(storage: Pick<Storage, 'getItem'>): boolean {
  return storage.getItem(AUTO_RUN_KEY) === 'true';
}

export function setAutoRunTrusted(storage: Pick<Storage, 'setItem'>, value: boolean): void {
  storage.setItem(AUTO_RUN_KEY, value ? 'true' : 'false');
}
