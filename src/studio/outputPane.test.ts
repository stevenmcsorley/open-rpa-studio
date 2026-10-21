import { describe,expect,it } from 'vitest';
import { adjustOutputHeight,DEFAULT_OUTPUT_HEIGHT,maximumOutputHeight,MAX_OUTPUT_HEIGHT,MIN_OUTPUT_HEIGHT } from './outputPane';

describe('output pane sizing',()=>{
  it('resizes in either direction and respects the configured limits',()=>{
    expect(adjustOutputHeight(DEFAULT_OUTPUT_HEIGHT,80)).toBe(298);
    expect(adjustOutputHeight(DEFAULT_OUTPUT_HEIGHT,-80)).toBe(MIN_OUTPUT_HEIGHT);
    expect(adjustOutputHeight(MAX_OUTPUT_HEIGHT,40)).toBe(MAX_OUTPUT_HEIGHT);
    expect(adjustOutputHeight(MIN_OUTPUT_HEIGHT,-40)).toBe(MIN_OUTPUT_HEIGHT);
  });

  it('rounds fractional sizes and rejects non-finite inputs safely',()=>{
    expect(adjustOutputHeight(218.2,10.4)).toBe(229);
    expect(adjustOutputHeight(Number.NaN,10)).toBe(DEFAULT_OUTPUT_HEIGHT);
    expect(adjustOutputHeight(218,Number.POSITIVE_INFINITY)).toBe(DEFAULT_OUTPUT_HEIGHT);
  });

  it('keeps the minimum designer height available on shorter windows',()=>{
    expect(maximumOutputHeight(650)).toBe(183);
    expect(maximumOutputHeight(900)).toBe(433);
    expect(maximumOutputHeight(1200)).toBe(MAX_OUTPUT_HEIGHT);
    expect(adjustOutputHeight(180,20,183)).toBe(183);
  });
});
