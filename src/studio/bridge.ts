import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import type { BridgeResult, CatalogEntry, Project, RunResult, Workflow } from './types';

const inDesktop = () => '__TAURI_INTERNALS__' in window;
export async function rpc(method: string, params: Record<string, unknown> = {}): Promise<any> {
  if (inDesktop()) return invoke('bridge_request', { method, params });
  return localRpc(method, params);
}

let localEngine: Worker | undefined;
let sequence = 0;
const pending = new Map<number, {resolve:(v:any)=>void;reject:(e:Error)=>void}>();
function localRpc(method:string, params:Record<string,unknown>):Promise<any> {
  if (!localEngine) {
    localEngine = new Worker(new URL('./local-engine.worker.ts', import.meta.url), {type:'module'});
    localEngine.onmessage = ({data}) => {
      if (data.event === 'run.event') { window.dispatchEvent(new CustomEvent('openrpa-run-event',{detail:data.data})); return; }
      const p = pending.get(data.id); if (!p) return; pending.delete(data.id);
      data.error ? p.reject(new Error(data.error.message)) : p.resolve(data.result);
    };
  }
  const id=++sequence; return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});localEngine!.postMessage({id,method,params});});
}
export async function openProject(path:string):Promise<BridgeResult>{return rpc('project.open',{path});}
export async function createProject(path:string,name:string):Promise<BridgeResult>{return rpc('project.create',{path,name});}
export async function saveProject(root:string,project:Project,workflows:Record<string,Workflow>):Promise<void>{await rpc('project.save',{root,project,workflows});}
export async function validateWorkflow(project:Project,workflow:Workflow):Promise<{valid:boolean;problems:{message:string;code:string;activityId?:string}[]}>{return rpc('workflow.validate',{project,workflow});}
export async function runWorkflow(project:Project,root:string,workflow:string,allowNetwork:boolean,allowDesktop=false,debug=false):Promise<RunResult>{return rpc('workflow.run',{project,root,workflow,allowNetwork,allowDesktop,debug});}
export async function cancelWorkflow():Promise<void>{await rpc('workflow.cancel');}
export async function debugControl(action:'pause'|'resume'|'step_over'|'step_into'|'step_out'):Promise<void>{await rpc(`debug.${action}`);}
export async function setDebugVariable(name:string,value:unknown):Promise<void>{await rpc('debug.set_variable',{name,value});}
export type BrowserControl={selectorKind:'role'|'test_id'|'placeholder';selector:string;role:string;name:string;tag:string;inputType:string;placeholder:string;matchCount:number;actions:string[]};
export async function openBrowserInspector(url:string,allowNetwork:boolean):Promise<{url:string;title:string;status:number|null}>{return rpc('browser.inspect.open',{url,allowNetwork});}
export async function readBrowserInspectorControls():Promise<{url:string;title:string;controls:BrowserControl[];truncated:boolean}>{return rpc('browser.inspect.controls');}
export async function startBrowserRecording(allowNetwork:boolean):Promise<{recording:boolean;url:string}>{return rpc('browser.inspect.record.start',{allowNetwork});}
export async function stopBrowserRecording():Promise<{recording:boolean;url:string;events:Record<string,unknown>[];truncated:boolean}>{return rpc('browser.inspect.record.stop');}
export async function closeBrowserInspector():Promise<void>{await rpc('browser.inspect.close');}
export type DesktopWindow={title:string;processId:number;controlType:string};
export type DesktopControl={name:string;automationId:string;controlType:string;matchCount:number;enabled:boolean;actions:string[]};
export async function listDesktopWindows(allowDesktop:boolean):Promise<DesktopWindow[]>{return (await rpc('desktop.inspect.windows',{allowDesktop})).windows??[];}
export async function listDesktopControls(windowTitle:string,processId:number,allowDesktop:boolean):Promise<DesktopControl[]>{return (await rpc('desktop.inspect.controls',{windowTitle,processId,allowDesktop})).controls??[];}
export async function getRunHistory(limit=50):Promise<any[]>{const value=await rpc('run.history',{limit});return value.runs??[];}
export async function getAdapterStatus():Promise<any>{return rpc('adapter.status');}
export async function getAuditHistory(limit=200):Promise<any[]>{const value=await rpc('audit.history',{limit});return value.events??[];}
export type AiConfig={provider:string;baseUrl?:string;credentialService?:string;credentialUsername?:string};
export type AiConnectionProfile={id:string;name:string;provider:string;baseUrl:string;model:string;credentialService:string;credentialUsername:string};
export async function listAiProviders():Promise<{id:string;name:string;local:boolean;defaultBaseUrl:string;requiresCredential:boolean}[]>{return (await rpc('ai.providers')).providers??[];}
export async function storeAiCredential(service:string,username:string,secret:string):Promise<void>{if(!inDesktop())throw new Error('Credential storage is available only in the installed desktop app.');await rpc('credential.store',{service,username,secret});}
export async function listAiConnections():Promise<AiConnectionProfile[]>{if(!inDesktop())return [];return (await rpc('ai.connections.list')).profiles??[];}
export async function saveAiConnection(profile:Partial<AiConnectionProfile>):Promise<AiConnectionProfile>{return (await rpc('ai.connections.save',{profile})).profile;}
export async function deleteAiConnection(profileId:string):Promise<void>{await rpc('ai.connections.delete',{profileId});}
export async function listAiModels(config:AiConfig):Promise<string[]>{const result=await rpc('ai.models',{...config});return result.models??[];}
export async function draftWithAi(config:AiConfig,model:string,prompt:string,workflows:string[],executionModel:'sequence'|'flowchart'|'state_machine'='sequence'):Promise<{explanation:string;workflow:Workflow;valid:boolean;problems:{code:string;message:string;activityId?:string}[]}>{return rpc('ai.draft',{...config,model,prompt,workflows,executionModel});}
/** @deprecated Ollama alias retained for callers using the previous bridge API. */
export async function listLocalModels():Promise<string[]>{return listAiModels({provider:'ollama'});}
/** @deprecated Ollama alias retained for callers using the previous bridge API. */
export async function draftWithLocalModel(model:string,prompt:string,workflows:string[]){return draftWithAi({provider:'ollama'},model,prompt,workflows);}
export async function getCatalog():Promise<CatalogEntry[]>{return rpc('activity.catalog');}
export async function listenRunEvents(handler:(event:Record<string,unknown>)=>void):Promise<()=>void>{
  if ('__TAURI_INTERNALS__' in window) return listen('run-event',e=>handler(e.payload as Record<string,unknown>));
  const fn=(e:Event)=>handler((e as CustomEvent).detail);window.addEventListener('openrpa-run-event',fn);return()=>window.removeEventListener('openrpa-run-event',fn);
}
