import { describe,expect,it } from 'vitest';
import { configureFromOpenApi,configureOpenApiOperation,connectionSeedFromOpenApi,createReusableApiWorkflow,parseOpenApi } from './openapi';

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
  it('prefills a reusable API-key connection from an unambiguous OpenAPI server and security scheme',()=>{
    const operation=parseOpenApi(`openapi: 3.1.0
info: {title: Inventory, version: '1'}
servers: [{url: 'https://inventory.example/v3'}]
security: [{partnerKey: []}]
paths: {/items: {get: {responses: {'200': {description: ok}}}}}
components: {securitySchemes: {partnerKey: {type: apiKey, in: header, name: X-Partner-Key}}}`).operations[0];
    const seed=connectionSeedFromOpenApi(operation,'Inventory');
    expect(seed.profile).toMatchObject({name:'Inventory (inventory.example)',baseUrl:'https://inventory.example/v3',authType:'api_key_header',apiKeyHeader:'X-Partner-Key'});
    expect(seed.warning).toBeUndefined();
  });
  it('prefills bearer and OAuth metadata but refuses to guess combined or alternative authentication',()=>{
    const bearer=parseOpenApi(`openapi: 3.0.3\ninfo: {title: Bearer API}\nservers: [{url: 'https://api.example/v1'}]\nsecurity: [{token: []}]\npaths: {/x: {get: {responses: {'200': {description: ok}}}}}\ncomponents: {securitySchemes: {token: {type: http, scheme: bearer}}}`).operations[0];
    expect(connectionSeedFromOpenApi(bearer).profile.authType).toBe('bearer');
    const ambiguous={...bearer,securityAlternatives:[{schemes:[{name:'token',kind:'bearer' as const,detail:'Bearer token'}]},{schemes:[{name:'key',kind:'api_key_header' as const,detail:'API key',headerName:'X-Key'}]}]};
    const seed=connectionSeedFromOpenApi(ambiguous);
    expect(seed.profile.authType).toBe('none');
    expect(seed.warning).toContain('No authentication was guessed');
  });
  it('rejects non-HTTPS, templated, or relative OpenAPI servers for connection prefill',()=>{
    const operation=parseOpenApi(`openapi: 3.0.3\ninfo: {title: API}\nservers: [{url: 'http://api.example/v1'}]\npaths: {/x: {get: {responses: {'200': {description: ok}}}}}`).operations[0];
    expect(()=>connectionSeedFromOpenApi(operation)).toThrow('absolute HTTPS');
    expect(()=>connectionSeedFromOpenApi({...operation,server:'https://{tenant}.example/v1'})).toThrow('template variables');
    expect(()=>connectionSeedFromOpenApi({...operation,server:'/relative'})).toThrow('absolute HTTPS');
  });
  it('imports DELETE operations so they can receive a destructive run review',()=>{
    const imported=parseOpenApi(`openapi: 3.0.3
info: {title: Records, version: '1'}
paths:
  /records/{id}:
    delete:
      operationId: removeRecord
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '204': {description: Removed}`);
    expect(imported.operations).toHaveLength(1);
    expect(configureFromOpenApi(imported.operations[0])).toMatchObject({method:'DELETE',path:'/records/{{ pathId }}'});
  });
  it('reads YAML, local references, parameters, and request-body examples',()=>{
    const imported=parseOpenApi(spec);
    expect(imported.title).toBe('Inventory');expect(imported.version).toBe('2.1');expect(imported.operations).toHaveLength(2);
    const get=imported.operations[0];expect(get.server).toBe('https://inventory.example/v2');
    expect(configureFromOpenApi(get)).toEqual({method:'GET',path:'/items/{{ pathItemId }}',query:{},headers:{'X-Client':'{{ headerXClient }}'}});
    expect(get.parameters.map(row=>[row.name,row.required,row.variable])).toEqual([['itemId',true,'pathItemId'],['includeHistory',false,'queryIncludeHistory'],['X-Client',true,'headerXClient']]);
    const patch=configureFromOpenApi(imported.operations[1]);expect(patch.method).toBe('PATCH');expect(patch.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(patch.body!)).toEqual({quantity:4,note:'counted'});
  });
  it('keeps API keys and token-like OpenAPI headers out of workflow files',()=>{
    const imported=parseOpenApi(`openapi: 3.0.3
info: {title: Secure API, version: '1'}
paths:
  /items:
    get:
      parameters:
        - name: X-API-Key
          in: header
          required: true
          schema: {type: string}
        - name: X-Request-Id
          in: header
          required: true
          schema: {type: string}
      responses: {'200': {description: ok}}`);
    const operation=imported.operations[0];
    expect(operation.parameters.map(parameter=>parameter.name)).toEqual(['X-Request-Id']);
    expect(configureFromOpenApi(operation).headers).toEqual({'X-Request-Id':'{{ headerXRequestId }}'});
    expect(imported.warnings.some(warning=>warning.includes('sensitive header parameter X-API-Key'))).toBe(true);
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
  it('clears stale response and pagination settings when applying a different OpenAPI operation',()=>{
    const operation=parseOpenApi(spec).operations[1];
    const configured=configureOpenApiOperation(operation,[]);
    expect(configured.patch.pagination).toBeUndefined();
    expect(configured.patch.responseMapping).toBeUndefined();
    expect(configured.patch.retryPolicy).toBeUndefined();
  });
  it('imports an unambiguous successful JSON object array as bounded response mapping',()=>{
    const imported=parseOpenApi(`openapi: 3.1.0
info: {title: Orders, version: '1'}
paths:
  /orders:
    get:
      responses:
        '200':
          description: Orders
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      items:
                        type: array
                        items: {$ref: '#/components/schemas/Order'}
components:
  schemas:
    Order:
      type: object
      properties:
        id: {type: integer}
        customer: {type: object, properties: {name: {type: string}}}
        active: {type: boolean}
        lines: {type: array, items: {type: string}}
`);
    const operation=imported.operations[0];
    expect(operation.responseMapping).toEqual({responseCode:'200',itemsPointer:'/data/items',fields:[{name:'id',path:'/id'},{name:'customerName',path:'/customer/name'},{name:'active',path:'/active'}]});
    const configured=configureOpenApiOperation(operation,[{name:'apiItems'}]);
    expect(configured.patch.responseMapping).toEqual({...operation.responseMapping,result:'apiItems2',maxItems:10000,maxOutputBytes:5_000_000});
  });
  it('generates an editable reusable API workflow with typed inputs and outputs',()=>{
    const operation=parseOpenApi(`openapi: 3.1.0
info: {title: Orders, version: '1'}
servers: [{url: 'https://orders.example/v1'}]
paths:
  /orgs/{orgId}/orders:
    get:
      operationId: listOrders
      parameters:
        - {name: orgId, in: path, required: true, schema: {type: string}}
        - {name: state, in: query, required: true, schema: {type: string}}
        - {name: pageSize, in: query, required: false, schema: {type: integer}}
        - {name: X-Region, in: header, required: false, schema: {type: string}}
      responses:
        '200':
          description: Orders
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                    items:
                      type: object
                      properties:
                        id: {type: string}
                        customer: {type: object, properties: {name: {type: string}}}
`).operations[0];
    const reusable=createReusableApiWorkflow(operation,'saved-orders','Orders API - List Orders');
    expect(reusable).toMatchObject({format:'openrpa.workflow',formatVersion:1,name:'Orders API - List Orders',executionModel:'sequence'});
    expect(reusable.arguments).toEqual([
      {name:'pathOrgId',type:'string',direction:'in',required:true},
      {name:'queryState',type:'string',direction:'in',required:true},
      {name:'queryPageSize',type:'string',direction:'in',required:false,default:''},
      {name:'headerXRegion',type:'string',direction:'in',required:false,default:''},
      {name:'apiResponse',type:'object',direction:'out',required:false,target:'apiResponse'},
      {name:'apiItems',type:'array',direction:'out',required:false,target:'apiItems'}
    ]);
    expect(reusable.activities[0]).toMatchObject({type:'api_request',connectionId:'saved-orders',method:'GET',path:'/orgs/{{ pathOrgId }}/orders',query:{state:'{{ queryState }}',pageSize:'{{ queryPageSize }}'},headers:{'X-Region':'{{ headerXRegion }}'},omitEmptyQuery:['pageSize'],omitEmptyHeaders:['X-Region'],result:'apiResponse',responseMapping:{result:'apiItems',maxItems:10_000,maxOutputBytes:5_000_000}});
    expect(()=>createReusableApiWorkflow(operation,'','Invalid')).toThrow('Choose a saved API connection');
  });
  it('leaves mapping unset for ambiguous arrays and never fetches external response schemas',()=>{
    const ambiguous=parseOpenApi(`openapi: 3.0.3
info: {title: Ambiguous, version: '1'}
paths:
  /items:
    get:
      responses:
        '200':
          description: ambiguous
          content:
            application/json:
              schema:
                type: object
                properties:
                  items: {type: array, items: {type: object, properties: {id: {type: string}}}}
                  archived: {type: array, items: {type: object, properties: {id: {type: string}}}}
`);
    expect(ambiguous.operations[0].responseMapping).toBeUndefined();
    expect(ambiguous.warnings.some(item=>item.includes('multiple JSON object arrays'))).toBe(true);
    const external=parseOpenApi(`openapi: 3.0.3
info: {title: External, version: '1'}
paths:
  /items:
    get:
      responses:
        '200':
          description: external schema
          content:
            application/json:
              schema: {$ref: 'https://example.invalid/schema.json'}
`);
    expect(external.operations[0].responseMapping).toBeUndefined();
    expect(external.warnings.some(item=>item.includes('External OpenAPI reference is not imported'))).toBe(true);
  });
  it('suggests supported saved-connection authentication without flattening OR/AND requirements or importing secrets',()=>{
    const imported=parseOpenApi(`openapi: 3.1.0
info: {title: Secured API, version: '1'}
security:
  - BearerAuth: []
  - ClientKey: []
paths:
  /inherited:
    get: {responses: {'200': {description: ok}}}
  /public:
    get:
      security: []
      responses: {'200': {description: ok}}
  /combined:
    get:
      security:
        - BearerAuth: []
          OAuthClient:
            - orders.read
      responses: {'200': {description: ok}}
components:
  securitySchemes:
    BearerAuth: {type: http, scheme: bearer, bearerFormat: JWT}
    ClientKey: {type: apiKey, in: header, name: X-Client-Key}
    OAuthClient:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://auth.example.test/token
          scopes: {orders.read: Read orders, orders.write: Write orders}
`);
    const [inherited,pub,combined]=imported.operations;
    expect(inherited.securityAlternatives?.map(item=>item.schemes.map(scheme=>scheme.kind))).toEqual([['bearer'],['api_key_header']]);
    expect(inherited.securityAlternatives?.[1].schemes[0].headerName).toBe('X-Client-Key');
    expect(pub.securityAlternatives).toEqual([]);
    expect(combined.securityAlternatives?.[0].schemes.map(scheme=>scheme.kind)).toEqual(['bearer','oauth_client_credentials']);
    expect(combined.securityAlternatives?.[0].schemes[1].tokenUrl).toBe('https://auth.example.test/token');
    expect(combined.securityAlternatives?.[0].schemes[1].scopes).toEqual(['orders.read']);
    expect(imported.warnings).toEqual([]);
  });
  it('marks authentication schemes unsupported when the saved connection cannot safely represent them',()=>{
    const imported=parseOpenApi(`openapi: 3.0.3
info: {title: Unsupported Auth, version: '1'}
security:
  - BadKey: []
  - RelativeOAuth: []
paths:
  /items:
    get: {responses: {'200': {description: ok}}}
components:
  securitySchemes:
    BadKey: {type: apiKey, in: header, name: Authorization}
    RelativeOAuth:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: /oauth/token
          scopes: {}
`);
    const schemes=imported.operations[0].securityAlternatives?.flatMap(item=>item.schemes)??[];
    expect(schemes.map(item=>item.kind)).toEqual(['unsupported','unsupported']);
    expect(schemes[0].detail).toContain('not supported');
    expect(schemes[1].detail).toContain('absolute public HTTPS URL');
  });
  it('recognizes OAuth authorization code and PKCE security schemes',()=>{
    const imported=parseOpenApi(`openapi: 3.1.0
info: {title: Calendar, version: '1'}
paths:
  /events:
    get:
      security: [{CalendarOAuth: [events.read]}]
      responses: {'200': {description: ok}}
components:
  securitySchemes:
    CalendarOAuth:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://login.example.test/authorize
          tokenUrl: https://login.example.test/token
          scopes: {events.read: Read calendar events}
`);
    const scheme=imported.operations[0].securityAlternatives?.[0].schemes[0];
    expect(scheme?.kind).toBe('oauth_authorization_code');
    expect(scheme?.authorizationUrl).toBe('https://login.example.test/authorize');
    expect(scheme?.tokenUrl).toBe('https://login.example.test/token');
    expect(scheme?.scopes).toEqual(['events.read']);
  });
});
