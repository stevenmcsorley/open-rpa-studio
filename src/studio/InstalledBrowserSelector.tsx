import type { BrowserStatus } from './BrowserLaunchEditor';

const BUILT_IN = new Set(['chromium', 'chrome', 'msedge']);

export function InstalledBrowserSelector({
  browserStatus,
  channel,
  setChannel,
  executablePath,
  setExecutablePath,
  disabled = false,
  label = 'Inspection Chromium browser',
}: {
  browserStatus?: BrowserStatus;
  channel: string;
  setChannel: (value: string) => void;
  executablePath: string;
  setExecutablePath: (value: string) => void;
  disabled?: boolean;
  label?: string;
}) {
  const installed = Object.entries(browserStatus?.channels ?? {})
    .filter(([id, item]) => !BUILT_IN.has(id) && item.available && item.executable);
  const installedId = installed.find(([, item]) => item.executable === executablePath)?.[0];
  const value = channel === 'custom' && installedId ? `installed:${installedId}` : channel;
  return <>
    <select aria-label={label} value={value} disabled={disabled} onChange={event => {
      const selected = event.target.value;
      if (selected.startsWith('installed:')) {
        const id = selected.slice('installed:'.length);
        setChannel('custom');
        setExecutablePath(browserStatus?.channels?.[id]?.executable ?? '');
      } else {
        setChannel(selected);
        if (selected !== 'custom') setExecutablePath('');
      }
    }}>
      <option value="chromium">Playwright Chromium</option>
      <option value="chrome">Google Chrome</option>
      <option value="msedge">Microsoft Edge</option>
      {installed.length > 0 && <optgroup label="Detected installed browsers">
        {installed.map(([id, item]) => <option key={id} value={`installed:${id}`}>{item.name ?? id}</option>)}
      </optgroup>}
      <option value="custom">Custom Chromium…</option>
    </select>
    {channel === 'custom' && <input aria-label="Inspection browser executable path" placeholder="Absolute path to a Chromium-based browser" value={executablePath} disabled={disabled} onChange={event => setExecutablePath(event.target.value)} />}
  </>;
}
