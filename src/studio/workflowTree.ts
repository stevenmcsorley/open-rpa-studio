import type { Activity } from './types';

const NESTED_BRANCHES=['then','else','body','catch','finally','default'] as const;

function switchCaseIndex(branch:string):number|undefined{
  const match=branch.match(/^case:(\d+)$/);
  return match?Number(match[1]):undefined;
}

export function appendNestedActivity(items:Activity[],parentId:string,branch:string,activity:Activity):Activity[]{
  return items.map(item=>{
    if(item.id===parentId){
      const caseIndex=item.type==='switch'?switchCaseIndex(branch):undefined;
      if(caseIndex!==undefined){
        const cases=Array.isArray(item.cases)?item.cases as {value:unknown;activities:Activity[]}[]:[];
        if(!cases[caseIndex])return item;
        return {...item,cases:cases.map((entry,index)=>index===caseIndex?{...entry,activities:[...(Array.isArray(entry.activities)?entry.activities:[]),activity]}:entry)};
      }
      return {...item,[branch]:[...(Array.isArray(item[branch])?item[branch] as Activity[]:[]),activity]};
    }
    const copy=Object.fromEntries(Object.entries(item).map(([key,value])=>[
      key,Array.isArray(value)&&NESTED_BRANCHES.includes(key as typeof NESTED_BRANCHES[number])
        ?appendNestedActivity(value as Activity[],parentId,branch,activity):value
    ])) as Activity;
    if(item.type==='switch'&&Array.isArray(item.cases))copy.cases=(item.cases as {value:unknown;activities:Activity[]}[]).map(entry=>({...entry,activities:appendNestedActivity(Array.isArray(entry.activities)?entry.activities:[],parentId,branch,activity)}));
    return copy;
  });
}

export function removeNestedActivity(items:Activity[],id:string):Activity[]{
  return items.filter(item=>item.id!==id).map(item=>{
    const copy=Object.fromEntries(Object.entries(item).map(([key,value])=>[
      key,Array.isArray(value)&&NESTED_BRANCHES.includes(key as typeof NESTED_BRANCHES[number])
        ?removeNestedActivity(value as Activity[],id):value
    ])) as Activity;
    if(item.type==='switch'&&Array.isArray(item.cases))copy.cases=(item.cases as {value:unknown;activities:Activity[]}[]).map(entry=>({...entry,activities:removeNestedActivity(Array.isArray(entry.activities)?entry.activities:[],id)}));
    return copy;
  });
}

export function reorderNestedActivity(items:Activity[],id:string,delta:number):Activity[]{
  const index=items.findIndex(item=>item.id===id);
  if(index>=0){
    const target=index+delta;
    if(target<0||target>=items.length)return items;
    const reordered=[...items];
    [reordered[index],reordered[target]]=[reordered[target],reordered[index]];
    return reordered;
  }
  let changed=false;
  const next=items.map(item=>{
    let copy=item;
    for(const key of NESTED_BRANCHES){
      const branch=item[key];
      if(Array.isArray(branch)){
        const reordered=reorderNestedActivity(branch as Activity[],id,delta);
        if(reordered!==branch){copy={...copy,[key]:reordered};changed=true;break;}
      }
    }
    if(item.type==='switch'&&!changed&&Array.isArray(item.cases)){
      const cases=item.cases as {value:unknown;activities:Activity[]}[];
      const reorderedCases=cases.map(entry=>{const original=Array.isArray(entry.activities)?entry.activities:[];const reordered=reorderNestedActivity(original,id,delta);if(reordered!==original)changed=true;return reordered===original?entry:{...entry,activities:reordered};});
      if(changed)copy={...copy,cases:reorderedCases};
    }
    return copy;
  });
  return changed?next:items;
}

export function findNestedActivity(items:Activity[],id:string):Activity|undefined{
  for(const item of items){
    if(item.id===id)return item;
    for(const key of NESTED_BRANCHES){
      const branch=item[key];
      if(Array.isArray(branch)){
        const found=findNestedActivity(branch as Activity[],id);
        if(found)return found;
      }
    }
    if(item.type==='switch'&&Array.isArray(item.cases)){
      for(const entry of item.cases as {activities?:Activity[]}[]){
        const found=findNestedActivity(entry.activities??[],id);
        if(found)return found;
      }
    }
  }
  return undefined;
}

export function updateNestedActivity(items:Activity[],id:string,patch:Record<string,unknown>):Activity[]{
  return items.map(item=>{
    if(item.id===id)return {...item,...patch};
    const copy=Object.fromEntries(Object.entries(item).map(([key,value])=>[
      key,Array.isArray(value)&&NESTED_BRANCHES.includes(key as typeof NESTED_BRANCHES[number])
        ?updateNestedActivity(value as Activity[],id,patch):value
    ])) as Activity;
    if(item.type==='switch'&&Array.isArray(item.cases))copy.cases=(item.cases as {value:unknown;activities:Activity[]}[]).map(entry=>({...entry,activities:updateNestedActivity(entry.activities??[],id,patch)}));
    return copy;
  });
}
