import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ActivitySequence } from './App';
import { draggedPosition, FlowchartEditor } from './FlowchartEditor';
import { appendNestedActivity, findNestedActivity, removeNestedActivity, reorderNestedActivity, updateNestedActivity } from './workflowTree';
import { insertFlowchartAction } from './flowchartEditing';
import { validate as validateWebWorkflow } from './webEngine';
import type { Activity } from './types';

const tree:Activity[]=[
  {id:'branch',type:'if',condition:'True',then:[
    {id:'loop',type:'for_each',items:'items',itemName:'item',body:[{id:'first',type:'log',message:'first task'},{id:'second',type:'log',message:'second task'}]},
  ],else:[{id:'fallback',type:'log',message:'fallback task'}]},
  {id:'last',type:'log'},
];
const switchTree:Activity[]=[{id:'router',type:'switch',expression:'route',cases:[{value:'ready',activities:[{id:'ready-log',type:'log',message:'ready'},{id:'second-log',type:'log',message:'second'}]}],default:[{id:'fallback-log',type:'log',message:'fallback'}]}];
const retryTree:Activity[]=[{id:'retry',type:'retry',maxAttempts:2,retryOn:['http-timeout'],delaySeconds:1,backoffFactor:2,repeatSafe:true,body:[{id:'retry-log',type:'log',message:'repeat'}]}];

