import type { Workflow } from './types';
function expr(s:string,v:Record<string,any>):any{
  const x=s.trim().replace(/^=/,'').trim();if(x==='True')return true;if(x==='False')return false;if(x==='None'||x==='null')return null;
  try{return JSON.parse(x)}catch{}
  const m=x.match(/^([A-Za-z][\w]*)\s*(==|!=|>=|<=|>|<|\+|-|\*|\/|in)\s*(.+)$/);
  if(m){const a=v[m[1]];let b:any;try{b=JSON.parse(m[3])}catch{b=v[m[3]]??m[3].replace(/^['"]|['"]$/g,'')}switch(m[2]){case'==':return a===b;case'!=':return a!==b;case'>':return a>b;case'<':return a<b;case'>=':return a>=b;case'<=':return a<=b;case'+':return a+b;case'-':return a-b;case'*':return a*b;case'/':return a/b;case'in':return b.includes(a)}}
  if(/^\w+$/.test(x)&&x in v)return v[x];return x;
}
function val(x:any,v:Record<string,any>):any{if(typeof x==='string'){const m=x.match(/^\{\{([^{}]*)\}\}$/);return m?expr(m[1],v):x.replace(/\{\{(.*?)\}\}/g,(_,e)=>String(expr(e,v)));}return x;}
function matchesArgumentType(value:any,type:string):boolean{return type==='any'||type==='string'&&typeof value==='string'||type==='integer'&&typeof value==='number'&&Number.isSafeInteger(value)||type==='number'&&typeof value==='number'&&Number.isFinite(value)||type==='boolean'&&typeof value==='boolean'||type==='object'&&value!==null&&typeof value==='object'&&!Array.isArray(value)||type==='array'&&Array.isArray(value)}
export function validate(w:Workflow):any[]{
  if(!w||w.format!=='openrpa.workflow')return[{code:'format',message:'Unsupported workflow format'}];
  const ids=new Set<string>();const problems:any[]=[];
  if(!Array.isArray(w.activities))return[{code:'activities-type',message:'activities must be an array'}];
  if(![undefined,'sequence','flowchart','state_machine'].includes((w as any).executionModel))problems.push({code:'execution-model',message:'executionModel must be sequence, flowchart or state_machine'});
  const args=(w as any).arguments??[];
  if(!Array.isArray(args))problems.push({code:'arguments-type',message:'arguments must be an array'});
  else{
    const names=new Set<string>();
    for(const arg of args){
      if(!arg||typeof arg!=='object'||typeof arg.name!=='string'||!arg.name.trim())problems.push({code:'argument-invalid',message:'Each argument needs a name'});
      else if(names.has(arg.name))problems.push({code:'argument-duplicate',message:`Duplicate argument: ${arg.name}`});
      else names.add(arg.name);
      if(!arg||typeof arg!=='object')continue;
      if(!['string','integer','number','boolean','object','array','any'].includes(arg.type??'any'))problems.push({code:'argument-type',message:`Argument '${arg.name??''}' has unsupported type ${arg.type}`});
      if(!['in','out','inout'].includes(arg.direction??'in'))problems.push({code:'argument-direction',message:`Invalid argument direction: ${arg.direction}`});
      if(arg.required!==undefined&&typeof arg.required!=='boolean')problems.push({code:'argument-required',message:`Argument '${arg.name??''}' required must be a boolean`});
      if(Object.hasOwn(arg,'default')&&!matchesArgumentType(arg.default,arg.type??'any'))problems.push({code:'argument-default-type',message:`Argument '${arg.name??''}' default does not match declared type ${arg.type??'any'}`});
    }
  }
  const walk=(items:any[])=>items.forEach((item:any)=>{
    if(!item.id)problems.push({code:'id',message:'Activity id is required'});
    else if(ids.has(item.id))problems.push({code:'duplicate',message:`Duplicate activity id ${item.id}`,activityId:item.id});
    else ids.add(item.id);
    if(!item.type)problems.push({code:'type',message:'Activity type is required',activityId:item.id});
    if(item.type==='browser_wait'&&(!['attached','detached','visible','hidden'].includes(item.state??'visible')||typeof item.selector!=='string'||!item.selector.trim()||!['role','label','text','placeholder','test_id','css'].includes(item.selectorKind??'role')||typeof item.timeoutSeconds!=='number'||item.timeoutSeconds<1||item.timeoutSeconds>120))problems.push({code:'browser-wait',message:'Browser Wait needs a valid selector, state and timeout from 1 to 120 seconds',activityId:item.id});
    if(item.type==='browser_assert'&&(!['visible','hidden','enabled','disabled','checked','text'].includes(item.assertion??'visible')||typeof item.selector!=='string'||!item.selector.trim()||!['role','label','text','placeholder','test_id','css'].includes(item.selectorKind??'role')||typeof item.timeoutSeconds!=='number'||item.timeoutSeconds<1||item.timeoutSeconds>120||(item.assertion==='text'&&(!item.expectedText||!['exact','contains'].includes(item.textMatch??'exact')))))problems.push({code:'browser-assert',message:'Browser Assert needs a valid selector, assertion and timeout; text assertions also need expected text',activityId:item.id});
    if(item.type==='pdf_read_text'&&(typeof item.path!=='string'||!item.path.trim()||typeof (item.result??'text')!=='string'||!/^[$A-Z_a-z][$\w]*$/.test(item.result??'text')||typeof (item.pageCountResult??'pageCount')!=='string'||!/^[$A-Z_a-z][$\w]*$/.test(item.pageCountResult??'pageCount')||(item.result??'text')===(item.pageCountResult??'pageCount')||typeof (item.maxPages??500)!=='number'||!Number.isInteger(item.maxPages??500)||(item.maxPages??500)<1||(item.maxPages??500)>5000||typeof (item.layoutMode??false)!=='boolean'))problems.push({code:'pdf-read-text',message:'PDF Read Text needs a path, distinct result variables, a page limit from 1 to 5,000 and a layout mode',activityId:item.id});
    if(item.type==='sqlite_query'&&(typeof item.path!=='string'||!item.path.trim()||typeof item.query!=='string'||!item.query.trim()||item.query.length>100000||typeof (item.result??'rows')!=='string'||!/^[$A-Z_a-z][$\w]*$/.test(item.result??'rows')||!['string','object'].includes(typeof (item.parameters??[]))||typeof (item.maxRows??10000)!=='number'||!Number.isInteger(item.maxRows??10000)||(item.maxRows??10000)<1||(item.maxRows??10000)>100000||typeof (item.timeoutSeconds??30)!=='number'||!Number.isFinite(item.timeoutSeconds??30)||(item.timeoutSeconds??30)<1||(item.timeoutSeconds??30)>120))problems.push({code:'sqlite-query',message:'SQLite Query needs a path, SQL statement, result variable, parameter list or mapping, row limit and timeout',activityId:item.id});
    if(item.type==='if'){walk(item.then||[]);walk(item.else||[])}
    if(item.type==='for_each'||item.type==='while')walk(item.body||[]);
    if(item.type==='retry'){
      const attempts=item.maxAttempts;
      if(!Number.isInteger(attempts)||attempts<1||attempts>10)problems.push({code:'retry-attempts',message:'Retry maxAttempts must be an integer from 1 to 10',activityId:item.id});
      else if(attempts>1&&item.repeatSafe!==true)problems.push({code:'retry-safety',message:'Mark the retry body as safe to repeat before allowing multiple attempts',activityId:item.id});
      if(attempts>1&&(!Array.isArray(item.retryOn)||item.retryOn.length===0))problems.push({code:'retry-codes-empty',message:'List at least one retryable error code before enabling multiple attempts',activityId:item.id});
      if(!Array.isArray(item.retryOn)||item.retryOn.length>50||item.retryOn.some((code:any)=>typeof code!=='string'||!code||code.length>100))problems.push({code:'retry-codes',message:'Retry retryOn must be an array of up to 50 non-empty error codes',activityId:item.id});
      if(typeof item.delaySeconds!=='number'||!Number.isFinite(item.delaySeconds)||item.delaySeconds<0||item.delaySeconds>60)problems.push({code:'retry-delay',message:'Retry delaySeconds must be between 0 and 60',activityId:item.id});
      if(typeof item.backoffFactor!=='number'||!Number.isFinite(item.backoffFactor)||item.backoffFactor<1||item.backoffFactor>5)problems.push({code:'retry-backoff',message:'Retry backoffFactor must be between 1 and 5',activityId:item.id});
      if(!Array.isArray(item.body))problems.push({code:'retry-body',message:'Retry body must be an array',activityId:item.id});else walk(item.body);
    }
    if(item.type==='switch'){
      if(typeof item.expression!=='string')problems.push({code:'switch-expression',message:'Switch needs an expression',activityId:item.id});
      if(!Array.isArray(item.cases)||item.cases.length>100)problems.push({code:'switch-cases',message:'Switch needs an array of at most 100 cases',activityId:item.id});
      else{
        const values=new Set<string>();
        item.cases.forEach((entry:any,index:number)=>{
          if(!entry||typeof entry!=='object'||!Object.hasOwn(entry,'value'))problems.push({code:'switch-case',message:`Switch case ${index+1} needs a value`,activityId:item.id});
          else if(entry.value!==null&&!['string','number','boolean'].includes(typeof entry.value))problems.push({code:'switch-case-value',message:`Switch case ${index+1} value must be a JSON scalar`,activityId:item.id});
          const key=JSON.stringify(entry?.value)??'undefined';
          if(values.has(key))problems.push({code:'switch-case-duplicate',message:`Duplicate Switch case value ${key}`,activityId:item.id});
          values.add(key);
          if(!Array.isArray(entry?.activities))problems.push({code:'switch-case-activities',message:`Switch case ${index+1} activities must be an array`,activityId:item.id});
          else walk(entry.activities);
        });
      }
      if(!Array.isArray(item.default))problems.push({code:'switch-default',message:'Switch default branch must be an array',activityId:item.id});
      else walk(item.default);
    }
  });
  if((w as any).executionModel==='flowchart'){
    const graph=(w as any).flowchart;const nodes=graph?.nodes;const transitions=graph?.transitions;
    if(!Array.isArray(nodes)||!nodes.length||nodes.length>10000)problems.push({code:'flowchart-nodes',message:'Flowchart needs between 1 and 10,000 nodes'});
    if(!Array.isArray(transitions)||transitions.length>20000)problems.push({code:'flowchart-transitions',message:'Flowchart transitions must be an array of at most 20,000 entries'});
    if((w.activities||[]).length)problems.push({code:'flowchart-sequence-mixed',message:'Flowchart workflows must keep sequence activities empty'});
    if(Array.isArray(nodes)&&Array.isArray(transitions)){
      const map=new Map<string,any>();const starts:any[]=[];const edges=new Map<string,any[]>();
      for(const node of nodes){if(!node||typeof node.id!=='string'||!node.id){problems.push({code:'flowchart-node-id',message:'Flowchart nodes need non-empty ids'});continue}if(map.has(node.id)||ids.has(node.id))problems.push({code:'flowchart-node-duplicate',message:`Duplicate node id ${node.id}`});map.set(node.id,node);edges.set(node.id,[]);if(!['start','action','decision','end'].includes(node.kind))problems.push({code:'flowchart-node-kind',message:`Unsupported node kind for ${node.id}`});if(node.kind==='start')starts.push(node.id);if(node.kind==='action'){if(!node.activity)problems.push({code:'flowchart-action',message:`Action ${node.id} needs an activity`});else walk([node.activity])}if(node.kind==='decision'&&typeof node.condition!=='string')problems.push({code:'flowchart-condition',message:`Decision ${node.id} needs a condition`});for(const key of ['x','y'])if(key in node&&(typeof node[key]!=='number'||!Number.isFinite(node[key])||node[key]<0||node[key]>10000))problems.push({code:'flowchart-position',message:`Node ${node.id} ${key} must be between 0 and 10,000`})}
      if(starts.length!==1||graph.start!==starts[0])problems.push({code:'flowchart-start',message:'Flowchart needs one declared Start node'});
      for(const id of map.keys())if(ids.has(id))problems.push({code:'flowchart-node-activity-duplicate',message:`Flowchart node id conflicts with an activity id ${id}`});
      const incoming=new Map<string,number>();for(const id of map.keys())incoming.set(id,0);const seenEdges=new Set<string>();
      for(const edge of transitions){if(!edge||!map.has(edge.from)||!map.has(edge.to)){problems.push({code:'flowchart-transition-target',message:'A transition refers to an unknown node'});continue}edges.get(edge.from)!.push(edge);incoming.set(edge.to,(incoming.get(edge.to)||0)+1);const kind=map.get(edge.from).kind;const when=edge.when??'always';if((kind==='decision'&&!['true','false'].includes(when))||(kind!=='decision'&&when!=='always'))problems.push({code:'flowchart-transition-condition',message:`Invalid transition condition from ${edge.from}`});const key=`${edge.from}:${when}`;if(seenEdges.has(key))problems.push({code:'flowchart-transition-duplicate',message:`Duplicate ${when} transition from ${edge.from}`});seenEdges.add(key)}
      for(const [id,node] of map){const out=edges.get(id)!;if(node.kind==='start'&&(out.length!==1||incoming.get(id)!==0))problems.push({code:'flowchart-start-edge',message:`Start ${id} needs one outgoing edge and no incoming edge`});if(node.kind==='action'&&out.length!==1)problems.push({code:'flowchart-action-edges',message:`Action ${id} needs one outgoing edge`});if(node.kind==='decision'&&new Set(out.map(e=>e.when)).size!==2)problems.push({code:'flowchart-decision-edges',message:`Decision ${id} needs true and false edges`});if(node.kind==='end'&&out.length)problems.push({code:'flowchart-end-edges',message:`End ${id} cannot have outgoing edges`})}
      if(![...map.values()].some(node=>node.kind==='end'))problems.push({code:'flowchart-end-missing',message:'Flowchart needs an End node'});
      if(map.has(graph.start)){const reached=new Set<string>();const pending=[graph.start];while(pending.length){const id=pending.pop()!;if(reached.has(id))continue;reached.add(id);for(const edge of edges.get(id)||[])pending.push(edge.to)}for(const id of map.keys())if(!reached.has(id))problems.push({code:'flowchart-unreachable',message:`Node ${id} is unreachable from Start`})}
    }
  }else if((w as any).executionModel==='state_machine'){
    const machine=(w as any).stateMachine;const states=machine?.states;const transitions=machine?.transitions;
    if((w.activities||[]).length)problems.push({code:'state-machine-sequence-mixed',message:'State-machine workflows must keep sequence activities empty'});
    if(!Array.isArray(states)||!states.length||states.length>1000)problems.push({code:'state-machine-states',message:'State machine needs between 1 and 1,000 states'});
    if(!Array.isArray(transitions)||transitions.length>5000)problems.push({code:'state-machine-transitions',message:'State machine transitions must be an array of at most 5,000 entries'});
    if(Array.isArray(states)&&Array.isArray(transitions)){
      const map=new Map<string,any>();const outgoing=new Map<string,any[]>();
      for(const state of states){if(!state||typeof state.id!=='string'||!state.id){problems.push({code:'state-machine-state-id',message:'States need non-empty ids'});continue}if(map.has(state.id)||ids.has(state.id))problems.push({code:'state-machine-state-duplicate',message:`Duplicate state id ${state.id}`});map.set(state.id,state);ids.add(state.id);outgoing.set(state.id,[]);if(typeof state.final!=='undefined'&&typeof state.final!=='boolean')problems.push({code:'state-machine-final',message:`State ${state.id} final must be boolean`});if(!Array.isArray(state.activities))problems.push({code:'state-machine-activities',message:`State ${state.id} activities must be an array`});else walk(state.activities)}
      if(!map.has(machine?.initial))problems.push({code:'state-machine-initial',message:'Initial state must refer to a declared state'});
      for(const edge of transitions){if(!edge||!map.has(edge.from)||!map.has(edge.to)){problems.push({code:'state-machine-transition-target',message:'Transition refers to an unknown state'});continue}if(edge.condition!==undefined&&(typeof edge.condition!=='string'||!edge.condition.trim()))problems.push({code:'state-machine-condition',message:`Transition from ${edge.from} needs a non-empty condition`});outgoing.get(edge.from)!.push(edge)}
      for(const [id,state] of map){const edges=outgoing.get(id)!;if(state.final&&edges.length)problems.push({code:'state-machine-final-edges',message:`Final state ${id} cannot have outgoing transitions`});if(!state.final&&!edges.length)problems.push({code:'state-machine-no-transition',message:`State ${id} needs an outgoing transition`});const fallback=edges.findIndex(edge=>edge.condition===undefined);if(fallback>=0&&fallback!==edges.length-1||edges.filter(edge=>edge.condition===undefined).length>1)problems.push({code:'state-machine-fallback-order',message:`State ${id} must have a single last unconditional fallback`})}
      if(![...map.values()].some(state=>state.final===true))problems.push({code:'state-machine-final-missing',message:'State machine needs a final state'});
      if(map.has(machine?.initial)){const reached=new Set<string>();const pending=[machine.initial];while(pending.length){const id=pending.pop()!;if(reached.has(id))continue;reached.add(id);for(const edge of outgoing.get(id)||[])pending.push(edge.to)}for(const id of map.keys())if(!reached.has(id))problems.push({code:'state-machine-unreachable',message:`State ${id} is unreachable`})}
    }
  }else walk(w.activities||[]);return problems;
}
export function validateBindings(workflows:Record<string,Workflow>,owner:string):any[]{
  const problems:any[]=[];const current=workflows[owner];if(!current)return problems;
  const matches=(value:any,type:string)=>type==='any'||type==='string'&&typeof value==='string'||type==='integer'&&typeof value==='number'&&Number.isSafeInteger(value)||type==='number'&&typeof value==='number'&&Number.isFinite(value)||type==='boolean'&&typeof value==='boolean'||type==='object'&&value!==null&&typeof value==='object'&&!Array.isArray(value)||type==='array'&&Array.isArray(value);
  const visit=(items:any[])=>{for(const item of items||[]){if(!item||typeof item!=='object')continue;
    if(item.type==='invoke_workflow'){
      const target=String(item.workflow||'');const child=workflows[target];const add=(code:string,message:string)=>problems.push({code,message,activityId:item.id});
      if(!child){add('workflow-ref',`Unknown reusable workflow '${target}'`);continue}
      const args=child.arguments||[];const inputs=item.inputs&&typeof item.inputs==='object'?item.inputs:{};const outputs=item.outputs&&typeof item.outputs==='object'?item.outputs:{};
      for(const name of Object.keys(inputs))if(!args.some(arg=>arg.name===name&&arg.direction!=='out'))add('argument-unknown',`'${target}' has no input argument '${name}'`);
      for(const arg of args)if(Object.hasOwn(inputs,arg.name)&&arg.direction!=='out'&&!(typeof inputs[arg.name]==='string'&&/^\\{\\{\\s*.+?\\s*\\}\\}$/s.test(String(inputs[arg.name])))&&!matches(inputs[arg.name],arg.type||'any'))add('argument-type',`Literal input '${arg.name}' does not match type ${arg.type}`);
      for(const arg of args)if(arg.direction!=='out'&&arg.required!==false&&!Object.hasOwn(arg,'default')&&!Object.hasOwn(inputs,arg.name))add('argument-missing',`Required input '${arg.name}' is not mapped for '${target}'`);
      for(const [name,destination] of Object.entries(outputs))if(!args.some(arg=>arg.name===name&&(arg.direction==='out'||arg.direction==='inout')))add('argument-output',`'${name}' is not an output argument of '${target}'`);else if(typeof destination!=='string'||!/^[$A-Z_a-z][$\w]{0,255}$/.test(destination))add('argument-output-target',`Output '${name}' needs a valid caller variable name`);
    }
    for(const key of ['then','else','body','catch','finally','default'])if(Array.isArray(item[key]))visit(item[key]);
    for(const entry of item.cases||[])if(Array.isArray(entry.activities))visit(entry.activities);
  }};
  visit(current.activities||[]);for(const node of current.flowchart?.nodes||[])if(node.activity)visit([node.activity]);for(const state of current.stateMachine?.states||[])visit(state.activities||[]);return problems;
}
export async function run(w:Workflow,allowNetwork:boolean,emitExternal:(e:any)=>void,workflows:Record<string,Workflow>={[w.name]:w},workflowName=w.name,inputs:Record<string,any>={},callStack:string[]=[]):Promise<any>{
  const emit=(event:any)=>emitExternal({...event,workflow:workflowName});
  if(callStack.includes(workflowName)||callStack.length>=40)return{status:'failed',variables:{},logs:[],activities:{},error:{code:'workflow-cycle',message:`Workflow invocation cycle or depth limit at ${workflowName}`}};
  const variables:any=Object.fromEntries((w.variables||[]).map(x=>[x.name,x.value]));
  for(const spec of w.arguments||[]){if(Object.hasOwn(inputs,spec.name))variables[spec.name]=inputs[spec.name];else if(Object.hasOwn(spec,'default'))variables[spec.name]=spec.default;else if((spec.direction==='in'||spec.direction==='inout'||!spec.direction)&&spec.required!==false)return{status:'failed',variables,logs:[],activities:{},error:{code:'argument-missing',message:`Missing required input argument '${spec.name}'`}};if(Object.hasOwn(variables,spec.name)&&!matchesArgumentType(variables[spec.name],spec.type||'any'))return{status:'failed',variables,logs:[],activities:{},error:{code:'argument-type',message:`Argument '${spec.name}' does not match declared type ${spec.type}`}}}
  const logs:any[]=[];const activities:any={};let error:any;
  const seq=async(items:any[])=>{for(const a of items){if(error)return;emit({event:'activity-started',activityId:a.id,type:a.type});try{
    switch(a.type){
      case'assign':variables[a.target]=val(a.value,variables);break;
      case'log':{const entry={event:'log',activityId:a.id,message:String(val(a.message,variables)),level:a.level||'info'};logs.push(entry);emit(entry);break}
      case'invoke_workflow':{
        const target=String(a.workflow||'');const child=workflows[target];if(!child)throw Error(`Unknown reusable workflow '${target}'`);
        const supplied=a.inputs&&typeof a.inputs==='object'?a.inputs:{};const childInputs:any={};
        for(const spec of child.arguments||[]){if(spec.direction==='out')continue;if(Object.hasOwn(supplied,spec.name))childInputs[spec.name]=val(supplied[spec.name],variables);else if(Object.hasOwn(spec,'default'))childInputs[spec.name]=spec.default;else if(spec.required!==false)throw Object.assign(new Error(`Missing required input '${spec.name}' for workflow '${target}'`),{code:'argument-missing'});}
        for(const name of Object.keys(supplied))if(!(child.arguments||[]).some(spec=>spec.name===name&&spec.direction!=='out'))throw Object.assign(new Error(`Unknown input '${name}' for workflow '${target}'`),{code:'argument-unknown'});
        const before=new Set(Object.keys(variables));const childResult=await run(child,allowNetwork,event=>emitExternal({...event,workflow:target,parentWorkflow:workflowName}),workflows,target,childInputs,[...callStack,workflowName]);
        if(childResult.status!=='succeeded')throw Object.assign(new Error(childResult.error?.message||`Workflow '${target}' failed`),{code:childResult.error?.code||'workflow-failed'});
        const mapped=a.outputs&&typeof a.outputs==='object'?a.outputs:{};
        for(const spec of child.arguments||[])if(spec.direction==='out'||spec.direction==='inout'){
          const destination=String(mapped[spec.name]??spec.target??spec.name);if(!/^[A-Za-z_]\w{0,255}$/.test(destination))throw Object.assign(new Error(`Output '${spec.name}' needs a valid caller variable name`),{code:'argument-output-target'});
          if(Object.hasOwn(childResult.variables,spec.name))variables[destination]=childResult.variables[spec.name];
        }
        if(a.resultTarget)variables[a.resultTarget]=Object.fromEntries(Object.entries(childResult.variables).filter(([name])=>!before.has(name)));
        break;
      }
      case'if':await seq(expr(a.condition,variables)?a.then||[]:a.else||[]);break;
      case'switch':{const actual=expr(a.expression,variables);const selected=(a.cases||[]).find((entry:any)=>typeof entry.value===typeof actual&&entry.value===actual);await seq(selected?.activities||a.default||[]);break}
      case'for_each':{const values=expr(a.items,variables);if(!Array.isArray(values))throw Error('For Each expects a list');if(values.length>100000)throw Error('For Each exceeded the 100,000 item preview limit');const had=Object.hasOwn(variables,a.itemName),old=variables[a.itemName];for(const item of values){variables[a.itemName]=item;await seq(a.body||[]);if(error)break}if(had)variables[a.itemName]=old;else delete variables[a.itemName];break}
      case'while':{let count=0;while(true){const condition=expr(a.condition,variables);if(typeof condition!=='boolean')throw Error('While condition must evaluate to true or false');if(!condition)break;if(++count>100000)throw Error('While exceeded the 100,000 iteration preview limit');await seq(a.body||[]);if(error)break}break}
      case'retry':{for(let attempt=1;attempt<=a.maxAttempts;attempt++){error=undefined;await seq(a.body);if(!error)break;const current=error;const willRetry=attempt<a.maxAttempts&&(a.retryOn||[]).includes(current.code);emit({event:'retry-attempt-failed',activityId:a.id,attempt,maxAttempts:a.maxAttempts,errorCode:current.code,willRetry});if(!willRetry)break;error=undefined;if(a.delaySeconds)await new Promise(r=>setTimeout(r,Math.min(60000,a.delaySeconds*1000*Math.pow(a.backoffFactor,attempt-1))))}if(error)throw Object.assign(new Error(error.message),{code:error.code});break}
      case'transform_field':{const rows=typeof a.rows==='string'&&a.rows in variables?variables[a.rows]:val(a.rows,variables);const op=a.operation;variables[a.result||'rows']=rows.map((row:any)=>{const copy={...row};if(copy[a.field]!=null){let text=String(copy[a.field]);if(op==='trim')text=text.trim();else if(op==='upper')text=text.toUpperCase();else if(op==='lower')text=text.toLowerCase();else if(op==='regex_replace')text=text.replace(new RegExp(a.pattern,'g'),String(a.replacement??''));else throw Error(`Unsupported field transform ${op}`);copy[a.field]=text}return copy});break}
      case'wait':await new Promise(r=>setTimeout(r,Math.min(300000,Number(val(a.seconds,variables))*1000)));break;
      case'http_request':if(!allowNetwork)throw Error('Network access requires run permission');throw Error('HTTP in browser preview is disabled; use the desktop engine');
      case'browser_wait':case'browser_assert':throw Error(`${a.type} requires the desktop Playwright engine`);
      case'sqlite_query':case'file_read_text':case'file_write_text':case'file_copy':case'file_list':case'file_move':case'file_delete':case'csv_read':case'csv_write':case'xlsx_read':case'xlsx_write':case'pdf_read_text':case'json_parse':case'json_write':case'regex_replace':case'regex_match':throw Error(`${a.type} requires the desktop filesystem engine`);
      default:throw Error(`Unsupported activity ${a.type}`)
    }
    activities[a.id]={status:'succeeded',type:a.type};emit({event:'activity-completed',activityId:a.id,type:a.type});
  }catch(e){activities[a.id]={status:'failed',type:a.type,error:e instanceof Error?e.message:String(e)};error={code:(e as any)?.code||'activity-failed',message:activities[a.id].error,activityId:a.id};emit({event:'activity-failed',activityId:a.id,type:a.type,error:activities[a.id].error});}}
  };
  if((w as any).executionModel==='flowchart'){
    const graph=(w as any).flowchart;const nodes=new Map(graph.nodes.map((node:any)=>[node.id,node]));const transitions=graph.transitions as any[];let current=graph.start;let steps=0;
    while(current&&!error){if(++steps>100000){error={code:'flowchart-quota',message:'Flowchart exceeded the 100,000 node visit preview limit',activityId:current};break}const node:any=nodes.get(current);if(!node){error={code:'flowchart-node',message:`Missing flowchart node ${current}`,activityId:current};break}if(node.kind==='action'){await seq([node.activity]);const edge=transitions.find(edge=>edge.from===current);current=edge?.to??null;continue}emit({event:'activity-started',activityId:node.id,type:`flowchart_${node.kind}`});let next:string|null=null;if(node.kind==='end')next=null;else if(node.kind==='decision'){const result=expr(node.condition,variables);if(typeof result!=='boolean'){error={code:'flowchart-condition-type',message:'Flowchart decision must evaluate to true or false',activityId:node.id};activities[node.id]={status:'failed',type:'flowchart_decision',error:error.message};emit({event:'activity-failed',activityId:node.id,type:'flowchart_decision',error:error.message});break}next=transitions.find(edge=>edge.from===node.id&&edge.when===(result?'true':'false'))?.to??null}else next=transitions.find(edge=>edge.from===node.id)?.to??null;activities[node.id]={status:'succeeded',type:`flowchart_${node.kind}`};emit({event:'activity-completed',activityId:node.id,type:`flowchart_${node.kind}`,nextNode:next});current=next}
  }else if((w as any).executionModel==='state_machine'){
    const machine=(w as any).stateMachine;const states=new Map(machine.states.map((state:any)=>[state.id,state]));const transitions=machine.transitions as any[];let current=machine.initial;let visits=0;
    while(current&&!error){if(++visits>100000){error={code:'state-machine-quota',message:'State machine exceeded the 100,000 state visit preview limit',activityId:current};break}const state:any=states.get(current);if(!state){error={code:'state-machine-state',message:`Missing state ${current}`,activityId:current};break}emit({event:'activity-started',activityId:current,type:'state_machine_state'});await seq(state.activities||[]);if(error){activities[current]={status:'failed',type:'state_machine_state',error:error.message};emit({event:'activity-failed',activityId:current,type:'state_machine_state',error:error.message});break}let next:string|null=null;if(!state.final){let fallback:any;for(const edge of transitions.filter(edge=>edge.from===current)){if(edge.condition===undefined){fallback=edge;continue}const matched=expr(edge.condition,variables);if(typeof matched!=='boolean'){error={code:'state-machine-condition-type',message:'Transition condition must evaluate to true or false',activityId:current};break}if(matched){next=edge.to;break}}if(!error&&next===null&&fallback)next=fallback.to;if(!error&&next===null)error={code:'state-machine-no-transition-match',message:`No transition matched from state ${current}`,activityId:current}}if(error){activities[current]={status:'failed',type:'state_machine_state',error:error.message};emit({event:'activity-failed',activityId:current,type:'state_machine_state',error:error.message});break}activities[current]={status:'succeeded',type:'state_machine_state'};emit({event:'activity-completed',activityId:current,type:'state_machine_state',nextState:next});current=next}
  }else await seq(w.activities||[]);return{status:error?'failed':'succeeded',variables,logs,activities,...(error?{error}:{})};
}
