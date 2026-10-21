import type { KeyboardEvent } from 'react';
import { useState } from 'react';
import type { MachineTransition, RunResult, StateMachine } from './types';
import { addGuardedTransition, moveStateTransition, patchStateTransition, removeStateTransition } from './stateMachineEditing';

type Point={x:number;y:number};
type Layout={positions:Map<string,Point>;width:number;height:number};

export function layoutStateMachine(machine:StateMachine):Layout{
  const stateIds=new Set(machine.states.map(state=>state.id));
  const levels=new Map<string,number>();
  const queue:string[]=[];
  if(stateIds.has(machine.initial)){levels.set(machine.initial,0);queue.push(machine.initial)}
  while(queue.length){const id=queue.shift()!;const nextLevel=levels.get(id)!+1;for(const edge of machine.transitions){if(edge.from===id&&stateIds.has(edge.to)&&!levels.has(edge.to)){levels.set(edge.to,nextLevel);queue.push(edge.to)}}}
  const maxReachable=Math.max(-1,...levels.values());
  for(const state of machine.states)if(!levels.has(state.id))levels.set(state.id,maxReachable+1);
  const columns=new Map<number,string[]>();
  for(const state of machine.states){const level=levels.get(state.id)!;const column=columns.get(level)??[];column.push(state.id);columns.set(level,column)}
  const positions=new Map<string,Point>();
  for(const [level,ids] of columns)ids.forEach((id,index)=>positions.set(id,{x:24+level*250,y:20+index*94}));
  const maxLevel=Math.max(0,...columns.keys());
  const maxRows=Math.max(1,...[...columns.values()].map(ids=>ids.length));
  return{positions,width:Math.max(620,48+(maxLevel+1)*250),height:Math.max(120,40+maxRows*94)};
}

function transitionGeometry(from:Point,to:Point,sourceId:string,targetId:string){
  if(sourceId===targetId){return{d:`M ${from.x+174} ${from.y+16} C ${from.x+230} ${from.y-24}, ${from.x+230} ${from.y+74}, ${from.x+174} ${from.y+42}`,x:from.x+202,y:from.y-8}}
  const startX=from.x+174,startY=from.y+29,endX=to.x,endY=to.y+29;
  if(endX<=startX){const side=Math.max(startX,endX)+44;return{d:`M ${startX} ${startY} C ${side} ${startY-42}, ${side} ${endY-42}, ${endX} ${endY}`,x:side-8,y:(startY+endY)/2-8}}
  const bend=(startX+endX)/2;
  return{d:`M ${startX} ${startY} C ${bend} ${startY}, ${bend} ${endY}, ${endX} ${endY}`,x:bend,y:(startY+endY)/2-7};
}

