import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import type { BridgeResult, CatalogEntry, LiveWorkflowDraft, Project, RunResult, Workflow } from './types';

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
export async function projectSignature(root:string):Promise<string>{const result=await rpc('project.signature',{root});return result.sha256;}
export async function readLiveWorkflowDraft(root:string):Promise<LiveWorkflowDraft|null>{const result=await rpc('project.live_draft.read',{root});return result.draft??null;}
export async function clearLiveWorkflowDraft(root:string,draftId:string):Promise<void>{await rpc('project.live_draft.clear',{root,draftId});}
export async function createProject(path:string,name:string):Promise<BridgeResult>{return rpc('project.create',{path,name});}
export async function saveProject(root:string,project:Project,workflows:Record<string,Workflow>):Promise<void>{await rpc('project.save',{root,project,workflows});}
export async function exportProjectPackage(root:string,destination:string):Promise<{path:string;files:number;sha256:string}>{return rpc('project.package.export',{root,destination});}
export async function importProjectPackage(packagePath:string,destination:string):Promise<{path:string;files:number;name:string;sha256:string}>{return rpc('project.package.import',{package:packagePath,destination});}
export async function validateWorkflow(project:Project,workflow:Workflow,workflows:Record<string,Workflow>,workflowName=workflow.name):Promise<{valid:boolean;problems:{message:string;code:string;activityId?:string}[]}>{return rpc('workflow.validate',{project,workflow,workflows,workflowName});}
export async function runWorkflow(project:Project,root:string,workflow:string,allowNetwork:boolean,allowDesktop=false,debug=false,inputs:Record<string,unknown>={},allowDestructive=false):Promise<RunResult>{return rpc('workflow.run',{project,root,workflow,allowNetwork,allowDesktop,debug,inputs,allowDestructive});}
export async function cancelWorkflow():Promise<void>{await rpc('workflow.cancel');}
export async function debugControl(action:'pause'|'resume'|'step_over'|'step_into'|'step_out'):Promise<void>{await rpc(`debug.${action}`);}
export type DebugWatchResult={status:'ok';type:string;value:unknown}|{status:'error';error:string};
export async function evaluateDebugWatch(expression:string):Promise<DebugWatchResult>{return rpc('debug.evaluate_watch',{expression});}
export async function setDebugVariable(name:string,value:unknown):Promise<void>{await rpc('debug.set_variable',{name,value});}
export type BrowserControl={selectorKind:'role'|'test_id'|'placeholder';selector:string;role:string;name:string;tag:string;inputType:string;placeholder:string;matchCount:number;actions:string[]};
export async function openBrowserInspector(url:string,allowNetwork:boolean,browserType='chromium',channel='chromium',executablePath=''):Promise<{url:string;title:string;status:number|null}>{return rpc('browser.inspect.open',{url,allowNetwork,browserType,channel,executablePath});}
export async function probeBrowserRuntime(browserType='chromium',channel='chromium',executablePath=''):Promise<{browserType:string;channel:string;version:string;headless:string;networkUsed:string}>{return rpc('browser.inspect.probe',{browserType,channel,executablePath});}
export async function readBrowserInspectorControls():Promise<{url:string;title:string;controls:BrowserControl[];truncated:boolean}>{return rpc('browser.inspect.controls');}
export async function startBrowserRecording(allowNetwork:boolean):Promise<{recording:boolean;url:string}>{return rpc('browser.inspect.record.start',{allowNetwork});}
export async function stopBrowserRecording():Promise<{recording:boolean;url:string;events:Record<string,unknown>[];truncated:boolean}>{return rpc('browser.inspect.record.stop');}
export async function closeBrowserInspector():Promise<void>{await rpc('browser.inspect.close');}
export type DesktopWindow={title:string;processId:number;controlType:string};
export type DesktopControl={name:string;automationId:string;controlType:string;matchCount:number;enabled:boolean;visible?:boolean;actions:string[]};
export async function listDesktopWindows(allowDesktop:boolean):Promise<DesktopWindow[]>{return (await rpc('desktop.inspect.windows',{allowDesktop})).windows??[];}
export async function listDesktopControls(windowTitle:string,processId:number,allowDesktop:boolean):Promise<DesktopControl[]>{return (await rpc('desktop.inspect.controls',{windowTitle,processId,allowDesktop})).controls??[];}
export type DesktopRecordedEvent=
  | {type:'desktop_ui_click';windowTitle:string;processId:number;name:string;automationId:string;controlType:string;timeoutSeconds:number}
  | {type:'desktop_ui_invoke'|'desktop_ui_check'|'desktop_ui_uncheck';windowTitle:string;processId:number;name:string;automationId:string;controlType:string;timeoutSeconds:number}
  | {type:'desktop_ui_press';windowTitle:string;processId:number;name:string;automationId:string;controlType:string;timeoutSeconds:number;key:string}
  | {type:'desktop_ui_set_range_value';windowTitle:string;processId:number;name:string;automationId:string;controlType:'Slider'|'Spinner';timeoutSeconds:number;value:number}
  | {type:'desktop_ui_drag';windowTitle:string;processId:number;sourceName:string;sourceAutomationId:string;sourceControlType:string;targetName:string;targetAutomationId:string;targetControlType:string;durationMilliseconds:number;timeoutSeconds:number};
