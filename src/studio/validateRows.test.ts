import { describe, expect, it } from 'vitest';
import { run, validate } from './webEngine';
import type { Workflow } from './types';

describe('Validate Rows preview activity',()=>{
  it('splits records with explicit field-level failure reasons',async()=>{
    const rows=[{email:'ada@example.org',age:37},{email:'',age:'old'},{age:22},{email:'grace@example.org',age:null},{email:'huge@example.org',age:Number.MAX_SAFE_INTEGER+1},{email:'huge-float@example.org',age:1e20}];
    const workflow:Workflow={format:'openrpa.workflow',formatVersion:1,name:'Validate rows',variables:[{name:'rows',type:'array',value:rows}],arguments:[],activities:[{id:'validate',type:'validate_rows',rows:'rows',rules:[{field:'email',type:'text',required:true,nonEmpty:true},{field:'age',type:'number',required:true}],validResult:'accepted',invalidResult:'rejected'}]};
    expect(validate(workflow)).toEqual([]);const events:any[]=[];const result=await run(workflow,false,event=>events.push(event));
    expect(result.status).toBe('succeeded');expect(result.variables.accepted).toEqual([rows[0]]);expect(result.variables.rejected[0]).toEqual({row:rows[1],errors:[{field:'email',code:'empty',message:'Value must not be empty'},{field:'age',code:'type',message:'Expected number'}]});expect(result.variables.rejected[3].errors[0].code).toBe('type');expect(result.variables.rejected[4].errors[0].code).toBe('type');expect(events.some(event=>event.event==='data-validated'&&event.inputRows===6&&event.validRows===1&&event.invalidRows===5)).toBe(true);expect(result.variables.rows).toEqual(rows);
  });
  it('rejects duplicate result variables during validation',()=>{const workflow:Workflow={format:'openrpa.workflow',formatVersion:1,name:'Invalid',variables:[],arguments:[],activities:[{id:'validate',type:'validate_rows',rules:[{field:'id',type:'number'}],validResult:'same',invalidResult:'same'}]};expect(validate(workflow).some(problem=>problem.code==='validate-result-duplicate')).toBe(true)});
});
