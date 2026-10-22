import { describe, expect, it } from 'vitest';
import { readRunTrust, runPlanFingerprint, saveRunTrust, isAutoRunTrusted, setAutoRunTrusted } from './runTrust';
import type { ExecutionPlan } from './executionPlan';

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
  };
}

const plan: ExecutionPlan = {
  actions: [{ id: 'nav', scope: 'Main', type: 'browser_navigate', label: 'Navigate', detail: 'https://example.org', risk: 'external' }],
  needsNetwork: true,
  needsDesktop: false,
  hasDestructiveActions: false,
};

describe('trusted workflow run preferences', () => {
  it('stores grants locally by project and workflow, without exposing secrets', () => {
    const storage = memoryStorage();
    const trust = { fingerprint: runPlanFingerprint(plan), network: true, desktop: false, destructive: false };
    saveRunTrust(storage, 'C:/Private/Project', 'Publisher', trust);
    expect(readRunTrust(storage, 'C:/Private/Project', 'Publisher')).toEqual(trust);
    expect(readRunTrust(storage, 'C:/Other/Project', 'Publisher')).toBeNull();
  });

  it('changes fingerprint when a permission-relevant action changes', () => {
    expect(runPlanFingerprint(plan)).not.toBe(runPlanFingerprint({ ...plan, actions: [{ ...plan.actions[0], detail: 'https://different.example' }] }));
    expect(runPlanFingerprint(plan)).not.toBe(runPlanFingerprint({ ...plan, hasDestructiveActions: true }));
  });

  it('keeps automatic trusted runs off until explicitly enabled', () => {
    const storage = memoryStorage();
    expect(isAutoRunTrusted(storage)).toBe(false);
    setAutoRunTrusted(storage, true);
    expect(isAutoRunTrusted(storage)).toBe(true);
  });
});
