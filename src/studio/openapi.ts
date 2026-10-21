import { parse } from 'yaml';

export type OpenApiParameter={name:string;in:'path'|'query'|'header';required:boolean;variable:string;description?:string};
export type OpenApiOperation={key:string;name:string;method:'GET'|'POST'|'PUT'|'PATCH';path:string;server:string;parameters:OpenApiParameter[];headers:Record<string,string>;query:Record<string,string>;body?:string;contentType?:string};
export type OpenApiImport={title:string;version:string;operations:OpenApiOperation[];warnings:string[]};
type Obj=Record<string,any>;
const METHODS=['get','post','put','patch'] as const;
const MAX_SPEC_BYTES=2_000_000;

function obj(value:unknown):value is Obj{return !!value&&typeof value==='object'&&!Array.isArray(value)}
function variableName(value:string):string{const parts=value.trim().replace(/([a-z0-9])([A-Z])/g,'$1 $2').split(/[^A-Za-z0-9]+/).filter(Boolean);let result=parts.map((part,index)=>index?part[0].toUpperCase()+part.slice(1):part.toLowerCase()).join('');if(!result)result='parameter';if(!/^[A-Za-z_]/.test(result))result=`value${result}`;return result.slice(0,60)}
function resolveRef(root:Obj,value:unknown,stack:string[]=[]):unknown{
  if(!obj(value)||typeof value.$ref!=='string')return value;
  const ref=value.$ref as string;
  if(!ref.startsWith('#/'))throw new Error(`External OpenAPI reference is not imported: ${ref.slice(0,160)}`);
  if(stack.includes(ref))return {};
  let target:unknown=root;
  for(const raw of ref.slice(2).split('/')){const key=raw.replace(/~1/g,'/').replace(/~0/g,'~');if(!obj(target)||!(key in target))throw new Error(`OpenAPI reference was not found: ${ref.slice(0,160)}`);target=target[key];}
  return resolveRef(root,target,[...stack,ref]);
}
function sample(schema:unknown,root:Obj,depth=0):unknown{
  if(depth>7||!obj(schema))return null;
  const resolved=resolveRef(root,schema);if(resolved!==schema)return sample(resolved,root,depth+1);
  if('example'in schema)return schema.example;if('default'in schema)return schema.default;
  if(Array.isArray(schema.enum)&&schema.enum.length)return schema.enum[0];
  if(Array.isArray(schema.oneOf)&&schema.oneOf.length)return sample(schema.oneOf[0],root,depth+1);
  if(Array.isArray(schema.anyOf)&&schema.anyOf.length)return sample(schema.anyOf[0],root,depth+1);
  if(schema.type==='object'||obj(schema.properties)){
    const output:Obj=Object.create(null);for(const [key,value] of Object.entries(obj(schema.properties)?schema.properties:{}).slice(0,50)){const result=sample(value,root,depth+1);if(result!==null)output[key]=result;}return output;
  }
  if(schema.type==='array')return [];
  if(schema.type==='integer'||schema.type==='number')return 0;
  if(schema.type==='boolean')return false;
  if(schema.type==='string')return '';
  return null;
}
function serverFor(root:Obj,pathItem:Obj,operation:Obj):string{return [operation.servers?.[0]?.url,pathItem.servers?.[0]?.url,root.servers?.[0]?.url].find(value=>typeof value==='string')??''}

