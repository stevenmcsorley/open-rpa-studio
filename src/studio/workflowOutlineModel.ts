import type { Activity } from './types';

export type WorkflowOutlineEntry={id:string;label:string;context:string;depth:number;kind:string};

function title(value:unknown,fallback:string):string{
  const text=typeof value==='string'&&value.trim()?value.trim():fallback;
  return text.replace(/[_-]+/g,' ').replace(/\b\w/g,letter=>letter.toUpperCase());
}

function branches(activity:Activity):{label:string;items:Activity[]}[]{
  if(activity.type==='if')return [['Then','then'],['Else','else']].map(([label,key])=>({label,items:Array.isArray(activity[key])?activity[key] as Activity[]:[]}));
  if(['for_each','while','retry'].includes(activity.type)){
    const key='body';const label=activity.type==='for_each'?'Each item':activity.type==='while'?'While body':'Retry body';
    return Array.isArray(activity[key])?[{label,items:activity[key] as Activity[]}]:[];
  }
  if(activity.type==='try')return [['Try','body'],['Catch','catch'],['Finally','finally']].filter(([,key])=>Array.isArray(activity[key])).map(([label,key])=>({label,items:activity[key] as Activity[]}));
  if(activity.type==='switch'){
    const cases=Array.isArray(activity.cases)?activity.cases as {value:unknown;activities?:Activity[]}[]:[];
    return [...cases.map((entry,index)=>({label:`Case ${String(entry.value??index+1)}`,items:Array.isArray(entry.activities)?entry.activities:[]})),{label:'Default',items:Array.isArray(activity.default)?activity.default as Activity[]:[]}];
  }
  return [];
}

export function flattenWorkflowOutline(activities:Activity[]):WorkflowOutlineEntry[]{
  const entries:WorkflowOutlineEntry[]=[];
  const visit=(items:Activity[],depth:number,ancestors:string[])=>items.forEach(activity=>{
    const kind=title(activity.type,'Activity');
    const label=title(activity.label,kind);
    entries.push({id:activity.id,label,context:ancestors.join(' / '),depth,kind});
    for(const branch of branches(activity))visit(branch.items,depth+1,[...ancestors,`${label} · ${branch.label}`]);
  });
  visit(activities,0,[]);
  return entries;
}
