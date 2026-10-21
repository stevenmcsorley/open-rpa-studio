import { parseOpenApi, type OpenApiImport } from './openapi';

export type OpenApiConnectorPackage={format:'openrpa.openapi-connector';formatVersion:1;name:string;specification:string;sha256:string};
// JSON escaping can expand a valid 2 MB YAML document (for example, one
// containing many line breaks), so the package envelope has a separate cap.
const MAX_PACKAGE_BYTES=12_100_000;

async function digest(text:string):Promise<string>{
  if(!globalThis.crypto?.subtle)throw new Error('Connector package integrity checks require Web Crypto support.');
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return [...new Uint8Array(bytes)].map(value=>value.toString(16).padStart(2,'0')).join('');
}

export async function createOpenApiConnectorPackage(specification:string,name:string):Promise<OpenApiConnectorPackage>{
  const parsed=parseOpenApi(specification);
  const safeName=name.trim().slice(0,160)||parsed.title;
  return {format:'openrpa.openapi-connector',formatVersion:1,name:safeName,specification,sha256:await digest(specification)};
}

export async function parseOpenApiConnectorPackage(text:string):Promise<{connector:OpenApiConnectorPackage;openApi:OpenApiImport}>{
  if(new TextEncoder().encode(text).byteLength>MAX_PACKAGE_BYTES)throw new Error('Connector package must be no larger than 12.1 MB.');
  let value:unknown;try{value=JSON.parse(text)}catch{throw new Error('Connector package is not valid JSON.')}
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('Connector package must be a JSON object.');
  const candidate=value as Record<string,unknown>;
  if(candidate.format!=='openrpa.openapi-connector'||candidate.formatVersion!==1)throw new Error('Unsupported OpenAPI connector package format or version.');
  if(typeof candidate.name!=='string'||candidate.name.length>160||typeof candidate.specification!=='string'||typeof candidate.sha256!=='string'||!/^[a-f0-9]{64}$/.test(candidate.sha256))throw new Error('Connector package metadata is invalid.');
  const actual=await digest(candidate.specification);
  if(actual!==candidate.sha256)throw new Error('Connector package integrity check failed: specification SHA-256 does not match.');
  const openApi=parseOpenApi(candidate.specification);
  return {connector:{format:'openrpa.openapi-connector',formatVersion:1,name:candidate.name,specification:candidate.specification,sha256:actual},openApi};
}

export function serializeOpenApiConnectorPackage(value:OpenApiConnectorPackage):string{return `${JSON.stringify(value,null,2)}\n`;}
