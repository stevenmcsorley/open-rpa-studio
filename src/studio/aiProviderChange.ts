export function aiProviderChangeReset(provider: string, baseUrl: string) {
  return {
    provider,
    baseUrl,
    model: '',
    models: [] as string[],
    error: '',
    connectionId: '',
    connectionName: '',
    credentialService: '',
    credentialUsername: '',
    credentialSecret: '',
    draft: null,
    connectionState: { status: 'idle' as const },
  };
}

export function aiEndpointChangeReset(baseUrl: string) {
  return {
    baseUrl,
    model: '',
    models: [] as string[],
    error: '',
    connectionId: '',
    connectionName: '',
    credentialService: '',
    credentialUsername: '',
    credentialSecret: '',
    draft: null,
    connectionState: { status: 'idle' as const },
  };
}
