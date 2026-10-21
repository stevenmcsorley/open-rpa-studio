import type { Argument } from './types';
import { editableRunArguments } from './runInputs';
import './WorkflowArgumentInputs.css';

const typeOf=(argument:Argument)=>argument.type??'any';

export function WorkflowArgumentInputs({arguments_,values,errors,formError,onChange}:{arguments_:Argument[];values:Record<string,string>;errors:Record<string,string>;formError?:string;onChange:(name:string,value:string)=>void}){
  const args=editableRunArguments(arguments_);
  if(!args.length)return null;
  const fieldValue=(name:string)=>Object.hasOwn(values,name)?values[name]??'':'';
  return <section className="run-argument-fields" aria-label="Workflow input arguments">
    <header><strong>WORKFLOW INPUTS</strong><small>Run-scoped values. Do not enter secrets; activities can log or send inputs.</small></header>
    {formError&&<small className="run-argument-error" role="alert">{formError}</small>}
    {args.map(argument=><label className="run-argument-field" key={argument.name}>
      <span><strong>{argument.name}</strong><small>{typeOf(argument)}{argument.required===false?' · optional':' · required'}{Object.hasOwn(argument,'default')?' · default available':''}</small></span>
      {typeOf(argument)==='boolean'?<select aria-label={`Input argument ${argument.name}`} value={fieldValue(argument.name)} onChange={event=>onChange(argument.name,event.target.value)}><option value="">Choose…</option><option value="true">True</option><option value="false">False</option></select>:typeOf(argument)==='object'||typeOf(argument)==='array'||typeOf(argument)==='any'?<textarea aria-label={`Input argument ${argument.name}`} rows={3} spellCheck={false} placeholder={typeOf(argument)==='array'?'["value"]':typeOf(argument)==='object'?'{"key":"value"}':'JSON value'} value={fieldValue(argument.name)} onChange={event=>onChange(argument.name,event.target.value)}/>:<input aria-label={`Input argument ${argument.name}`} type={typeOf(argument)==='integer'||typeOf(argument)==='number'?'number':'text'} step={typeOf(argument)==='integer'?'1':typeOf(argument)==='number'?'any':undefined} value={fieldValue(argument.name)} onChange={event=>onChange(argument.name,event.target.value)}/>}
      {Object.hasOwn(errors,argument.name)&&<small className="run-argument-error" role="alert">{errors[argument.name]}</small>}
    </label>)}
  </section>;
}
