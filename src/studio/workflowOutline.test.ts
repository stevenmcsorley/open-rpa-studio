import { describe,expect,it } from 'vitest';
import { flattenWorkflowOutline } from './workflowOutlineModel';

describe('nested workflow outline',()=>{
  it('lists activity IDs and branch context through nested control flow',()=>{
    const entries=flattenWorkflowOutline([
      {id:'check',type:'if',condition:'ready',then:[{id:'loop',type:'for_each',body:[{id:'write',type:'file_write',label:'Save output'}]}],else:[{id:'log',type:'log'}]},
    ]);
    expect(entries).toEqual([
      {id:'check',label:'If',context:'',depth:0,kind:'If'},
      {id:'loop',label:'For Each',context:'If · Then',depth:1,kind:'For Each'},
      {id:'write',label:'Save Output',context:'If · Then / For Each · Each item',depth:2,kind:'File Write'},
      {id:'log',label:'Log',context:'If · Else',depth:1,kind:'Log'},
    ]);
  });

  it('includes switch case and default activities without inferring empty branches',()=>{
    const entries=flattenWorkflowOutline([{id:'route',type:'switch',cases:[{value:'urgent',activities:[{id:'notify',type:'http_request'}]},{value:2,activities:[]}],default:[{id:'noop',type:'log'}]}]);
    expect(entries.map(entry=>[entry.id,entry.context])).toEqual([
      ['route',''],['notify','Switch · Case urgent'],['noop','Switch · Default'],
    ]);
  });
});
