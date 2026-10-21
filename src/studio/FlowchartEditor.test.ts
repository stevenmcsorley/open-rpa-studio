import { describe, expect, it } from 'vitest';
import { fitFlowchartZoom, minimapScrollTarget } from './FlowchartEditor';

describe('flowchart minimap navigation', () => {
  it('centers the viewport on the selected graph point at the current zoom', () => {
    expect(minimapScrollTarget(
      { x: 200, y: 100 },
      { left: 100, top: 50, width: 200, height: 100 },
      { x: 1000, y: 500 },
      0.8,
      { x: 400, y: 200 },
    )).toEqual({ x: 200, y: 100 });
  });

  it('does not request a negative scroll near the graph origin', () => {
    expect(minimapScrollTarget(
      { x: 100, y: 50 },
      { left: 100, top: 50, width: 200, height: 100 },
      { x: 1000, y: 500 },
      1,
      { x: 800, y: 400 },
    )).toEqual({ x: 0, y: 0 });
  });

  it('fits both graph dimensions and keeps large graphs readable', () => {
    expect(fitFlowchartZoom({ x: 900, y: 1000 }, { x: 1000, y: 1000 })).toBeCloseTo(0.89);
    expect(fitFlowchartZoom({ x: 10000, y: 10000 }, { x: 1000, y: 1000 })).toBe(0.35);
  });
});