export async function startDesktopRecording(windowTitle:string,processId:number,allowDesktop:boolean,recordKeyboard=true):Promise<{recording:boolean;windowTitle:string;processId:number;recordKeyboard:boolean}>{return rpc('desktop.inspect.record.start',{windowTitle,processId,allowDesktop,recordKeyboard});}
export async function stopDesktopRecording():Promise<{recording:boolean;windowTitle:string;processId:number;events:DesktopRecordedEvent[];truncated:boolean;ignoredClicks:number;ignoredKeys:number}>{return rpc('desktop.inspect.record.stop');}
export type RunHistorySummary={runId:string;projectPath:string;projectName:string;workflow:string;workflowSha256:string;status:string;startedAt:string;endedAt:string|null;error:Record<string,unknown>|null;recoveryNote:string|null;source?:'Studio'|'MCP'};
export type RunHistoryDetail=RunHistorySummary&{result:{status?:string;activities?:Record<string,{status:string;type:string;durationMs?:number;error?:string}>;error?:Record<string,unknown>}|null;events:Record<string,unknown>[]};
export type QueuedJob={jobId:string;workflow:string;status:string;availableAt:string;submittedAt:string;startedAt:string|null;endedAt:string|null;runId:string|null;error:Record<string,unknown>|null;cancelRequested:boolean};
export async function getJobQueue(limit=100):Promise<QueuedJob[]>{return (await rpc('jobs.history',{limit})).jobs??[];}
export async function cancelQueuedJob(jobId:string):Promise<QueuedJob>{return (await rpc('jobs.cancel',{jobId})).job;}
export async function getRunHistory(limit=50):Promise<RunHistorySummary[]>{const value=await rpc('run.history',{limit});return value.runs??[];}
export async function getRunDetails(runId:string):Promise<RunHistoryDetail|null>{const value=await rpc('run.get',{runId});return value.run??null;}
export async function exportRunEvidence(runId:string,destination:string):Promise<{sha256:string;bytes:number}>{return rpc('run.export',{runId,destination});}
export async function getAdapterStatus():Promise<any>{return rpc('adapter.status');}
export async function getAuditHistory(limit=200):Promise<any[]>{const value=await rpc('audit.history',{limit});return value.events??[];}
export type AiConfig={provider:string;baseUrl?:string;credentialService?:string;credentialUsername?:string;credentialMode?:'bearer'|'api_key_header';credentialHeader?:string};
export type AiConnectionProfile={id:string;name:string;provider:string;baseUrl:string;model:string;credentialService:string;credentialUsername:string;credentialMode?:'bearer'|'api_key_header';credentialHeader?:string};
export async function listAiProviders():Promise<{id:string;name:string;local:boolean;defaultBaseUrl:string;requiresCredential:boolean}[]>{return (await rpc('ai.providers')).providers??[];}
export async function storeAiCredential(service:string,username:string,secret:string):Promise<void>{if(!inDesktop())throw new Error('Credential storage is available only in the installed desktop app.');await rpc('credential.store',{service,username,secret});}
export async function listAiConnections():Promise<AiConnectionProfile[]>{if(!inDesktop())return [];return (await rpc('ai.connections.list')).profiles??[];}
export async function saveAiConnection(profile:Partial<AiConnectionProfile>):Promise<AiConnectionProfile>{return (await rpc('ai.connections.save',{profile})).profile;}
export async function deleteAiConnection(profileId:string):Promise<void>{await rpc('ai.connections.delete',{profileId});}
export type ApiConnectionProfile={id:string;name:string;baseUrl:string;authType:'none'|'bearer'|'api_key_header'|'oauth_client_credentials'|'oauth_authorization_code';apiKeyHeader:string;headers:Record<string,string>;minIntervalSeconds:number;authorizationUrl:string;tokenUrl:string;clientId:string;scope:string;audience:string;clientAuthMethod:'none'|'client_secret_basic'|'client_secret_post';credentialStored?:boolean;clientSecretStored?:boolean};
export async function listApiConnections():Promise<ApiConnectionProfile[]>{if(!inDesktop())return [];return (await rpc('api.connections.list')).profiles??[];}
export async function saveApiConnection(profile:Partial<ApiConnectionProfile>,secret?:string):Promise<ApiConnectionProfile>{const {credentialStored,clientSecretStored,...configuration}=profile;void credentialStored;void clientSecretStored;const result=await rpc('api.connections.save',{profile:configuration,...(secret?{secret}:{})});return {...result.profile,credentialStored:result.credentialStored,clientSecretStored:result.clientSecretStored};}
export async function deleteApiConnection(profileId:string):Promise<void>{await rpc('api.connections.delete',{profileId});}
export async function testApiConnection(profileId:string,path:string,allowNetwork:boolean):Promise<{status:number;ok:boolean;contentType:string}>{return rpc('api.connections.test',{profileId,path,allowNetwork});}
export type ApiDiscoveredField={name:string;path:string;type:string};
export type ApiDiscoveredArray={itemsPointer:string;stablePointer:boolean;observedRows:number;sampledRows:number;fields:ApiDiscoveredField[];fieldsTruncated:boolean};
export async function discoverApiResponse(profileId:string,path:string,query:Record<string,string|number|boolean>,allowNetwork:boolean):Promise<{status:number;ok:boolean;contentType:string;candidates:ApiDiscoveredArray[];discoveryError?:string}>{return rpc('api.connections.discover',{profileId,path,query,allowNetwork});}
export async function authorizeApiConnection(profileId:string,allowNetwork:boolean):Promise<{authorized:boolean;credentialStored:boolean}>{return rpc('api.connections.authorize',{profileId,allowNetwork});}
export async function cancelApiConnectionAuthorization(profileId:string):Promise<{cancelled:boolean}>{return rpc('api.connections.authorize.cancel',{profileId});}
export async function fetchOpenApiSpec(url:string,allowNetwork:boolean):Promise<string>{if(!inDesktop())throw new Error('Fetching OpenAPI documents from a URL requires the installed desktop app.');const result=await rpc('openapi.fetch',{url,allowNetwork});return result.text;}
export async function listAiModels(config:AiConfig):Promise<string[]>{const result=await rpc('ai.models',{...config});return result.models??[];}
export type AiTokenUsage={inputTokens?:number;outputTokens?:number;totalTokens?:number};
export async function draftWithAi(config:AiConfig,model:string,prompt:string,workflows:string[],executionModel:'sequence'|'flowchart'|'state_machine'='sequence',draftId=crypto.randomUUID()):Promise<{explanation:string;workflow:Workflow;valid:boolean;problems:{code:string;message:string;activityId?:string}[];warnings?:string[];usage?:AiTokenUsage|null}>{return rpc('ai.draft',{...config,model,prompt,workflows,executionModel,draftId});}
export async function cancelAiDraft(draftId:string):Promise<boolean>{const result=await rpc('ai.cancel',{draftId});return result.cancelled===true;}
/** @deprecated Ollama alias retained for callers using the previous bridge API. */
export async function listLocalModels():Promise<string[]>{return listAiModels({provider:'ollama'});}
/** @deprecated Ollama alias retained for callers using the previous bridge API. */
export async function draftWithLocalModel(model:string,prompt:string,workflows:string[]){return draftWithAi({provider:'ollama'},model,prompt,workflows);}
export async function getCatalog():Promise<CatalogEntry[]>{return rpc('activity.catalog');}
export async function listenRunEvents(handler:(event:Record<string,unknown>)=>void):Promise<()=>void>{
  if ('__TAURI_INTERNALS__' in window) return listen('run-event',e=>handler(e.payload as Record<string,unknown>));
  const fn=(e:Event)=>handler((e as CustomEvent).detail);window.addEventListener('openrpa-run-event',fn);return()=>window.removeEventListener('openrpa-run-event',fn);
}
