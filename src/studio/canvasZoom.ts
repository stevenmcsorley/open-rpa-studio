export const MIN_CANVAS_ZOOM=0.5;
export const MAX_CANVAS_ZOOM=1.5;
export const CANVAS_ZOOM_STEP=0.1;

export function adjustCanvasZoom(current:number,direction:-1|1):number{
  const next=Math.round((current+direction*CANVAS_ZOOM_STEP)*100)/100;
  return Math.max(MIN_CANVAS_ZOOM,Math.min(MAX_CANVAS_ZOOM,next));
}