describe('nested visual workflow editing',()=>{
  it('appends a new activity to the selected nested branch without changing the source tree',()=>{
    const added={id:'third',type:'assign'};
    const result=appendNestedActivity(tree,'loop','body',added);
    expect((result[0].then as Activity[])[0].body).toEqual([{id:'first',type:'log',message:'first task'},{id:'second',type:'log',message:'second task'},added]);
    expect((tree[0].then as Activity[])[0].body).toHaveLength(2);
    expect(result[0].else).toEqual(tree[0].else);
  });

  it('removes a nested activity without removing its control-flow parent',()=>{
    const result=removeNestedActivity(tree,'first');
    expect(result[0].id).toBe('branch');
    expect(((result[0].then as Activity[])[0].body as Activity[]).map(item=>item.id)).toEqual(['second']);
    expect(((tree[0].then as Activity[])[0].body as Activity[]).map(item=>item.id)).toEqual(['first','second']);
  });

  it('reorders only within the selected sibling sequence',()=>{
    const result=reorderNestedActivity(tree,'second',-1);
    expect(((result[0].then as Activity[])[0].body as Activity[]).map(item=>item.id)).toEqual(['second','first']);
    expect((result[0].then as Activity[])[0].id).toBe('loop');
    expect(result[1].id).toBe('last');
  });

  it('keeps array identity when a selected item cannot move past a branch boundary',()=>{
    const result=reorderNestedActivity(tree,'first',-1);
    expect(result).toBe(tree);
  });

  it('renders nested branches and their activities in the visual editor tree',()=>{
    const markup=renderToStaticMarkup(createElement(ActivitySequence,{
      items:tree,depth:0,selected:'second',run:null,catalog:[{type:'log',title:'Log Message',category:'Workflow',description:'Write a log entry.',defaults:{}}],
      onSelect:()=>undefined,onAdd:()=>undefined,onPatch:()=>undefined,
    }));
    expect(markup).toContain('THEN');
    expect(markup).toContain('ELSE');
    expect(markup).toContain('EACH ITEM');
    expect(markup).toContain('first task');
    expect(markup).toContain('second task');
    expect(markup).toContain('fallback task');
    expect(markup).toContain('Add an activity inside this branch');
  });

  it('adds, locates, updates, removes, and reorders activities inside Switch cases',()=>{
    const appended=appendNestedActivity(switchTree,'router','case:0',{id:'third-log',type:'log',message:'third'});
    expect((appended[0].cases as any[])[0].activities.map((item:Activity)=>item.id)).toEqual(['ready-log','second-log','third-log']);
    expect(findNestedActivity(appended,'second-log')?.message).toBe('second');
    const updated=updateNestedActivity(appended,'second-log',{message:'updated'});
    expect(findNestedActivity(updated,'second-log')?.message).toBe('updated');
    const reordered=reorderNestedActivity(updated,'third-log',-1);
    expect((reordered[0].cases as any[])[0].activities.map((item:Activity)=>item.id)).toEqual(['ready-log','third-log','second-log']);
    const removed=removeNestedActivity(reordered,'third-log');
    expect((removed[0].cases as any[])[0].activities.map((item:Activity)=>item.id)).toEqual(['ready-log','second-log']);
  });

  it('renders typed Switch cases and a distinct default branch',()=>{
    const markup=renderToStaticMarkup(createElement(ActivitySequence,{
      items:switchTree,depth:0,selected:'ready-log',run:null,catalog:[],onSelect:()=>undefined,onAdd:()=>undefined,onPatch:()=>undefined,
    }));
    expect(markup).toContain('Switch');
    expect(markup).toContain('CASE');
    expect(markup).toContain('ready');
    expect(markup).toContain('DEFAULT');
    expect(markup).toContain('fallback');
    expect(markup).toContain('Add case');
  });

  it('renders Retry Scope body as an editable nested branch',()=>{
    const markup=renderToStaticMarkup(createElement(ActivitySequence,{items:retryTree,depth:0,selected:'retry-log',run:null,catalog:[],onSelect:()=>undefined,onAdd:()=>undefined,onPatch:()=>undefined}));
    expect(markup).toContain('Retry Scope');expect(markup).toContain('RETRY BODY');expect(markup).toContain('repeat');
  });

  it('renders flowchart decision connectors and node targets',()=>{
    const markup=renderToStaticMarkup(createElement(FlowchartEditor,{graph:{start:'start',nodes:[{id:'start',kind:'start'},{id:'decision',kind:'decision',condition:'ready',x:150,y:260},{id:'end',kind:'end'}],transitions:[{from:'start',to:'decision'},{from:'decision',to:'end',when:'true'}]},selected:'decision',onSelect:()=>undefined,onAddNode:()=>undefined,onConnect:()=>undefined,onRemove:()=>undefined,onPositionChange:()=>undefined}));
    expect(markup).toContain('FLOWCHART');expect(markup).toContain('True destination');expect(markup).toContain('False destination');expect(markup).toContain('Decision');expect(markup).toContain('left:150px');expect(markup).toContain('top:260px');
  });

  it('converts pointer movement through zoom and clamps saved flowchart coordinates',()=>{
    expect(draggedPosition({x:200,y:100},{x:10,y:20},{x:50,y:80},2)).toEqual({x:220,y:130});
    expect(draggedPosition({x:0,y:0},{x:0,y:0},{x:-100,y:30000},1)).toEqual({x:0,y:10000});
  });

  it('inserts a palette activity into an existing action path and keeps every node reachable',()=>{
    const workflow:any={format:'openrpa.workflow',formatVersion:1,name:'Graph',variables:[],arguments:[],activities:[],executionModel:'flowchart',flowchart:{start:'start',nodes:[{id:'start',kind:'start'},{id:'first',kind:'action',activity:{id:'first-log',type:'log'}},{id:'end',kind:'end'}],transitions:[{from:'start',to:'first'},{from:'first',to:'end'}]}};
    workflow.flowchart=insertFlowchartAction(workflow.flowchart,'first-log',{id:'new-log',type:'log'},'Log');
    expect(workflow.flowchart.transitions).toEqual([{from:'start',to:'first'},{from:'first',to:'node-new-log'},{from:'node-new-log',to:'end',when:'always'}]);
    expect(validateWebWorkflow(workflow)).toEqual([]);
  });

  it('inserts a graph activity onto a decision True route and preserves False route',()=>{
    const graph:any={start:'start',nodes:[{id:'start',kind:'start'},{id:'decision',kind:'decision',condition:'ready'},{id:'true-end',kind:'end'},{id:'false-end',kind:'end'}],transitions:[{from:'start',to:'decision'},{from:'decision',to:'true-end',when:'true'},{from:'decision',to:'false-end',when:'false'}]};
    const updated=insertFlowchartAction(graph,'decision',{id:'notify',type:'log'},'Notify');
    expect(updated.transitions).toContainEqual({from:'decision',to:'node-notify',when:'true'});
    expect(updated.transitions).toContainEqual({from:'node-notify',to:'true-end',when:'always'});
    expect(updated.transitions).toContainEqual({from:'decision',to:'false-end',when:'false'});
  });

  it('inserts before an End node and reconnects all incoming paths',()=>{
    const graph:any={start:'start',nodes:[{id:'start',kind:'start'},{id:'decision',kind:'decision',condition:'ready'},{id:'a',kind:'end'},{id:'b',kind:'end'}],transitions:[{from:'start',to:'decision'},{from:'decision',to:'a',when:'true'},{from:'decision',to:'b',when:'false'}]};
    const updated=insertFlowchartAction(graph,'a',{id:'cleanup',type:'file_copy'},'Cleanup');
    expect(updated.transitions).toContainEqual({from:'decision',to:'node-cleanup',when:'true'});
    expect(updated.transitions).toContainEqual({from:'node-cleanup',to:'a',when:'always'});
  });
});
