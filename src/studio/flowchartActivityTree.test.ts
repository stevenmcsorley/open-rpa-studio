import { describe,expect,it } from 'vitest';
import type { Flowchart } from './types';
import { appendFlowchartActionBranchActivity,findFlowchartActionContaining,patchFlowchartActionActivity,removeFlowchartNestedActivity } from './flowchartActivityTree';

const graph:Flowchart={start:'start',nodes:[
  {id:'start',kind:'start'},
  {id:'node-if',kind:'action',label:'Check',activity:{id:'if-1',type:'if',condition:'ready',then:[{id:'log-1',type:'log',message:'before'}],else:[]}},
  {id:'end',kind:'end'},
],transitions:[{from:'start',to:'node-if'},{from:'node-if',to:'end'}]};

describe('nested activities in flowchart action nodes',()=>{
  it('locates a nested activity and patches its fields without changing the source graph',()=>{
    expect(findFlowchartActionContaining(graph,'log-1')?.id).toBe('node-if');
    const updated=patchFlowchartActionActivity(graph,'log-1',{message:'after'});
    expect(updated?.nodes[1].activity?.then).toEqual([{id:'log-1',type:'log',message:'after'}]);
    expect(graph.nodes[1].activity?.then).toEqual([{id:'log-1',type:'log',message:'before'}]);
  });

  it('appends a new activity to the exact nested branch',()=>{
    const updated=appendFlowchartActionBranchActivity(graph,'if-1','then',{id:'wait-1',type:'wait'});
    expect(updated?.nodes[1].activity?.then).toEqual([
      {id:'log-1',type:'log',message:'before'},{id:'wait-1',type:'wait'},
    ]);
    expect(appendFlowchartActionBranchActivity(graph,'missing','then',{id:'x',type:'log'})).toBeNull();
  });

  it('removes a nested child while preserving its containing flowchart action',()=>{
    const result=removeFlowchartNestedActivity(graph,'log-1');
    expect(result?.containerId).toBe('if-1');
    expect(result?.graph.nodes[1].id).toBe('node-if');
    expect(result?.graph.nodes[1].activity?.then).toEqual([]);
    expect(removeFlowchartNestedActivity(graph,'if-1')).toBeNull();
  });
});
