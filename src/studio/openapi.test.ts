import { describe,expect,it } from 'vitest';
import { configureFromOpenApi,configureOpenApiOperation,parseOpenApi } from './openapi';

const spec=`openapi: 3.0.3
info: { title: Inventory, version: '2.1' }
servers:
  - url: https://inventory.example/v2
paths:
  /items/{itemId}:
    parameters:
      - $ref: '#/components/parameters/ItemId'
    get:
      summary: Get one inventory item
      parameters:
        - name: includeHistory
          in: query
          required: false
          schema: { type: boolean }
        - name: X-Client
          in: header
          required: true
          schema: { type: string }
      responses: { '200': { description: ok } }
    patch:
      operationId: updateItem
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                quantity: { type: integer, example: 4 }
                note: { type: string, example: counted }
      responses: { '200': { description: ok } }
components:
  parameters:
    ItemId:
      name: itemId
      in: path
      required: true
      schema: { type: string }
`;

describe('OpenAPI import',()=>{
  it('reads YAML, local references, parameters, and request-body examples',()=>{
    const imported=parseOpenApi(spec);
    expect(imported.title).toBe('Inventory');expect(imported.version).toBe('2.1');expect(imported.operations).toHaveLength(2);
    const get=imported.operations[0];expect(get.server).toBe('https://inventory.example/v2');
    expect(configureFromOpenApi(get)).toEqual({method:'GET',path:'/items/{{ pathItemId }}',query:{},headers:{'X-Client':'{{ headerXClient }}'}});
    expect(get.parameters.map(row=>[row.name,row.required,row.variable])).toEqual([['itemId',true,'pathItemId'],['includeHistory',false,'queryIncludeHistory'],['X-Client',true,'headerXClient']]);
    const patch=configureFromOpenApi(imported.operations[1]);expect(patch.method).toBe('PATCH');expect(patch.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(patch.body!)).toEqual({quantity:4,note:'counted'});
  });
  it('rejects unsupported specifications and oversized input',()=>{
    expect(()=>parseOpenApi('swagger: 2.0\npaths: {}')).toThrow('OpenAPI 3.0 or 3.1');
    expect(()=>parseOpenApi('x'.repeat(2_000_001))).toThrow('2 MB');
    expect(()=>parseOpenApi('openapi: 3.1.0\npaths: {}')).toThrow('No supported');
  });
  it('records unsupported external parameter references without fetching them',()=>{
    const imported=parseOpenApi(`openapi: 3.0.3\ninfo: {title: External, version: '1'}\npaths:\n  /safe:\n    get:\n      parameters:\n        - $ref: https://evil.example/parameter.yaml\n      responses: {'200': {description: ok}}`);
    expect(imported.operations).toHaveLength(1);expect(imported.operations[0].parameters).toEqual([]);
    expect(imported.warnings[0]).toContain('External OpenAPI reference is not imported');
  });
  it('creates collision-safe string variables and matches every expression to its variable',()=>{
    const operation=parseOpenApi(spec).operations[0];
    const configured=configureOpenApiOperation(operation,[{name:'pathItemId'}]);
    expect(configured.variables.map(item=>item.name)).toEqual(['pathItemId2','headerXClient']);
    expect(configured.patch.path).toBe('/items/{{ pathItemId2 }}');
    expect(configured.patch.headers['X-Client']).toBe('{{ headerXClient }}');
  });
});
