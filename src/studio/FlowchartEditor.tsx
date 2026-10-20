import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent } from 'react';
import type { Flowchart, FlowNode, FlowTransition } from './types';

type Point={x:number;y:number};
type Rect=Point&{width:number;height:number};
const useSafeLayoutEffect=typeof window==='undefined'?useEffect:useLayoutEffect;

export function draggedPosition(origin:Point,start:Point,current:Point,zoom:number):Point{return{x:Math.max(0,Math.min(10_000,origin.x+(current.x-start.x)/zoom)),y:Math.max(0,Math.min(10_000,origin.y+(current.y-start.y)/zoom))}}

function initialLayout(graph:Flowchart):Map<string,Point>{
  const nodes=new Map(graph.nodes.map(node=>[node.id,node]));
  const outgoing=new Map<string,FlowTransition[]>();
  for(const edge of graph.transitions){const edges=outgoing.get(edge.from)??[];edges.push(edge);outgoing.set(edge.from,edges)}
  const points=new Map<string,Point>();
  const start=nodes.get(graph.start);
  if(start)points.set(start.id,{x:440,y:36});
  const queue=start?[start.id]:[];
  while(queue.length){
    const from=queue.shift()!;const node=nodes.get(from)!;const base=points.get(from)!;
  const edges=[...(outgoing.get(from)??[])].sort((a,b)=>Number(a.when!=='true')-Number(b.when!=='true'));
    for(const edge of edges){if(points.has(edge.to))continue;const offset=node.kind==='decision'?(edge.when==='true'?-210:210):0;points.set(edge.to,{x:Math.max(24,base.x+offset),y:base.y+(node.kind==='decision'?210:166)});queue.push(edge.to)}
  }
  graph.nodes.forEach((node,index)=>{if(!points.has(node.id))points.set(node.id,{x:40+(index%3)*330,y:36+Math.floor(index/3)*220})});
  return points;
}

