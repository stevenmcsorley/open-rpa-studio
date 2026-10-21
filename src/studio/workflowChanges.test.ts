import { describe,expect,it } from 'vitest';
import type { BridgeResult,Workflow } from './types';
import { changedWorkflowNames,workflowChangeNotice } from './workflowChanges';

const workflow=(name:string):Workflow=>({format:'openrpa.workflow',formatVersion:1,name,variables:[],arguments:[],activities:[]});
const project=(workflows:Record<string,Workflow>):BridgeResult=>({root:'fixture',project:{format:'openrpa.project',formatVersion:1,name:'Fixture',main:'Main',workflows:Object.fromEntries(Object.keys(workflows).map(name=>[name,`${name}.json`]))},workflows});

describe('external workflow changes',()=>{
  it('detects exactly which workflow was created, edited, or removed',()=>{
    const before=project({Main:workflow('Main'),Old:workflow('Old')});
    const after=project({Main:workflow('Main'),Old:workflow('Old edited'),New:workflow('New')});
    expect(changedWorkflowNames(before,after)).toEqual(['Old','New']);
    expect(changedWorkflowNames(after,project({Main:workflow('Main'),New:workflow('New')}))).toEqual(['Old']);
  });
  it('uses clear status text for newly created and updated workflows',()=>{
    const before=project({Main:workflow('Main')});
    const created=project({Main:workflow('Main'),Inventory:workflow('Inventory')});
    expect(workflowChangeNotice('Inventory',before,created)).toBe('MCP created “Inventory” · opened it');
    expect(workflowChangeNotice('Main',before,project({Main:workflow('Main edited')}))).toBe('Workflow “Main” updated from an external editor or MCP');
  });
});
