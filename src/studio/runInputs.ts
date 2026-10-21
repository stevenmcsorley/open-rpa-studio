import type { Argument } from './types';

export type RunInputParseResult={inputs:Record<string,unknown>;errors:Record<string,string>;formError?:string};

function containsNonFiniteNumber(value:unknown):boolean{
  if(typeof value==='number')return !Number.isFinite(value);
  if(Array.isArray(value))return value.some(containsNonFiniteNumber);
  if(value&&typeof value==='object')return Object.values(value).some(containsNonFiniteNumber);
  return false;
}

export function editableRunArguments(arguments_:Argument[]):Argument[]{
  return arguments_.filter(argument=>(argument.direction??'in')!=='out');
}

export function runInputDefaults(arguments_:Argument[]):Record<string,string>{
  return Object.fromEntries(editableRunArguments(arguments_).map(argument=>[
    argument.name,
    Object.hasOwn(argument,'default')?(argument.type??'any')==='string'&&typeof argument.default==='string'?argument.default:JSON.stringify(argument.default):'',
  ]));
}

export function parseRunInputs(arguments_:Argument[],values:Record<string,string>):RunInputParseResult{
  const entries:[string,unknown][]=[];
  const errors:Record<string,string>={};
  for(const argument of editableRunArguments(arguments_)){
    const raw=Object.hasOwn(values,argument.name)?values[argument.name]??'':'';
    const hasDefault=Object.hasOwn(argument,'default');
    const type=argument.type??'any';
    if(raw.trim()===''&&!hasDefault){
      if(argument.required!==false)errors[argument.name]='This required input is missing.';
      continue;
    }
    try{
      let value:unknown;
      switch(type){
        case 'string': value=raw;break;
        case 'integer': {if(!raw.trim())throw new Error('Enter a whole number within the safe integer range.');const parsed=Number(raw.trim());if(!Number.isSafeInteger(parsed))throw new Error('Enter a whole number within the safe integer range.');value=parsed;break;}
        case 'number': {if(!raw.trim())throw new Error('Enter a finite number.');const parsed=Number(raw.trim());if(!Number.isFinite(parsed))throw new Error('Enter a finite number.');value=parsed;break;}
        case 'boolean': if(raw==='true')value=true;else if(raw==='false')value=false;else throw new Error('Choose true or false.');break;
        case 'array': case 'object': case 'any': {
          value=JSON.parse(raw);
          if(containsNonFiniteNumber(value))throw new Error('JSON numbers must be finite.');
          if(type==='array'&&!Array.isArray(value))throw new Error('Enter a JSON array.');
          if(type==='object'&&(value===null||Array.isArray(value)||typeof value!=='object'))throw new Error('Enter a JSON object.');
          break;
        }
        default: throw new Error(`Unsupported argument type “${type}”.`);
      }
      entries.push([argument.name,value]);
    }catch(error){Object.defineProperty(errors,argument.name,{value:error instanceof Error?error.message:'Enter a valid value.',enumerable:true,configurable:true,writable:true});}
  }
  const inputs=Object.fromEntries(entries);
  if(Object.keys(errors).length)return {inputs,errors};
  const size=new TextEncoder().encode(JSON.stringify(inputs)).length;
  if(size>2_000_000)return {inputs,errors,formError:'Combined workflow inputs exceed the 2 MB execution limit.'};
  return {inputs,errors};
}
