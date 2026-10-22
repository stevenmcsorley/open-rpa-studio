import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { CredentialManagerDialog } from './CredentialManagerDialog';

describe('CredentialManagerDialog', () => {
  it('explains secure storage and distinguishes the credential label from its vault reference', () => {
    const html = renderToStaticMarkup(<CredentialManagerDialog onClose={() => undefined}/>);
    expect(html).toContain('Credentials');
    expect(html).toContain('Display name');
    expect(html).toContain('Service reference');
    expect(html).toContain('Username reference');
    expect(html).toContain('Secret values are written directly');
  });
});
