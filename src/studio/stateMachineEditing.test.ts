import { describe,expect,it } from 'vitest';
import type { StateMachine } from './types';
import { addGuardedTransition,moveStateTransition,patchStateTransition,removeStateTransition } from './stateMachineEditing';

const machine:StateMachine={initial:'start',states:[
  {id:'start',label:'Start',activities:[]},{id:'review',label:'Review',activities:[]},{id:'done',label:'Done',final:true,activities:[]},
],transitions:[{from:'start',to:'review',condition:'approved'},{from:'start',to:'done'}]};

describe('state-machine graph transition editing',()=>{
  it('inserts a new safe guard before its fallback and selects its index',()=>{
    const result=addGuardedTransition(machine,'start','done');
    expect(result?.index).toBe(1);
    expect(result?.machine.transitions).toEqual([
      {from:'start',to:'review',condition:'approved'},
      {from:'start',to:'done',condition:'False'},
      {from:'start',to:'done'},
    ]);
    expect(addGuardedTransition(machine,'done','start')).toBeNull();
    expect(addGuardedTransition(machine,'start','missing')).toBeNull();
  });

  it('edits an edge and moves a new unconditional fallback to the end',()=>{
    expect(patchStateTransition(machine,0,{to:'done'})?.transitions[0]).toEqual({from:'start',to:'done',condition:'approved'});
    const guardedOnly:StateMachine={...machine,transitions:[machine.transitions[0]]};
    const changed=patchStateTransition(guardedOnly,0,{to:'done',condition:'  '});
    expect(changed?.transitions).toEqual([
      {from:'start',to:'done'},
    ]);
    expect(patchStateTransition(machine,0,{condition:''})).toBeNull();
  });

  it('moves guards within their source order but never past an unconditional fallback',()=>{
    const withThree:StateMachine={...machine,transitions:[...machine.transitions.slice(0,1),{from:'start',to:'review',condition:'urgent'},machine.transitions[1]]};
    expect(moveStateTransition(withThree,1,-1)?.transitions.map(edge=>edge.condition)).toEqual(['urgent','approved',undefined]);
    expect(moveStateTransition(withThree,1,1)).toBeNull();
    expect(moveStateTransition(withThree,2,-1)).toBeNull();
  });

  it('removes an edge without mutating the source machine',()=>{
    const updated=removeStateTransition(machine,0);
    expect(updated?.transitions).toEqual([{from:'start',to:'done'}]);
    expect(machine.transitions).toHaveLength(2);
    expect(removeStateTransition(machine,99)).toBeNull();
  });
});