export function StateMachineMap({machine,selected,run,onSelect,onChange}:{machine:StateMachine;selected:string;run:RunResult|null;onSelect:(id:string)=>void;onChange:(machine:StateMachine)=>void}){
  const [selectedTransition,setSelectedTransition]=useState<number|null>(null);
  const layout=layoutStateMachine(machine);
  const keySelect=(event:KeyboardEvent<SVGGElement>,id:string)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(id)}};
  const byId=new Map(machine.states.map(state=>[state.id,state]));
  const edge=selectedTransition===null?undefined:machine.transitions[selectedTransition];
  const selectedIndex=selectedTransition??-1;
  const source=byId.get(selected);
  const outgoing=machine.transitions.filter(item=>item.from===edge?.from);
  const isFallback=Boolean(edge&&edge.condition===undefined);
  const otherFallback=Boolean(edge&&outgoing.some(item=>item!==edge&&item.condition===undefined));
  const changeEdge=(patch:Partial<MachineTransition>)=>{if(selectedTransition===null)return;const current=machine.transitions[selectedTransition];const next=patchStateTransition(machine,selectedTransition,patch);if(!next)return;const target=patch.to??current.to;const condition=patch.condition===undefined?current.condition:(patch.condition.trim()||undefined);const relocated=next.transitions.findIndex(item=>item.from===current.from&&item.to===target&&item.condition===condition);if(relocated>=0)setSelectedTransition(relocated);onChange(next)};
  const addTransition=()=>{if(!source)return;const target=machine.states.find(state=>state.id!==source.id);if(!target)return;const added=addGuardedTransition(machine,source.id,target.id);if(added){onChange(added.machine);setSelectedTransition(added.index)}};
  const deleteTransition=()=>{if(selectedTransition===null)return;const next=removeStateTransition(machine,selectedTransition);if(next)onChange(next);setSelectedTransition(null)};
  const shiftTransition=(direction:-1|1)=>{if(selectedTransition===null)return;const next=moveStateTransition(machine,selectedTransition,direction);if(!next)return;const moved=next.transitions.findIndex(item=>item===machine.transitions[selectedTransition]);onChange(next);setSelectedTransition(moved)};
  const keyEdge=(event:KeyboardEvent<SVGGElement>,index:number)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setSelectedTransition(index)}};
  return <div className={`state-machine-overview ${edge?'has-selected-edge':''}`} aria-label="State machine transition overview">
    <div className="state-machine-overview-head"><strong>TRANSITION OVERVIEW</strong><span>{machine.states.length} STATES · {machine.transitions.length} TRANSITIONS</span><button type="button" className="state-map-add-transition" disabled={!source||source.final||machine.states.length<2} onClick={addTransition} title="Add a safe False-guarded transition from the selected state">+ TRANSITION</button></div>
    <div className="state-machine-overview-viewport"><svg role="group" aria-label="State machine graph" viewBox={`0 0 ${layout.width} ${layout.height}`} preserveAspectRatio="xMidYMid meet" style={{minWidth:`${Math.min(layout.width,860)}px`}}>
      <defs><marker id="state-map-arrow" markerWidth="7" markerHeight="7" refX="5" refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="#82947b"/></marker></defs>
      {machine.transitions.map((transition,index)=>{const from=layout.positions.get(transition.from),to=layout.positions.get(transition.to);if(!from||!to)return null;const geometry=transitionGeometry(from,to,transition.from,transition.to);const condition=transition.condition?.trim()||'Always';const selectedEdge=index===selectedTransition;return <g className={`state-map-edge ${selectedEdge?'selected':''}`} key={`${transition.from}-${transition.to}-${index}`} role="button" tabIndex={0} aria-label={`Edit transition ${byId.get(transition.from)?.label??transition.from} to ${byId.get(transition.to)?.label??transition.to}; ${condition}`} aria-pressed={selectedEdge} onClick={()=>setSelectedTransition(index)} onKeyDown={event=>keyEdge(event,index)}><path className="state-map-edge-hit" d={geometry.d}/><path d={geometry.d} markerEnd="url(#state-map-arrow)"/><text x={geometry.x} y={geometry.y}>{condition.length>22?`${condition.slice(0,20)}…`:condition}</text><title>{`${byId.get(transition.from)?.label??transition.from} → ${byId.get(transition.to)?.label??transition.to}: ${condition}`}</title></g>})}
      {machine.states.map((state,index)=>{const point=layout.positions.get(state.id)!;const status=run?.activities?.[state.id]?.status??'idle';const isSelected=state.id===selected;return <g key={state.id} role="button" tabIndex={0} aria-label={`${state.label||state.id}${state.id===machine.initial?', initial':''}${state.final?', final':''}; ${state.activities.length} activities`} aria-pressed={isSelected} className={`state-map-node ${state.id===machine.initial?'initial':''} ${state.final?'final':''} ${isSelected?'selected':''} ${status}`} transform={`translate(${point.x} ${point.y})`} onClick={()=>{setSelectedTransition(null);onSelect(state.id)}} onKeyDown={event=>keySelect(event,state.id)}>
        <rect width="174" height="58" rx="7"/><text className="state-map-number" x="10" y="15">{String(index+1).padStart(2,'0')}</text><text className="state-map-label" x="10" y="34">{(state.label||state.id).slice(0,22)}</text><text className="state-map-meta" x="10" y="49">{state.id===machine.initial?'INITIAL · ':''}{state.final?'FINAL · ':''}{state.activities.length} ACTIVITIES</text><title>{state.label||state.id}</title>
      </g>})}
    </svg></div>
    {edge&&<div className="state-map-transition-editor" aria-label="Selected transition editor"><label>FROM <strong>{byId.get(edge.from)?.label??edge.from}</strong></label><span aria-hidden="true">→</span><label>TO <select aria-label="Selected transition destination" value={edge.to} onChange={event=>changeEdge({to:event.target.value})}>{machine.states.map(state=><option key={state.id} value={state.id}>{state.label||state.id}</option>)}</select></label><label className="state-map-condition">GUARD <input aria-label="Selected transition guard; blank means fallback" placeholder="Expression · blank = fallback" value={edge.condition??''} disabled={otherFallback} title={otherFallback?'Another fallback already exists for this state':''} onChange={event=>changeEdge({condition:event.target.value})}/></label><div className="state-map-edge-actions"><button type="button" aria-label="Move transition earlier" disabled={isFallback||!machine.transitions.slice(0,selectedIndex).some(item=>item.from===edge.from)} onClick={()=>shiftTransition(-1)}>↑</button><button type="button" aria-label="Move transition later" disabled={isFallback||!machine.transitions.slice(selectedIndex+1).some(item=>item.from===edge.from)} onClick={()=>shiftTransition(1)}>↓</button><button type="button" aria-label="Remove selected transition" onClick={deleteTransition}>REMOVE</button></div></div>}
  </div>;
}
