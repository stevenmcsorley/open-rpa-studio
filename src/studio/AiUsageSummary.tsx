import type { AiTokenUsage } from './bridge';

function formatted(value:number|undefined):string|undefined {
  if(typeof value!=="number"||!Number.isSafeInteger(value)||value<0)return undefined;
  return new Intl.NumberFormat().format(value);
}

export function AiUsageSummary({usage}:{usage?:AiTokenUsage|null}) {
  const input=formatted(usage?.inputTokens);
  const output=formatted(usage?.outputTokens);
  const total=formatted(usage?.totalTokens);
  if(!input&&!output&&!total)return <small className="field-hint">This provider did not report token usage. No token count or cost is estimated.</small>;
  return <small className="field-hint">Provider-reported tokens{input?` · input ${input}`:''}{output?` · output ${output}`:''}{total?` · total ${total}`:''}. Monetary cost is not estimated.</small>;
}
