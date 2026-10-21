import { describe,expect,it } from 'vitest';
import { adjustCanvasZoom,MAX_CANVAS_ZOOM,MIN_CANVAS_ZOOM } from './canvasZoom';

describe('sequence canvas zoom',()=>{
  it('changes in stable ten-percent increments',()=>{
    expect(adjustCanvasZoom(1,1)).toBe(1.1);
    expect(adjustCanvasZoom(1,-1)).toBe(0.9);
  });
  it('clamps zoom to readable bounds',()=>{
    expect(adjustCanvasZoom(MAX_CANVAS_ZOOM,1)).toBe(MAX_CANVAS_ZOOM);
    expect(adjustCanvasZoom(MIN_CANVAS_ZOOM,-1)).toBe(MIN_CANVAS_ZOOM);
  });
});
