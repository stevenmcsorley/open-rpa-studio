import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe,expect,it } from 'vitest';
import { WorkflowArgumentInputs } from './WorkflowArgumentInputs';
import type { Argument } from './types';

describe('WorkflowArgumentInputs',()=>{
  it('renders typed inputs and excludes output-only arguments',()=>{
    const arguments_:Argument[]=[{name:'client',type:'string',direction:'in'},{name:'dryRun',type:'boolean',direction:'in',default:true},{name:'result',type:'object',direction:'out'}];
    const html=renderToStaticMarkup(createElement(WorkflowArgumentInputs,{arguments_,values:{client:'Contoso',dryRun:'true'},errors:{},onChange:()=>undefined}));
    expect(html).toContain('WORKFLOW INPUTS');
    expect(html).toContain('aria-label="Input argument client"');
    expect(html).toContain('value="Contoso"');
    expect(html).toContain('Choose…');
    expect(html).not.toContain('Input argument result');
  });

  it('renders required input errors accessibly',()=>{
    const html=renderToStaticMarkup(createElement(WorkflowArgumentInputs,{arguments_:[{name:'supplier',type:'string',direction:'in'}],values:{supplier:''},errors:{supplier:'This required input is missing.'},onChange:()=>undefined}));
    expect(html).toContain('role="alert"');
    expect(html).toContain('This required input is missing.');
  });

  it('renders combined input size errors',()=>{
    const html=renderToStaticMarkup(createElement(WorkflowArgumentInputs,{arguments_:[{name:'payload',type:'string',direction:'in'}],values:{payload:'x'},errors:{},formError:'Combined workflow inputs exceed the 2 MB execution limit.',onChange:()=>undefined}));
    expect(html).toContain('Combined workflow inputs exceed the 2 MB execution limit.');
  });
});
