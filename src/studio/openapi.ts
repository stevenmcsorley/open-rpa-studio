import { parse } from 'yaml';
import type { ApiConnectionProfile } from './bridge';
import type { Workflow } from './types';

export type OpenApiParameter={name:string;in:'path'|'query'|'header';required:boolean;variable:string;description?:string};
export type ApiResponseField={name:string;path?:string;expression?:string};
export type OpenApiResponseMapping={responseCode:string;itemsPointer:string;fields:ApiResponseField[]};
export type ApiResponseMapping=OpenApiResponseMapping&{result:string;maxItems:number;maxOutputBytes:number};
export type OpenApiAuthHint={name:string;kind:'bearer'|'api_key_header'|'oauth_client_credentials'|'oauth_authorization_code'|'unsupported';detail:string;headerName?:string;tokenUrl?:string;authorizationUrl?:string;scopes?:string[]};
export type OpenApiSecurityAlternative={schemes:OpenApiAuthHint[]};
export type OpenApiOperation={key:string;name:string;method:'GET'|'POST'|'PUT'|'PATCH'|'DELETE';path:string;server:string;parameters:OpenApiParameter[];headers:Record<string,string>;query:Record<string,string>;securityAlternatives?:OpenApiSecurityAlternative[];body?:string;contentType?:string;responseMapping?:OpenApiResponseMapping};
export type OpenApiImport={title:string;version:string;operations:OpenApiOperation[];warnings:string[]};
export type OpenApiConnectionSeed=Omit<ApiConnectionProfile,'id'|'credentialStored'|'clientSecretStored'>;
type Obj=Record<string,any>;
const METHODS=['get','post','put','patch','delete'] as const;
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
function pointer(parts:string[]):string{return parts.map(part=>`/${part.replace(/~/g,'~0').replace(/\//g,'~1')}`).join('')}
function schemaFields(schema:unknown,root:Obj,prefix:string,depth=0,used=new Set<string>()):ApiResponseField[]{
  if(depth>4||!obj(schema))return [];
  let current:unknown;try{current=resolveRef(root,schema)}catch{return []}
  if(!obj(current))return [];
  const primitive=['string','integer','number','boolean'].includes(current.type)||Array.isArray(current.enum)&&current.enum.length>0;
  if(primitive&&prefix){let name=variableName(prefix.split('/').filter(Boolean).map(part=>part.replace(/~1/g,'/').replace(/~0/g,'~')).join('_'));const base=name;let suffix=2;while(used.has(name.toLowerCase()))name=`${base}${suffix++}`;used.add(name.toLowerCase());return [{name,path:prefix}]}
  if(current.type==='object'||obj(current.properties)){
    const fields:ApiResponseField[]=[];
    for(const [key,value] of Object.entries(obj(current.properties)?current.properties:{}).slice(0,100)){
      fields.push(...schemaFields(value,root,`${prefix}/${key.replace(/~/g,'~0').replace(/\//g,'~1')}`,depth+1,used));if(fields.length>=50)break;
    }
    return fields.slice(0,50);
  }
  return [];
}
function arraySchemas(schema:unknown,root:Obj,prefix:string,depth=0):{itemsPointer:string;itemSchema:unknown}[]{
  if(depth>8||!obj(schema))return [];
  let current:unknown;try{current=resolveRef(root,schema)}catch{return []}
  if(!obj(current))return [];
  if(current.type==='array'){
    let item:unknown;try{item=resolveRef(root,current.items)}catch{return []}
    if(obj(item)&&(item.type==='object'||obj(item.properties)))return [{itemsPointer:prefix,itemSchema:item}];
    return [];
  }
  if(current.type==='object'||obj(current.properties)){
    const found:{itemsPointer:string;itemSchema:unknown}[]=[];
    for(const [key,value] of Object.entries(obj(current.properties)?current.properties:{}).slice(0,100))found.push(...arraySchemas(value,root,`${prefix}/${key.replace(/~/g,'~0').replace(/\//g,'~1')}`,depth+1));
    return found.slice(0,100);
  }
  return [];
}
function responseMapping(operation:Obj,root:Obj,method:string,path:string,warnings:string[]):OpenApiResponseMapping|undefined{
  const label=`${method.toUpperCase()} ${path}`;
  try{
    const responses=resolveRef(root,operation.responses);if(!obj(responses)){warnings.push(`${label}: no response object was available for response mapping.`);return}
    const success=Object.keys(responses).filter(code=>/^2\d\d$/.test(code)).sort((a,b)=>a==='200'?-1:b==='200'?1:Number(a)-Number(b));
    if(!success.length)return;
    let code='';let schema:unknown;
    for(const candidate of success){
      const response=resolveRef(root,responses[candidate]);if(!obj(response)||!obj(response.content))continue;
      const media=Object.entries(response.content).find(([type])=>type==='application/json'||type.endsWith('+json'));
      if(media&&obj(media[1])&&obj(media[1].schema)){code=candidate;schema=media[1].schema;break;}
    }
    if(!code||!obj(schema))return;
    try{resolveRef(root,schema)}catch(error){warnings.push(`${label}: response mapping was not imported: ${String(error)}`);return}
    const arrays=arraySchemas(schema,root,'');
    if(arrays.length!==1){if(arrays.length>1)warnings.push(`${label}: response ${code} has multiple JSON object arrays; automatic response mapping was left unset.`);return}
    const fields=schemaFields(arrays[0].itemSchema,root,'');
    if(!fields.length){warnings.push(`${label}: response ${code} has an object array but no supported scalar fields for mapping.`);return}
    return {responseCode:code,itemsPointer:arrays[0].itemsPointer,fields};
  }catch(error){warnings.push(`${label}: response mapping was not imported: ${String(error)}`);return}
}
function securityAlternatives(operation:Obj,root:Obj,label:string,warnings:string[]):OpenApiSecurityAlternative[]|undefined{
  const requirements=Array.isArray(operation.security)?operation.security:Array.isArray(root.security)?root.security:undefined;
  if(requirements===undefined)return;
  const schemes=obj(root.components)&&obj(root.components.securitySchemes)?root.components.securitySchemes:{};
  return requirements.slice(0,20).map((requirement,index)=>{
    if(!obj(requirement)){warnings.push(`${label}: ignored malformed OpenAPI security alternative ${index+1}.`);return {schemes:[]}}
    const hints:OpenApiAuthHint[]=[];
    for(const name of Object.keys(requirement).slice(0,20)){
      let scheme:unknown;
      try{scheme=resolveRef(root,schemes[name])}catch(error){warnings.push(`${label}: security scheme ${name} could not be resolved: ${String(error)}`);hints.push({name,kind:'unsupported',detail:'Unresolved security scheme'});continue}
      if(!obj(scheme)){hints.push({name,kind:'unsupported',detail:'Security scheme is missing'});continue}
      const requiredScopes=Array.isArray(requirement[name])?requirement[name].filter((scope:unknown):scope is string=>typeof scope==='string').slice(0,50):[];
      if(scheme.type==='http'&&String(scheme.scheme).toLowerCase()==='bearer')hints.push({name,kind:'bearer',detail:'Bearer token'});
      else if(scheme.type==='apiKey'&&scheme.in==='header'&&typeof scheme.name==='string'&&/^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$/.test(scheme.name)&&!['authorization','cookie','set-cookie','host','connection','content-length','transfer-encoding','proxy-authorization','content-type'].includes(scheme.name.toLowerCase()))hints.push({name,kind:'api_key_header',detail:`API key in ${scheme.name}`,headerName:scheme.name});
      else if(scheme.type==='oauth2'&&obj(scheme.flows)&&obj(scheme.flows.clientCredentials)){
        const flow=scheme.flows.clientCredentials;let validTokenUrl=false;
        if(typeof flow.tokenUrl==='string'){try{const parsed=new URL(flow.tokenUrl);validTokenUrl=parsed.protocol==='https:'&&!parsed.username&&!parsed.password&&!parsed.search&&!parsed.hash}catch{/* Relative and malformed token URLs need manual resolution before connection setup. */}}
        if(!validTokenUrl)hints.push({name,kind:'unsupported',detail:'OAuth client-credentials token URL is missing or incompatible with saved connections; configure an absolute public HTTPS URL without query or fragment'});
        else hints.push({name,kind:'oauth_client_credentials',detail:'OAuth 2.0 client credentials',tokenUrl:flow.tokenUrl,scopes:requiredScopes});
      }else if(scheme.type==='oauth2'&&obj(scheme.flows)&&obj(scheme.flows.authorizationCode)){
        const flow=scheme.flows.authorizationCode;let validAuthorizationUrl=false,validTokenUrl=false;
        if(typeof flow.authorizationUrl==='string'){try{const parsed=new URL(flow.authorizationUrl);validAuthorizationUrl=parsed.protocol==='https:'&&!parsed.username&&!parsed.password&&!parsed.search&&!parsed.hash}catch{/* Dynamic endpoints require manual correction. */}}
        if(typeof flow.tokenUrl==='string'){try{const parsed=new URL(flow.tokenUrl);validTokenUrl=parsed.protocol==='https:'&&!parsed.username&&!parsed.password&&!parsed.search&&!parsed.hash}catch{/* Dynamic endpoints require manual correction. */}}
        if(!validAuthorizationUrl||!validTokenUrl)hints.push({name,kind:'unsupported',detail:'OAuth authorization-code URLs are missing or incompatible; configure absolute public HTTPS authorization and token URLs'});
        else hints.push({name,kind:'oauth_authorization_code',detail:'OAuth 2.0 authorization code with PKCE',authorizationUrl:flow.authorizationUrl,tokenUrl:flow.tokenUrl,scopes:requiredScopes});
      }else hints.push({name,kind:'unsupported',detail:`${String(scheme.type??'Unknown')} authentication is not supported by saved API connections`});
    }
    return {schemes:hints};
  });
}

