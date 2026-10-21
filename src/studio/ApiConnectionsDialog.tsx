import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Plug, X } from 'lucide-react';
import { authorizeApiConnection, cancelApiConnectionAuthorization, deleteApiConnection, saveApiConnection, testApiConnection } from './bridge';
import type { ApiConnectionProfile } from './bridge';
import { KeyValueEditor } from './KeyValueEditor';
import type { OpenApiConnectionSeed } from './openapi';

const empty = (): ApiConnectionProfile => ({
  id: '', name: '', baseUrl: 'https://api.example.com/v1', authType: 'none',
  apiKeyHeader: 'X-API-Key', headers: {}, minIntervalSeconds: 0,
  authorizationUrl: 'https://auth.example.com/oauth/authorize',
  tokenUrl: 'https://auth.example.com/oauth/token', clientId: '', scope: '', audience: '',
  clientAuthMethod: 'client_secret_basic', credentialStored: false, clientSecretStored: false,
});

export function ApiConnectionsDialog({ profiles, onProfiles, onClose, allowNetwork, initialProfile, initialNote, onSaved }: {
  profiles: ApiConnectionProfile[]; onProfiles: (profiles: ApiConnectionProfile[]) => void;
  onClose: () => void; allowNetwork: boolean; initialProfile?:OpenApiConnectionSeed; initialNote?:string; onSaved?:(profile:ApiConnectionProfile)=>void;
}) {
  const [draft, setDraft] = useState<ApiConnectionProfile>(()=>initialProfile?{...empty(),...initialProfile}:empty());
  const [secret, setSecret] = useState('');
  const [testPath, setTestPath] = useState('/');
  const [busy, setBusy] = useState(false);
  const [authorizing, setAuthorizing] = useState(false);
  const [error, setError] = useState('');
  const [testMessage, setTestMessage] = useState('');
  const sorted = useMemo(() => [...profiles].sort((a, b) => a.name.localeCompare(b.name)), [profiles]);

  useEffect(()=>{if(!initialProfile)return;setDraft({...empty(),...initialProfile});setSecret('');setError('');setTestMessage('')},[initialProfile]);

  function select(id: string) {
    const profile = profiles.find(item => item.id === id);
    const next = profile ? { ...profile } : empty();
    setDraft(next); setSecret(''); setError(''); setTestMessage('');
  }
  function changeAuthType(authType: ApiConnectionProfile['authType']) {
    setDraft(current => ({ ...current, authType,
      clientAuthMethod: authType === 'oauth_authorization_code' ? 'none' : 'client_secret_basic' }));
    setSecret(''); setTestMessage(''); setError('');
  }
  async function save() {
    setBusy(true); setError(''); setTestMessage('');
    try {
      const saved = await saveApiConnection(draft, secret || undefined);
      setDraft(saved); setSecret('');
      onProfiles([...profiles.filter(profile => profile.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name)));
      onSaved?.(saved);
      setTestMessage(saved.authType === 'oauth_authorization_code'
        ? (saved.credentialStored ? 'Connection saved; OAuth authorization is stored in the OS vault.' : 'Connection saved. Choose Authorize to sign in.')
        : saved.credentialStored ? 'Connection saved; its credential is in the OS vault.' : 'Connection saved locally.');
    } catch (value) { setError(value instanceof Error ? value.message : String(value)); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!draft.id || !window.confirm(`Remove API connection “${draft.name}”? Its associated vault credentials and OAuth tokens will also be removed.`)) return;
    setBusy(true); setError('');
    try {
      await deleteApiConnection(draft.id);
      const next = profiles.filter(profile => profile.id !== draft.id); onProfiles(next); select(''); setTestMessage('Connection removed.');
    } catch (value) { setError(value instanceof Error ? value.message : String(value)); }
    finally { setBusy(false); }
  }
  async function authorize() {
    if (!draft.id) { setError('Save the connection before authorizing it.'); return; }
    if (!allowNetwork) { setError('Enable Allow network in the Studio toolbar before authorizing a connection.'); return; }
    setBusy(true); setError(''); setTestMessage('Complete sign-in in the system browser…');
    setAuthorizing(true);
    try {
      const result = await authorizeApiConnection(draft.id, allowNetwork);
      const updated = { ...draft, credentialStored: result.credentialStored };
      setDraft(updated); onProfiles(profiles.map(profile => profile.id === updated.id ? updated : profile));
      setTestMessage('Authorized. OAuth tokens are stored in the OS credential vault.');
    } catch (value) { setTestMessage(''); setError(value instanceof Error ? value.message : String(value)); }
    finally { setBusy(false); setAuthorizing(false); }
  }
  async function cancelAuthorization() {
    if (!draft.id) return;
    try { await cancelApiConnectionAuthorization(draft.id); }
    catch (value) { setError(value instanceof Error ? value.message : String(value)); }
  }
  async function test() {
    if (!draft.id) { setError('Save the connection before testing it.'); return; }
    if (!allowNetwork) { setError('Enable Allow network in the Studio toolbar before testing a connection.'); return; }
    if (draft.authType === 'oauth_authorization_code' && !draft.credentialStored) { setError('Authorize this OAuth connection before testing it.'); return; }
    setBusy(true); setError(''); setTestMessage('');
    try {
      const result = await testApiConnection(draft.id, testPath, allowNetwork);
      setTestMessage(result.ok ? `Connected · HTTP ${result.status}${result.contentType ? ` · ${result.contentType}` : ''}` : `Endpoint responded · HTTP ${result.status}`);
    } catch (value) { setError(value instanceof Error ? value.message : String(value)); }
    finally { setBusy(false); }
  }

  const oauthCode = draft.authType === 'oauth_authorization_code';
  const secretNeeded = draft.authType === 'bearer' || draft.authType === 'api_key_header'
    || (draft.authType === 'oauth_client_credentials' && draft.clientAuthMethod !== 'none')
    || (oauthCode && draft.clientAuthMethod !== 'none');
  return <div className="modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="ai-modal api-connections-modal" role="dialog" aria-modal="true" aria-label="API connections">
      <header><div><Plug size={16}/><strong>API CONNECTIONS</strong></div><button className="tiny-icon" aria-label="Close API connections" onClick={onClose}><X size={15}/></button></header>
      <p className="ai-disclosure">Reusable HTTPS endpoints for workflow API requests. Secrets and OAuth grants stay in the operating-system credential vault. OAuth Authorization Code uses PKCE and opens your system browser only when you choose Authorize.</p>
      {initialNote&&<small className="field-hint openapi-connection-note">{initialNote}</small>}
      <div className="api-connection-layout">
        <aside className="api-connection-list">
          <button className={`toolbar-btn${!draft.id ? ' primary' : ''}`} onClick={() => select('')}>+ New connection</button>
          {sorted.map(profile => <button key={profile.id} className={`api-connection-card${draft.id === profile.id ? ' selected' : ''}`} onClick={() => select(profile.id)}>
            <strong>{profile.name}</strong><small>{profile.baseUrl}</small>
            <span>{profile.authType === 'none' ? 'No authentication' : profile.authType === 'oauth_authorization_code' ? profile.credentialStored ? 'OAuth authorized' : 'Sign in required' : profile.credentialStored ? 'Credential stored' : 'Credential needed'}</span>
          </button>)}
          {!sorted.length && <small className="field-hint">No API connections yet.</small>}
        </aside>
        <div className="api-connection-form">
          <label>Connection name<input aria-label="API connection name" maxLength={100} value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} placeholder="Orders API"/></label>
          <label>Base URL<input aria-label="API connection base URL" maxLength={2048} value={draft.baseUrl} onChange={event => setDraft({ ...draft, baseUrl: event.target.value })} placeholder="https://api.example.com/v1"/><small className="field-hint">HTTPS public endpoint; request paths stay on this host.</small></label>
          <label>Authentication<select aria-label="API authentication type" value={draft.authType} onChange={event => changeAuthType(event.target.value as ApiConnectionProfile['authType'])}>
            <option value="none">None</option><option value="bearer">Bearer token</option><option value="api_key_header">API key header</option>
            <option value="oauth_client_credentials">OAuth 2.0 · Client credentials</option><option value="oauth_authorization_code">OAuth 2.0 · Authorization Code with PKCE</option>
          </select></label>
          {draft.authType === 'api_key_header' && <label>API key header name<input aria-label="API key header name" maxLength={128} value={draft.apiKeyHeader} onChange={event => setDraft({ ...draft, apiKeyHeader: event.target.value })}/></label>}
          {(draft.authType === 'oauth_client_credentials' || oauthCode) && <>
            {oauthCode && <label>OAuth authorization URL<input aria-label="OAuth authorization URL" maxLength={2048} value={draft.authorizationUrl} onChange={event => setDraft({ ...draft, authorizationUrl: event.target.value })}/></label>}
            <label>OAuth token URL<input aria-label="OAuth token URL" maxLength={2048} value={draft.tokenUrl} onChange={event => setDraft({ ...draft, tokenUrl: event.target.value })}/></label>
            <label>Client ID<input aria-label="OAuth client ID" maxLength={1024} value={draft.clientId} onChange={event => setDraft({ ...draft, clientId: event.target.value })}/></label>
            <label>Client authentication<select aria-label="OAuth client authentication method" value={draft.clientAuthMethod} onChange={event => setDraft({ ...draft, clientAuthMethod: event.target.value as ApiConnectionProfile['clientAuthMethod'] })}>
              {oauthCode && <option value="none">Public client · PKCE</option>}<option value="client_secret_basic">HTTP Basic</option><option value="client_secret_post">Credentials in form body</option>
            </select></label>
            <label>Scope<input aria-label="OAuth scope" maxLength={2048} value={draft.scope} onChange={event => setDraft({ ...draft, scope: event.target.value })}/></label>
            <label>Audience<input aria-label="OAuth audience" maxLength={2048} value={draft.audience} onChange={event => setDraft({ ...draft, audience: event.target.value })}/></label>
          </>}
          {secretNeeded && <label>{draft.authType === 'oauth_client_credentials' ? 'Client secret' : oauthCode ? 'OAuth client secret' : 'Credential secret'}
            <input aria-label={oauthCode ? 'OAuth client secret' : 'API credential secret'} type="password" autoComplete="new-password" spellCheck={false} value={secret} onChange={event => setSecret(event.target.value)} placeholder={draft.clientSecretStored || draft.credentialStored ? 'Leave blank to keep the stored credential' : 'Enter secret; it is stored in the OS vault'}/>
            {oauthCode && <small className="field-hint">Leave blank for a public OAuth client. Confidential clients need a secret.</small>}
          </label>}
          <KeyValueEditor kind="headers" values={draft.headers} onChange={headers => setDraft(current => ({ ...current, headers }))}/>
          <label>Minimum interval between calls · seconds<input aria-label="API minimum request interval" type="number" min={0} max={60} step={0.1} value={draft.minIntervalSeconds} onChange={event => setDraft({ ...draft, minIntervalSeconds: Number(event.target.value) })}/></label>
          {oauthCode && <div className="api-connection-test"><small>{draft.credentialStored ? 'OAuth grant is in the OS vault.' : 'Sign in once to grant this connection API access.'}</small>
            <button className="toolbar-btn" disabled={busy || !allowNetwork || !draft.id || (draft.clientAuthMethod !== 'none' && !draft.clientSecretStored)} onClick={() => void authorize()}>{authorizing ? 'Waiting for browser…' : 'Authorize in browser'}</button>
            {authorizing && <button className="toolbar-btn" onClick={() => void cancelAuthorization()}>Cancel authorization</button>}
          </div>}
          <div className="api-connection-test"><label>Test GET path<input aria-label="API test path" value={testPath} onChange={event => setTestPath(event.target.value)} placeholder="/health or /v1/me"/></label>
            <button className="toolbar-btn" disabled={busy || !allowNetwork || !draft.id} onClick={() => void test()}>{busy ? 'Working…' : 'Test connection'}</button>
          </div>
          {!allowNetwork && <small className="field-hint">Enable Allow network in the Studio toolbar to authorize or test this API connection.</small>}
          {error && <div className="ai-error"><AlertCircle size={14}/>{error}</div>}{testMessage && <div className="api-connection-result">{testMessage}</div>}
          <footer><button className="toolbar-btn" onClick={onClose}>Close</button>{draft.id && <button className="toolbar-btn" disabled={busy} onClick={() => void remove()}>Delete</button>}
            <button className="toolbar-btn primary" disabled={busy || !draft.name.trim()} onClick={() => void save()}>{busy ? 'Saving…' : draft.id ? 'Save changes' : 'Save connection'}</button>
          </footer>
        </div>
      </div>
    </section>
  </div>;
}
