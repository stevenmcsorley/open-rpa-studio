import { useEffect, useState } from 'react';
import { AlertCircle, KeyRound, Trash2, X } from 'lucide-react';
import { deleteManagedCredential, listManagedCredentials, storeAiCredential, type ManagedCredential } from './bridge';

export function CredentialManagerDialog({ onClose, onChanged }: { onClose: () => void; onChanged?: () => void }) {
  const [items, setItems] = useState<ManagedCredential[]>([]);
  const [label, setLabel] = useState('');
  const [service, setService] = useState('');
  const [username, setUsername] = useState('');
  const [secret, setSecret] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function refresh() { setItems(await listManagedCredentials()); }
  useEffect(() => { void refresh().catch(reason => setError(String(reason))); }, []);
  async function save() {
    setBusy(true); setError('');
    try { await storeAiCredential(service, username, secret, label); setSecret(''); setLabel(''); await refresh(); onChanged?.(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  async function remove(item: ManagedCredential) {
    if (!window.confirm(`Delete “${item.label}” from the operating-system credential store? Workflows using this reference will fail until a credential is stored again.`)) return;
    setBusy(true); setError('');
    try { await deleteManagedCredential(item.service, item.username); await refresh(); onChanged?.(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }
  return <div className="modal-backdrop"><section className="credential-manager" role="dialog" aria-modal="true" aria-labelledby="credential-manager-title">
    <header><div><KeyRound size={17}/><strong id="credential-manager-title">Credentials</strong></div><button className="tiny-icon" aria-label="Close credentials" onClick={onClose}><X size={16}/></button></header>
    <p className="ai-disclosure">Create named credential references for browser or desktop logins and workflow credential activities. Secret values are written directly to the operating-system secure credential store. Workflows and MCP tools use the service and username reference; they never need the secret value.</p>
    <div className="credential-manager-form"><label>Display name<input value={label} onChange={event=>setLabel(event.target.value)} maxLength={200} placeholder="Marketing site login"/></label><label>Service reference<input value={service} onChange={event=>setService(event.target.value)} maxLength={200} placeholder="company-site"/></label><label>Username reference<input value={username} onChange={event=>setUsername(event.target.value)} maxLength={200} placeholder="publisher"/></label><label>Secret<input type="password" autoComplete="new-password" spellCheck={false} value={secret} onChange={event=>setSecret(event.target.value)} maxLength={8192} placeholder="Password, API token, or client secret"/></label><button className="toolbar-btn primary" disabled={busy||!label.trim()||!service.trim()||!username.trim()||!secret} onClick={()=>void save()}>{busy?'Saving…':'Store credential'}</button></div>
    {error&&<div className="ai-error"><AlertCircle size={14}/>{error}</div>}
    <div className="credential-manager-list"><div className="credential-list-heading"><strong>Managed references</strong><span>{items.length}</span></div>{items.length?items.map(item=><article key={`${item.service}\0${item.username}`}><div><strong>{item.label}</strong><code>{item.service} · {item.username}</code><small>{item.stored?'Available in OS credential store':'Missing from OS credential store'}</small></div><button className="tiny-icon" aria-label={`Delete ${item.label}`} title="Delete credential" disabled={busy||!item.stored} onClick={()=>void remove(item)}><Trash2 size={14}/></button></article>):<p className="empty-output">No app-managed credentials yet.</p>}</div>
    <footer><button className="toolbar-btn" onClick={onClose}>Done</button></footer>
  </section></div>;
}