export function FlowchartEditor({graph,selected,onSelect,onAddNode,onConnect,onRemove,onPositionChange}:{
  graph:Flowchart;selected:string;onSelect:(id:string)=>void;onAddNode:(kind:'decision'|'end')=>void;
  onConnect:(from:string,when:'always'|'true'|'false',to:string|null)=>void;onRemove:(id:string)=>void;
  onPositionChange:(id:string,x:number,y:number)=>void;
}){
  const viewport=useRef<HTMLDivElement>(null);
  const refs=useRef(new Map<string,HTMLElement>());
  const drag=useRef<{id:string;pointerX:number;pointerY:number;originX:number;originY:number}|null>(null);
  const [rects,setRects]=useState<Record<string,Rect>>({});
  const [moving,setMoving]=useState<{id:string;point:Point}|null>(null);
  const [zoom,setZoom]=useState(1);
  const layout=useMemo(()=>initialLayout(graph),[graph.nodes,graph.transitions]);
  const positions=useMemo(()=>new Map(graph.nodes.map(node=>[node.id,{x:moving?.id===node.id?moving.point.x:node.x??layout.get(node.id)!.x,y:moving?.id===node.id?moving.point.y:node.y??layout.get(node.id)!.y}])),[graph.nodes,layout,moving]);
  const width=Math.max(920,...[...positions.values()].map(point=>point.x+340));
  const height=Math.max(620,...[...positions.values()].map(point=>point.y+250));
  const nodes=graph.nodes;
  const outgoing=(id:string,when:string)=>graph.transitions.find(edge=>edge.from===id&&(edge.when??'always')===when)?.to??'';
  const nodeTitle=(node:FlowNode):string=>String(node.label||node.activity?.label||node.activity?.type||({start:'Start',decision:'Decision',end:'End'} as Record<string,string>)[node.kind]||node.kind);
  const link=(node:FlowNode,when:'always'|'true'|'false',label:string)=><label className="flowchart-edge" key={when}><span>{label}</span><span className="edge-arrow">→</span><select aria-label={`${nodeTitle(node)} ${label} destination`} value={outgoing(node.id,when)} onChange={event=>onConnect(node.id,when,event.target.value||null)}><option value="">Choose destination</option>{nodes.filter(target=>target.kind!=='start').map(target=><option key={target.id} value={target.id}>{nodeTitle(target)} · {target.id.slice(-6)}</option>)}</select></label>;
  const measure=()=>{const next:Record<string,Rect>={};for(const [id,element] of refs.current){if(element)next[id]={x:element.offsetLeft,y:element.offsetTop,width:element.offsetWidth,height:element.offsetHeight}}setRects(next)};
  useSafeLayoutEffect(()=>{measure();const observer=new ResizeObserver(measure);for(const element of refs.current.values())observer.observe(element);return()=>observer.disconnect()},[graph.nodes,graph.transitions,zoom,moving]);
  const fit=()=>{const view=viewport.current;if(!view)return;setZoom(Math.max(.45,Math.min(1.25,(view.clientWidth-50)/width)))};
  const pathFor=(edge:FlowTransition)=>{const from=rects[edge.from],to=rects[edge.to],source=nodes.find(node=>node.id===edge.from);if(!from||!to||!source)return null;const split=source.kind==='decision'?(edge.when==='true'?.28:.72):.5;const sx=from.x+from.width*split,sy=from.y+from.height,tx=to.x+to.width/2,ty=to.y;const bend=Math.max(50,Math.abs(ty-sy)*.48);return{d:`M ${sx} ${sy} C ${sx} ${sy+bend}, ${tx} ${ty-bend}, ${tx} ${ty}`,labelX:(sx+tx)/2,labelY:(sy+ty)/2,when:edge.when??'always'}};
  const beginDrag=(event:PointerEvent<HTMLDivElement>,node:FlowNode)=>{if(event.button!==0)return;const point=positions.get(node.id)!;onSelect(node.kind==='action'&&node.activity?node.activity.id:node.id);drag.current={id:node.id,pointerX:event.clientX,pointerY:event.clientY,originX:point.x,originY:point.y};event.currentTarget.setPointerCapture(event.pointerId)};
  const moveDrag=(event:PointerEvent<HTMLDivElement>)=>{const active=drag.current;if(!active)return;setMoving({id:active.id,point:draggedPosition({x:active.originX,y:active.originY},{x:active.pointerX,y:active.pointerY},{x:event.clientX,y:event.clientY},zoom)})};
  const finishDrag=()=>{if(drag.current&&moving?.id===drag.current.id)onPositionChange(drag.current.id,Math.round(moving.point.x),Math.round(moving.point.y));drag.current=null;setMoving(null)};
  return <div className="flowchart-canvas" ref={viewport}><div className="flowchart-tools"><strong>FLOWCHART</strong><button onClick={()=>onAddNode('decision')}>+ Decision</button><button onClick={()=>onAddNode('end')}>+ End</button><span>Drag node headers to arrange; edit outgoing connectors on each node.</span><button aria-label="Zoom out" onClick={()=>setZoom(value=>Math.max(.45,value-.1))}>−</button><span className="flowchart-zoom">{Math.round(zoom*100)}%</span><button aria-label="Zoom in" onClick={()=>setZoom(value=>Math.min(1.5,value+.1))}>+</button><button onClick={fit}>Fit</button></div><div className="flowchart-stage" style={{width:width*zoom,height:height*zoom}}><div className="flowchart-stage-content" style={{width,height,transform:`scale(${zoom})`}}>
    <svg className="flowchart-links" width={width} height={height} aria-label="Flowchart transitions"><defs><marker id="flowchart-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#86b779"/></marker></defs>{graph.transitions.map((edge,index)=>{const path=pathFor(edge);return path?<g key={`${edge.from}-${edge.when}-${edge.to}-${index}`}><path d={path.d} fill="none" stroke="#71876a" strokeWidth="2" markerEnd="url(#flowchart-arrow)"/><text x={path.labelX} y={path.labelY} fill="#bac7b4" fontSize="10" textAnchor="middle">{edge.when==='true'?'True':edge.when==='false'?'False':''}</text></g>:null})}</svg>
    {nodes.map(node=>{const point=positions.get(node.id)!;return <article ref={element=>{if(element)refs.current.set(node.id,element);else refs.current.delete(node.id)}} style={{left:point.x,top:point.y}} className={`flowchart-node ${node.kind} ${selected===node.id||selected===node.activity?.id?'selected':''}`} key={node.id}>
      <div role="button" tabIndex={0} className="flowchart-node-title" onPointerDown={event=>beginDrag(event,node)} onPointerMove={moveDrag} onPointerUp={finishDrag} onPointerCancel={finishDrag} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(node.kind==='action'&&node.activity?node.activity.id:node.id)}}}><span className="flowchart-kind">{node.kind.toUpperCase()}</span><strong>{nodeTitle(node)}</strong>{(node.breakpoint||node.activity?.breakpoint===true)&&<span className="breakpoint-marker" title="Breakpoint">●</span>}<code>{node.id}</code></div>
      {node.kind==='decision'&&<div className="flowchart-edges">{link(node,'true','True')}{link(node,'false','False')}</div>}
      {(node.kind==='start'||node.kind==='action')&&<div className="flowchart-edges">{link(node,'always','Next')}</div>}
      {node.kind!=='start'&&<button className="flowchart-remove" title={`Remove ${nodeTitle(node)}`} onClick={()=>onRemove(node.id)}>Remove node</button>}
    </article>})}
  </div></div></div>;
}
