import { describe,expect,it } from 'vitest';
import { parseRunInputs,runInputDefaults } from './runInputs';
import type { Argument } from './types';

const args:Argument[]=[
  {name:'supplier',type:'string',direction:'in'},
  {name:'limit',type:'integer',direction:'in'},
  {name:'enabled',type:'boolean',direction:'in'},
  {name:'options',type:'object',direction:'in'},
  {name:'labels',type:'array',direction:'in'},
  {name:'mode',type:'string',direction:'in',default:'summary'},
  {name:'result',type:'string',direction:'out'},
];

describe('run input arguments',()=>{
  it('parses typed inputs, applies defaults, and excludes output arguments',()=>{
    expect(runInputDefaults(args)).toEqual({supplier:'',limit:'',enabled:'',options:'',labels:'',mode:'summary'});
    expect(parseRunInputs(args,{supplier:'Northwind',limit:'12',enabled:'false',options:'{"region":"north"}',labels:'["approved"]',mode:'detail'})).toEqual({inputs:{supplier:'Northwind',limit:12,enabled:false,options:{region:'north'},labels:['approved'],mode:'detail'},errors:{}});
  });

  it('reports missing required and malformed typed values by argument name',()=>{
    expect(parseRunInputs(args,{supplier:'',limit:'1.2',enabled:'yes',options:'[]',labels:'{}',mode:'summary'}).errors).toEqual({supplier:'This required input is missing.',limit:'Enter a whole number within the safe integer range.',enabled:'Choose true or false.',options:'Enter a JSON object.',labels:'Enter a JSON array.'});
  });

  it('does not require optional inputs without defaults',()=>{
    const optional:Argument[]=[{name:'memo',type:'string',direction:'in',required:false}];
    expect(parseRunInputs(optional,{memo:''})).toEqual({inputs:{},errors:{}});
  });

  it('rejects non-finite nested JSON values and inputs beyond the engine size limit',()=>{
    const data:Argument[]=[{name:'payload',type:'any',direction:'in'}];
    expect(parseRunInputs(data,{payload:'{"amount":1e999}'}).errors.payload).toBe('JSON numbers must be finite.');
    expect(parseRunInputs(data,{payload:`"${'x'.repeat(2_000_001)}"`}).formError).toBe('Combined workflow inputs exceed the 2 MB execution limit.');
  });

  it('handles prototype-like argument names as ordinary field keys',()=>{
    const unusual:Argument[]=[{name:'__proto__',type:'integer',direction:'in'}];
    expect(parseRunInputs(unusual,Object.fromEntries([['__proto__','not a number']])).errors['__proto__']).toBe('Enter a whole number within the safe integer range.');
    expect(parseRunInputs(unusual,Object.fromEntries([['__proto__','42']])).inputs['__proto__']).toBe(42);
  });

  it('treats legacy arguments without a type as JSON any values',()=>{
    const legacy=[{name:'configuration',direction:'in',default:{mode:'safe'}}] as Argument[];
    expect(runInputDefaults(legacy)).toEqual({configuration:'{"mode":"safe"}'});
    expect(parseRunInputs(legacy,{configuration:'{"mode":"fast"}'}).inputs).toEqual({configuration:{mode:'fast'}});
  });
});