export function parseOpenApi(text:string):OpenApiImport{
  if(typeof text!=='string'||new TextEncoder().encode(text).byteLength>MAX_SPEC_BYTES)throw new Error('OpenAPI file must be no larger than 2 MB');
  let root:unknown;try{root=parse(text,{maxAliasCount:50,uniqueKeys:true})}catch(error){throw new Error(`OpenAPI YAML/JSON could not be parsed: ${error instanceof Error?error.message:String(error)}`)}
  if(!obj(root)||typeof root.openapi!=='string'||!/^3\.(0|1)\./.test(root.openapi))throw new Error('Import requires an OpenAPI 3.0 or 3.1 document');
  if(!obj(root.paths))throw new Error('OpenAPI document has no paths object');
  const warnings:string[]=[];const operations:OpenApiOperation[]=[];
  pathsLoop:for(const [path,pathValue] of Object.entries(root.paths)){
    if(!path.startsWith('/')||path.length>1024||!obj(pathValue))continue;
    let pathItem:Obj;try{pathItem=resolveRef(root,pathValue) as Obj;if(!obj(pathItem))continue}catch(error){warnings.push(String(error));continue;}
    const common=Array.isArray(pathItem.parameters)?pathItem.parameters:[];
    for(const methodKey of METHODS){const raw=pathItem[methodKey];if(!obj(raw))continue;const operation=resolveRef(root,raw) as Obj;if(!obj(operation))continue;
      if(operations.length>=500){warnings.push('Only the first 500 supported operations are imported.');break pathsLoop;}
      const candidates=[...common,...(Array.isArray(operation.parameters)?operation.parameters:[])];const merged=new Map<string,Obj>();
      for(const candidate of candidates){try{const parameter=resolveRef(root,candidate);if(!obj(parameter)||typeof parameter.name!=='string'||!['path','query','header'].includes(parameter.in))continue;merged.set(`${parameter.in}:${parameter.name}`,parameter);}catch(error){warnings.push(`${methodKey.toUpperCase()} ${path}: ${String(error)}`)}}
      const parameters:OpenApiParameter[]=[];const query:Record<string,string>={};const headers:Record<string,string>={};const variableOwners=new Set<string>();
      const locationCounts={path:0,query:0,header:0};
      for(const parameter of merged.values()){
        if(parameter.in==='header'&&(['authorization','cookie','set-cookie','host','proxy-authorization'].includes(parameter.name.toLowerCase())||/(token|secret|api[-_]?key|apikey|password|credential)/i.test(parameter.name))){warnings.push(`${methodKey.toUpperCase()} ${path}: sensitive header parameter ${parameter.name} was not imported; configure credentials on the saved API connection.`);continue;}
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
      const mappedResponse=responseMapping(operation,root,methodKey,path,warnings);
      const auth=securityAlternatives(operation,root,key,warnings);
      operations.push({key,name,method,path,server:serverFor(root,pathItem,operation),parameters,headers,query,...(auth?{securityAlternatives:auth}:{}),...(body!==undefined?{body}:{}),...(contentType?{contentType}:{}),...(mappedResponse?{responseMapping:mappedResponse}:{})});
    }
  }
  if(!operations.length)throw new Error('No supported GET/POST/PUT/PATCH/DELETE operations were found in this OpenAPI document');
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
  let response:ApiResponseMapping|undefined;
  if(operation.responseMapping){let result='apiItems';let suffix=2;while(used.has(result.toLowerCase()))result=`apiItems${suffix++}`;used.add(result.toLowerCase());response={...operation.responseMapping,result,maxItems:10_000,maxOutputBytes:5_000_000};}
  const patch={...configureFromOpenApi({...operation,parameters:required}),responseMapping:response,pagination:undefined,...(operation.method!=='GET'||operation.body!==undefined?{retryPolicy:undefined}:{})};
  return {patch,parameters,variables:required.map(parameter=>({name:parameter.variable,type:'string' as const,value:''}))};
}

export function createReusableApiWorkflow(operation:OpenApiOperation,connectionId:string,name:string):Workflow{
  if(!connectionId.trim())throw new Error('Choose a saved API connection before generating a reusable workflow.');
  if(!name.trim()||name.length>200)throw new Error('Reusable API workflow name must contain 1–200 characters.');
  const configured=configureOpenApiOperation(operation,[]);
  const restrictedHeader=/^(authorization|cookie|set-cookie|host|connection|content-length|transfer-encoding|proxy-authorization)$/i;
  if(configured.parameters.some(parameter=>parameter.in==='header'&&(restrictedHeader.test(parameter.name)||/(token|secret|api[-_]?key|password|credential)/i.test(parameter.name))))
    throw new Error('This operation declares a credential-like header parameter. Configure it as authentication on the saved API connection instead of exposing it as a workflow input.');
  if(configured.parameters.some(parameter=>parameter.in==='path'&&!parameter.required))
    throw new Error('OpenAPI path parameters must be required before a reusable workflow can be generated.');
  const request=configureFromOpenApi({...operation,parameters:configured.parameters.map(parameter=>({...parameter,required:true}))});
  const optionalQuery=configured.parameters.filter(parameter=>!parameter.required&&parameter.in==='query').map(parameter=>parameter.name);
  const optionalHeaders=configured.parameters.filter(parameter=>!parameter.required&&parameter.in==='header'&&Object.hasOwn(request.headers,parameter.name)).map(parameter=>parameter.name);
  const inputArguments=configured.parameters.map(parameter=>({name:parameter.variable,type:'string' as const,direction:'in' as const,required:parameter.required,...(!parameter.required?{default:''}:{})}));
  const used=new Set(inputArguments.map(argument=>argument.name.toLowerCase()));
  if(configured.patch.responseMapping)used.add(String(configured.patch.responseMapping.result).toLowerCase());
  const allocate=(base:string)=>{let candidate=base;let suffix=2;while(used.has(candidate.toLowerCase()))candidate=`${base}${suffix++}`;used.add(candidate.toLowerCase());return candidate};
  const responseName=allocate('apiResponse');
  const outputs:Workflow['arguments']=[{name:responseName,type:'object',direction:'out',required:false,target:responseName}];
  if(configured.patch.responseMapping){
    const mappedName=String(configured.patch.responseMapping.result);
    outputs.push({name:mappedName,type:'array' as const,direction:'out' as const,required:false,target:mappedName});
  }
  const activity:Workflow['activities'][number]={id:'api-request',type:'api_request',label:`Call ${operation.name}`,connectionId,...configured.patch,...request,...(optionalQuery.length?{omitEmptyQuery:optionalQuery}:{}),...(optionalHeaders.length?{omitEmptyHeaders:optionalHeaders}:{}),result:responseName};
  return {format:'openrpa.workflow',formatVersion:1,name,executionModel:'sequence',variables:[],arguments:[...inputArguments,...outputs],activities:[activity]};
}

export function connectionSeedFromOpenApi(operation:OpenApiOperation,title='Imported API'): {profile:OpenApiConnectionSeed;warning?:string}{
  let server:URL;
  try{server=new URL(operation.server)}catch{throw new Error('The OpenAPI operation has no absolute HTTPS server URL to use as a connection base.')}
  if(server.protocol!=='https:'||server.username||server.password||server.search||server.hash||/[{}]/.test(server.href))throw new Error('The OpenAPI server must be an absolute HTTPS URL without credentials, query, fragment, or template variables.');
  const profile:OpenApiConnectionSeed={name:`${title.trim()||'Imported API'} (${server.host})`.slice(0,100),baseUrl:server.href.replace(/\/$/,''),authType:'none',apiKeyHeader:'X-API-Key',headers:{},minIntervalSeconds:0,
    authorizationUrl:'https://auth.example.com/oauth/authorize',tokenUrl:'https://auth.example.com/oauth/token',clientId:'',scope:'',audience:'',clientAuthMethod:'client_secret_basic'};
  const alternatives=operation.securityAlternatives;
  if(!alternatives)return {profile};
  if(alternatives.length===0)return {profile};
  if(alternatives.length!==1||alternatives[0].schemes.length!==1)return {profile,warning:'The specification declares alternative or combined authentication schemes. No authentication was guessed; choose a supported method in the connection form.'};
  const scheme=alternatives[0].schemes[0];
  if(scheme.kind==='bearer')profile.authType='bearer';
  else if(scheme.kind==='api_key_header'&&scheme.headerName){profile.authType='api_key_header';profile.apiKeyHeader=scheme.headerName;}
  else if(scheme.kind==='oauth_client_credentials'&&scheme.tokenUrl){profile.authType='oauth_client_credentials';profile.tokenUrl=scheme.tokenUrl;profile.scope=(scheme.scopes??[]).join(' ');}
  else if(scheme.kind==='oauth_authorization_code'&&scheme.tokenUrl&&scheme.authorizationUrl){profile.authType='oauth_authorization_code';profile.tokenUrl=scheme.tokenUrl;profile.authorizationUrl=scheme.authorizationUrl;profile.scope=(scheme.scopes??[]).join(' ');profile.clientAuthMethod='none';}
  else return {profile,warning:`The declared ${scheme.detail||'authentication'} scheme cannot be preconfigured. Choose a supported method in the connection form.`};
  return {profile};
}
