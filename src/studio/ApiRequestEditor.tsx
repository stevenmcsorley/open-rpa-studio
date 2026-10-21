import { useEffect, useState } from 'react';
import type { ApiConnectionProfile } from './bridge';
import type { Activity } from './types';

export function ApiRequestEditor({activity,connections,onChange}:{activity:Activity;connections:ApiConnectionProfile[];onChange:(patch:Partial<Activity>)=>void}){
  const value=activity as Record<string,any>;
  const [queryText,setQueryText]=useState(JSON.stringify(value.query??{},null,2));
  const [headersText,setHeadersText]=useState(JSON.stringify(value.headers??{},null,2));
  useEffect(()=>setQueryText(JSON.stringify(value.query??{},null,2)),[value.query]);
  useEffect(()=>setHeadersText(JSON.stringify(value.headers??{},null,2)),[value.headers]);
  const updateJson=(field:string,text:string,setText:(value:string)=>void)=>{setText(text);try{const parsed=JSON.parse(text);if(parsed&&typeof parsed==='object'&&!Array.isArray(parsed))onChange({[field]:parsed})}catch{/* Keep the user's in-progress JSON text in the input until it parses. */}};
  return <div className="api-request-editor">
    <div className="field"><label>Saved API connection</label><select aria-label="Saved API connection" value={String(value.connectionId??'')} onChange={event=>onChange({connectionId:event.target.value})}><option value="">Choose a connection…</option>{connections.map(profile=><option key={profile.id} value={profile.id}>{profile.name} · {profile.baseUrl}</option>)}</select>{!connections.length&&<small className="field-hint">Create a reusable connection with the API Connections button.</small>}</div>
    <div className="field api-request-method-path"><label>Method<select aria-label="API request method" value={String(value.method??'GET')} onChange={event=>onChange({method:event.target.value})}><option>GET</option><option>POST</option><option>PUT</option><option>PATCH</option></select></label><label>Relative path<input aria-label="API request path" value={String(value.path??'/')} maxLength={8192} placeholder="/v1/orders" onChange={event=>onChange({path:event.target.value})}/></label></div>
    <div className="field"><label>Query parameters · JSON object</label><textarea rows={3} aria-label="API query parameters JSON" value={queryText} spellCheck={false} onChange={event=>updateJson('query',event.target.value,setQueryText)}/></div>
    <div className="field"><label>Request headers · JSON object</label><textarea rows={3} aria-label="API request headers JSON" value={headersText} spellCheck={false} onChange={event=>updateJson('headers',event.target.value,setHeadersText)}/><small className="field-hint">Authentication headers come from the saved connection and its OS-vault credential.</small></div>
    {String(value.method??'GET')!=='GET'&&<div className="field"><label>Request body · text or JSON</label><textarea rows={4} aria-label="API request body" value={String(value.body??'')} spellCheck={false} onChange={event=>onChange({body:event.target.value})}/></div>}
    <div className="field api-request-limits"><label>Timeout seconds<input type="number" min={1} max={60} value={Number(value.timeoutSeconds??20)} onChange={event=>onChange({timeoutSeconds:Number(event.target.value)})}/></label><label>Max response bytes<input type="number" min={1} max={20000000} value={Number(value.maxResponseBytes??5000000)} onChange={event=>onChange({maxResponseBytes:Number(event.target.value)})}/></label></div>
    <div className="field"><label>Response variable<input aria-label="API response variable" value={String(value.result??'response')} onChange={event=>onChange({result:event.target.value})}/></label></div>
  </div>
}
