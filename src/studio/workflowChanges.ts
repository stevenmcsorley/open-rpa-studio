import type { BridgeResult } from './types';

export function changedWorkflowNames(before:BridgeResult,after:BridgeResult):string[]{
  const names=new Set([...Object.keys(before.workflows),...Object.keys(after.workflows)]);
  return [...names].filter(name=>JSON.stringify(before.workflows[name])!==JSON.stringify(after.workflows[name]));
}

export function workflowChangeNotice(name:string|undefined,before:BridgeResult,after:BridgeResult):string{
  if(!name)return 'Project updated from an external editor or MCP';
  if(!before.workflows[name]&&after.workflows[name])return `MCP created “${name}” · opened it`;
  if(before.workflows[name]&&after.workflows[name])return `Workflow “${name}” updated from an external editor or MCP`;
  return `Workflow “${name}” was removed from the project`;
}
