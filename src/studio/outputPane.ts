export const DEFAULT_OUTPUT_HEIGHT = 218;
export const MIN_OUTPUT_HEIGHT = 140;
export const MAX_OUTPUT_HEIGHT = 500;
const MIN_APP_HEIGHT = 397;
const FIXED_VERTICAL_CHROME = 60 + 48 + 29;
const MIN_WORKSPACE_HEIGHT = 120;

export function maximumOutputHeight(viewportHeight: number): number {
  const appHeight = Number.isFinite(viewportHeight) ? Math.max(MIN_APP_HEIGHT, viewportHeight) : MIN_APP_HEIGHT;
  return Math.max(MIN_OUTPUT_HEIGHT, Math.min(MAX_OUTPUT_HEIGHT, appHeight - FIXED_VERTICAL_CHROME - MIN_WORKSPACE_HEIGHT));
}

export function adjustOutputHeight(current: number, delta: number, maxHeight = MAX_OUTPUT_HEIGHT): number {
  if (!Number.isFinite(current) || !Number.isFinite(delta)) return DEFAULT_OUTPUT_HEIGHT;
  const boundedMax = Number.isFinite(maxHeight) ? Math.max(MIN_OUTPUT_HEIGHT, Math.min(MAX_OUTPUT_HEIGHT, maxHeight)) : MAX_OUTPUT_HEIGHT;
  return Math.min(boundedMax, Math.max(MIN_OUTPUT_HEIGHT, Math.round(current + delta)));
}
