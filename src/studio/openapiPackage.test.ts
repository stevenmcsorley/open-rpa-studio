import { describe,expect,it } from 'vitest';
import { createOpenApiConnectorPackage,parseOpenApiConnectorPackage,serializeOpenApiConnectorPackage } from './openapiPackage';

const spec=`openapi: 3.0.3
info: {title: Example API, version: '1'}
servers: [{url: https://api.example.test/v1}]
paths:
  /items:
    get:
      responses: {'200': {description: OK}}
`;

describe('portable OpenAPI connector packages',()=>{
  it('round-trips deterministically and reparses the specification',async()=>{
    const first=await createOpenApiConnectorPackage(spec,'Example API');
    const second=await createOpenApiConnectorPackage(spec,'Example API');
    expect(serializeOpenApiConnectorPackage(first)).toBe(serializeOpenApiConnectorPackage(second));
    const imported=await parseOpenApiConnectorPackage(serializeOpenApiConnectorPackage(first));
    expect(imported.connector.name).toBe('Example API');
    expect(imported.openApi.operations[0].path).toBe('/items');
    expect(imported.connector.sha256).toMatch(/^[a-f0-9]{64}$/);
  });

  it('rejects tampered specifications before loading them',async()=>{
    const pack=await createOpenApiConnectorPackage(spec,'Example API');
    pack.specification=spec.replace('/items','/admin');
    await expect(parseOpenApiConnectorPackage(JSON.stringify(pack))).rejects.toThrow('integrity check failed');
  });

  it('rejects unsupported formats and oversized packages',async()=>{
    await expect(parseOpenApiConnectorPackage('{"format":"other"}')).rejects.toThrow('Unsupported');
    await expect(parseOpenApiConnectorPackage(' '.repeat(12_100_001))).rejects.toThrow('12.1 MB');
  });
});
