import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

const HEADER_NAME=/^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$/;
const FORBIDDEN_HEADERS=new Set(['authorization','cookie','set-cookie','host','connection','content-length','transfer-encoding','proxy-authorization']);
const formatValue=(value:unknown)=>value==null?'':typeof value==='string'?value:String(value);

export function KeyValueEditor({kind,values,onChange}:{kind:'query'|'headers';values:Record<string,unknown>;onChange:(values:Record<string,string>)=>void}){
  const entries=Object.entries(values&&typeof values==='object'&&!Array.isArray(values)?values:{});
  const [rows,setRows]=useState<Array<[string,string]>>(()=>entries.map(([key,value])=>[key,formatValue(value)]));
  const [error,setError]=useState('');
  useEffect(()=>{setRows(entries.map(([key,value])=>[key,formatValue(value)]));setError('')},[values]);
  const isHeaders=kind==='headers';
  const singular=isHeaders?'header':'parameter';
  const valueLabel=isHeaders?'Header value':'Parameter value';
  const addLabel=isHeaders?'Add header':'Add query parameter';
  const reservedHeader=(key:string)=>{
    const lower=key.toLowerCase();
    return FORBIDDEN_HEADERS.has(lower)||['token','secret','api-key','api_key','apikey','password','credential'].some(term=>lower.includes(term));
  };
  function commit(next:Array<[string,string]>){
    setRows(next);
    const names=next.map(([key])=>key.trim());
    if(names.some(name=>!name)){setError('Parameter and header names cannot be empty.');return;}
    const unique=new Set<string>();
    for(const name of names){
      const normalized=isHeaders?name.toLowerCase():name;
      if(unique.has(normalized)){setError(`Names must be unique; “${name}” appears more than once.`);return;}
      unique.add(normalized);
      if(isHeaders&&!HEADER_NAME.test(name)){setError('Header names must use valid HTTP token characters.');return;}
      if(isHeaders&&reservedHeader(name)){setError('Authentication, transport, and credential headers must come from the saved connection.');return;}
    }
    setError('');
    onChange(Object.fromEntries(next));
  }
  function add(){
    const base=isHeaders?'X-Request-Header':'parameter';let name=base;let suffix=2;
    const normalized=new Set(rows.map(([key])=>isHeaders?key.toLowerCase():key));
    while(normalized.has(isHeaders?name.toLowerCase():name))name=`${base}-${suffix++}`;
    const next=[...rows,[name,''] as [string,string]];setRows(next);setError('');onChange(Object.fromEntries(next));
  }
  function changeKey(index:number,key:string){const next:Array<[string,string]>=rows.map(([name,value],row)=>[row===index?key:name,value]);commit(next)}
  function changeValue(index:number,value:string){const next:Array<[string,string]>=rows.map(([name,current],row)=>[name,row===index?value:current]);commit(next)}
  function remove(index:number){const next=rows.filter((_,row)=>row!==index);setRows(next);setError('');onChange(Object.fromEntries(next))}
  return <section className="key-value-editor" aria-label={isHeaders?'Request headers':'Query parameters'}>
    <div className="key-value-heading"><div><strong>{isHeaders?'REQUEST HEADERS':'QUERY PARAMETERS'}</strong><small>{rows.length} / {isHeaders?50:100}</small></div><button className="toolbar-btn" type="button" onClick={add} disabled={rows.length>=(isHeaders?50:100)||!!error}><Plus size={12}/>{addLabel}</button></div>
    {!rows.length&&<p className="key-value-empty">No {isHeaders?'custom headers':'query parameters'} configured.</p>}
    {rows.map(([key,value],index)=><div className="key-value-row" key={index}>
      <label><span>{isHeaders?'Header name':'Parameter name'}</span><input aria-label={`${isHeaders?'Header':'Query parameter'} ${index+1} name`} value={key} maxLength={isHeaders?128:256} placeholder={isHeaders?'X-Request-Id':'page'} onChange={event=>changeKey(index,event.target.value)}/></label>
      <label><span>{valueLabel}</span><input aria-label={`${isHeaders?'Header':'Query parameter'} ${index+1} value`} value={formatValue(value)} maxLength={8192} placeholder={isHeaders?'application/json':'{{ page }}'} onChange={event=>changeValue(index,event.target.value)}/></label>
      <button className="tiny-icon" type="button" aria-label={`Remove ${singular} ${key}`} title={`Remove ${singular}`} onClick={()=>remove(index)}><Trash2 size={13}/></button>
    </div>)}
    {error&&<small className="key-value-error" role="alert">{error}</small>}
    {isHeaders&&<small className="field-hint">Authentication and credential headers are managed by the saved connection and OS vault. Do not put secrets here.</small>}
  </section>;
}
