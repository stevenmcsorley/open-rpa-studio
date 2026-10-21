import type { MachineTransition, StateMachine } from './types';

export type TransitionEditResult={machine:StateMachine;index:number}|null;

export function addGuardedTransition(machine:StateMachine,from:string,to:string):TransitionEditResult{
  const source=machine.states.find(state=>state.id===from);
  if(!source||source.final||!machine.states.some(state=>state.id===to))return null;
  const transitions=[...machine.transitions];
  const fallback=transitions.findIndex(edge=>edge.from===from&&edge.condition===undefined);
  const sourceEdges=transitions.map((edge,index)=>edge.from===from?index:-1).filter(index=>index>=0);
  const index=fallback>=0?fallback:(sourceEdges.at(-1)??transitions.length-1)+1;
  transitions.splice(index,0,{from,to,condition:'False'});
  return{machine:{...machine,transitions},index};
}

export function patchStateTransition(machine:StateMachine,index:number,patch:Partial<MachineTransition>):StateMachine|null{
  const current=machine.transitions[index];
  if(!current)return null;
  if(patch.from!==undefined&&patch.from!==current.from)return null;
  if(patch.to!==undefined&&!machine.states.some(state=>state.id===patch.to))return null;
  const condition=patch.condition===undefined?current.condition:(patch.condition.trim()||undefined);
  const next={...current,...patch,condition};
  const transitions=[...machine.transitions];
  if(condition===undefined){
    const anotherFallback=transitions.some((edge,edgeIndex)=>edgeIndex!==index&&edge.from===current.from&&edge.condition===undefined);
    if(anotherFallback)return null;
    transitions.splice(index,1);
    const sourceEdges=transitions.map((edge,edgeIndex)=>edge.from===current.from?edgeIndex:-1).filter(edgeIndex=>edgeIndex>=0);
    const insertion=(sourceEdges.at(-1)??transitions.length-1)+1;
    transitions.splice(insertion,0,next);
  }else transitions[index]=next;
  return{...machine,transitions};
}

export function removeStateTransition(machine:StateMachine,index:number):StateMachine|null{
  if(!machine.transitions[index])return null;
  return{...machine,transitions:machine.transitions.filter((_edge,edgeIndex)=>edgeIndex!==index)};
}

export function moveStateTransition(machine:StateMachine,index:number,direction:-1|1):StateMachine|null{
  const current=machine.transitions[index];
  if(!current)return null;
  const siblings=machine.transitions.map((edge,edgeIndex)=>edge.from===current.from?edgeIndex:-1).filter(edgeIndex=>edgeIndex>=0);
  const siblingIndex=siblings.indexOf(index);
  const targetSibling=siblings[siblingIndex+direction];
  if(targetSibling===undefined)return null;
  const adjacent=machine.transitions[targetSibling];
  if(direction===1&&adjacent.condition===undefined)return null;
  if(direction===-1&&current.condition===undefined)return null;
  const transitions=[...machine.transitions];
  [transitions[index],transitions[targetSibling]]=[transitions[targetSibling],transitions[index]];
  return{...machine,transitions};
}
