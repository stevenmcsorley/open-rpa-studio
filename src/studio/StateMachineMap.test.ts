import { describe, expect, it } from 'vitest';
import { layoutStateMachine } from './StateMachineMap';
import type { StateMachine } from './types';

const machine:StateMachine={initial:'receive',states:[
  {id:'receive',label:'Receive',activities:[]},
  {id:'review',label:'Review',activities:[]},
  {id:'approve',label:'Approve',activities:[]},
  {id:'reject',label:'Reject',final:true,activities:[]},
  {id:'archived',label:'Archived',final:true,activities:[]},
],transitions:[
  {from:'receive',to:'review'},
  {from:'review',to:'approve',condition:'score >= 80'},
  {from:'review',to:'reject',condition:'score < 80'},
  {from:'approve',to:'review',condition:'needsMoreInfo'},
]};

describe('state-machine overview layout',()=>{
  it('lays reachable transitions into deterministic left-to-right levels',()=>{
    const {positions,width,height}=layoutStateMachine(machine);
    expect(positions.get('receive')).toEqual({x:24,y:20});
    expect(positions.get('review')?.x).toBe(274);
    expect(positions.get('approve')?.x).toBe(524);
    expect(positions.get('reject')?.x).toBe(524);
    expect(width).toBe(1048);
    expect(height).toBe(228);
    expect(layoutStateMachine(machine).positions).toEqual(positions);
  });

  it('places disconnected states after reachable states and ignores unknown targets',()=>{
    const broken:StateMachine={...machine,transitions:[...machine.transitions,{from:'receive',to:'missing'}]};
    const {positions}=layoutStateMachine(broken);
    expect(positions.get('archived')?.x).toBe(774);
    expect(positions.size).toBe(machine.states.length);
  });
});