export function parseOpenApi(text:string):OpenApiImport{
  if(typeof text!=='string'||new TextEncoder().encode(text).byteLength>MAX_SPEC_BYTES)throw new Error('OpenAPI file must be no larger than 2 MB');
  let root:unknown;try{root=parse(text,{maxAliasCount:50,uniqueKeys:true})}catch(error){throw new Error(`OpenAPI YAML/JSON could not be parsed: ${error instanceof Error?error.message:String(error)}`)}
  if(!obj(root)||typeof root.openapi!=='string'||!/^3\.(0|1)\./.test(root.openapi))throw new Error('Import requires an OpenAPI 3.0 or 3.1 document');
  if(!obj(root.paths))throw new Error('OpenAPI document has no paths object');
  const warnings:string[]=[];const operations:OpenApiOperation[]=[];
  if(root.security||obj(root.components)&&root.components.securitySchemes)warnings.push('Authentication schemes are not imported; configure authentication on the saved API connection.');
  pathsLoop:for(const [path,pathValue] of Object.entries(root.paths)){
    if(!path.startsWith('/')||path.length>1024||!obj(pathValue))continue;
    let pathItem:Obj;try{pathItem=resolveRef(root,pathValue) as Obj;if(!obj(pathItem))continue}catch(error){warnings.push(String(error));continue;}
    const common=Array.isArray(pathItem.parameters)?pathItem.parameters:[];
    for(const methodKey of METHODS){const raw=pathItem[methodKey];if(!obj(raw))continue;const operation=resolveRef(root,raw) as Obj;if(!obj(operation))continue;
      if(operation.security)warnings.push('Operation-specific security schemes are not imported; configure authentication on the saved API connection.');
      if(operations.length>=500){warnings.push('Only the first 500 supported operations are imported.');break pathsLoop;}
      const candidates=[...common,...(Array.isArray(operation.parameters)?operation.parameters:[])];const merged=new Map<string,Obj>();
      for(const candidate of candidates){try{const parameter=resolveRef(root,candidate);if(!obj(parameter)||typeof parameter.name!=='string'||!['path','query','header'].includes(parameter.in))continue;merged.set(`${parameter.in}:${parameter.name}`,parameter);}catch(error){warnings.push(`${methodKey.toUpperCase()} ${path}: ${String(error)}`)}}
      const parameters:OpenApiParameter[]=[];const query:Record<string,string>={};const headers:Record<string,string>={};const variableOwners=new Set<string>();
      const locationCounts={path:0,query:0,header:0};
      for(const parameter of merged.values()){
        if(parameter.in==='header'&&['authorization','cookie','set-cookie','host','proxy-authorization'].includes(parameter.name.toLowerCase())){warnings.push(`${methodKey.toUpperCase()} ${path}: sensitive header parameter ${parameter.name} was not imported; configure credentials on the saved API connection.`);continue;}
        const location=parameter.in as OpenApiParameter['in'];const limit=location==='query'?100:location==='header'?49:50;if(locationCounts[location]>=limit){warnings.push(`${methodKey.toUpperCase()} ${path}: skipped ${location} parameters beyond the ${limit}-parameter import limit.`);continue;}locationCounts[location]++;
        const variableBase=variableName(parameter.name);let variable=`${location==='path'?'path':location==='query'?'query':'header'}${variableBase[0].toUpperCase()}${variableBase.slice(1)}`;let suffix=2;while(variableOwners.has(variable.toLowerCase()))variable=`${variableBase}${suffix++}`;variableOwners.add(variable.toLowerCase());
        const info:OpenApiParameter={name:parameter.name,in:location,required:parameter.required===true||location==='path',variable,...(typeof parameter.description==='string'?{description:parameter.description.slice(0,500)}:{})};parameters.push(info);
        const expression=`{{ ${variable} }}`;if(location==='query')query[parameter.name]=expression;if(location==='header'&&!['authorization','cookie','host'].includes(parameter.name.toLowerCase()))headers[parameter.name]=expression;
      }
      let body:string|undefined;let contentType:string|undefined;
      try{const requestBody=resolveRef(root,operation.requestBody);const content=obj(requestBody)&&obj(requestBody.content)?requestBody.content:{};const media=Object.entries(content).find(([type])=>type==='application/json'||type.endsWith('+json'));
        if(media){contentType=media[0];const value=media[1];if(obj(value)){let example=value.example;if(example===undefined&&obj(value.examples))example=Object.values(value.examples).find(obj)?.value;if(example===undefined)example=sample(value.schema,root);if(example!==null&&example!==undefined){const serialized=JSON.stringify(example,null,2);if(serialized.length<=65_536)body=serialized;else warnings.push(`${methodKey.toUpperCase()} ${path}: request-body example exceeds 64 KB and was not imported.`);}}}
        else if(Object.keys(content).length)warnings.push(`${methodKey.toUpperCase()} ${path}: only JSON request bodies can be filled into API Request; other media types were left blank.`);
      }catch(error){warnings.push(`${methodKey.toUpperCase()} ${path}: ${String(error)}`)}
      if(body&&contentType)headers['Content-Type']=contentType;
      const method=methodKey.toUpperCase() as OpenApiOperation['method'];const name=String(operation.summary??operation.operationId??`${method} ${path}`).slice(0,200);const key=`${method} ${path}`;
      operations.push({key,name,method,path,server:serverFor(root,pathItem,operation),parameters,headers,query,...(body!==undefined?{body}:{}),...(contentType?{contentType}:{})});
    }
  }
  if(!operations.length)throw new Error('No supported GET/POST/PUT/PATCH operations were found in this OpenAPI document');
  return {title:typeof root.info?.title==='string'?root.info.title:'Imported OpenAPI',version:typeof root.info?.version==='string'?root.info.version:'',operations,warnings:[...new Set(warnings)].slice(0,50)};
}

export function configureFromOpenApi(operation:OpenApiOperation){
  let path=operation.path;
  for(const parameter of operation.parameters.filter(item=>item.in==='path'))path=path.split(`{${parameter.name}}`).join(`{{ ${parameter.variable} }}`);
  const query=Object.fromEntries(operation.parameters.filter(item=>item.in==='query'&&item.required).map(item=>[item.name,`{{ ${item.variable} }}`]));
  const headers=Object.fromEntries(operation.parameters.filter(item=>item.in==='header'&&item.required&&!['authorization','cookie','host','content-type'].includes(item.name.toLowerCase())).map(item=>[item.name,`{{ ${item.variable} }}`]));
  if(operation.contentType)headers['Content-Type']=operation.contentType;
  return {method:operation.method,path,query,headers,...(operation.body!==undefined?{body:operation.body}:{})};
}

export function configureOpenApiOperation(operation:OpenApiOperation,existingVariables:{name:string}[]){
  const used=new Set(existingVariables.map(item=>item.name.toLowerCase()));
  const parameters=operation.parameters.map(parameter=>{let name=parameter.variable;let suffix=2;while(used.has(name.toLowerCase()))name=`${parameter.variable}${suffix++}`;used.add(name.toLowerCase());return {...parameter,variable:name};});
  const required=parameters.filter(parameter=>parameter.required);
  return {patch:configureFromOpenApi({...operation,parameters:required}),parameters,variables:required.map(parameter=>({name:parameter.variable,type:'string' as const,value:''}))};
}
