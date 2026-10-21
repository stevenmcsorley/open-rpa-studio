import { describe, expect, it } from 'vitest';
import { aiEndpointChangeReset, aiProviderChangeReset } from './aiProviderChange';

describe('aiProviderChangeReset', () => {
  it('drops the previous profile and vault reference when changing provider', () => {
    expect(aiProviderChangeReset('openrouter', 'https://openrouter.ai/api/v1')).toEqual({
      provider: 'openrouter',
      baseUrl: 'https://openrouter.ai/api/v1',
      model: '',
      models: [],
      error: '',
      connectionId: '',
      connectionName: '',
      credentialService: '',
      credentialUsername: '',
      credentialSecret: '',
      draft: null,
      connectionState: { status: 'idle' },
    });
  });

  it('drops the previous profile and vault reference when changing endpoint', () => {
    expect(aiEndpointChangeReset('https://proxy.example/v1')).toEqual({
      baseUrl: 'https://proxy.example/v1',
      model: '',
      models: [],
      error: '',
      connectionId: '',
      connectionName: '',
      credentialService: '',
      credentialUsername: '',
      credentialSecret: '',
      draft: null,
      connectionState: { status: 'idle' },
    });
  });
});
