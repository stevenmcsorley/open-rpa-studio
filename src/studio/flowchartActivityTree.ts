import type { Activity,Flowchart,FlowNode } from './types';
import { appendNestedActivity,findNestedActivity,removeNestedActivity,updateNestedActivity } from './workflowTree';

export function findFlowchartActionContaining(graph:Flowchart,activityId:string):FlowNode|undefined{
  return graph.nodes.find(node=>Boolean(node.activity&&findNestedActivity([node.activity],activityId)));
}

export function patchFlowchartActionActivity(graph:Flowchart,activityId:string,patch:Record<string,unknown>):Flowchart|null{
  let matched=false;
  const nodes=graph.nodes.map(node=>{
    if(!node.activity||!findNestedActivity([node.activity],activityId))return node;
    matched=true;
    return{...node,activity:updateNestedActivity([node.activity],activityId,patch)[0]};
  });
  return matched?{...graph,nodes}:null;
}

export function appendFlowchartActionBranchActivity(graph:Flowchart,parentId:string,branch:string,activity:Activity):Flowchart|null{
  let matched=false;
  const nodes=graph.nodes.map(node=>{
    if(!node.activity||!findNestedActivity([node.activity],parentId))return node;
    matched=true;
    return{...node,activity:appendNestedActivity([node.activity],parentId,branch,activity)[0]};
  });
  return matched?{...graph,nodes}:null;
}

export function removeFlowchartNestedActivity(graph:Flowchart,activityId:string):{graph:Flowchart;containerId:string}|null{
  const container=findFlowchartActionContaining(graph,activityId);
  if(!container?.activity||container.activity.id===activityId)return null;
  const nodes=graph.nodes.map(node=>node.id===container.id?{...node,activity:removeNestedActivity([container.activity!],activityId)[0]}:node);
  return{graph:{...graph,nodes},containerId:container.activity.id};
}
