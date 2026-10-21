import { CheckCircle2, CircleAlert, LoaderCircle, Radio } from 'lucide-react';

export type AiConnectionState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'connected'; modelCount: number; durationMs: number }
  | { status: 'empty'; durationMs: number }
  | { status: 'catalog-failed'; message: string }
  | { status: 'failed'; message: string };

export function AiConnectionStatus({ state }: { state: AiConnectionState }) {
  if (state.status === 'idle') {
    return <div className="ai-connection-status idle" aria-live="polite"><Radio size={13} /><span>Connection not tested</span></div>;
  }
  if (state.status === 'checking') {
    return <div className="ai-connection-status checking" role="status"><LoaderCircle className="spin" size={13} /><span>Checking endpoint and listing models…</span></div>;
  }
  if (state.status === 'connected') {
    return <div className="ai-connection-status connected" role="status"><CheckCircle2 size={13} /><span>Connected · {state.modelCount} model{state.modelCount === 1 ? '' : 's'} · {state.durationMs} ms</span></div>;
  }
  if (state.status === 'catalog-failed') {
    return <div className="ai-connection-status warning" role="alert"><CircleAlert size={13} /><span>Model catalogue unavailable · {state.message} · enter a model ID to try generation</span></div>;
  }
  if (state.status === 'empty') {
    return <div className="ai-connection-status warning" role="status"><CircleAlert size={13} /><span>Endpoint responded but listed no models · {state.durationMs} ms</span></div>;
  }
  return <div className="ai-connection-status failed" role="alert"><CircleAlert size={13} /><span>Connection failed · {state.message}</span></div>;
}
