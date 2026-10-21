# API activities

Open RPA Studio supports both a reusable connection-based **API Request** activity and a bounded page-numbered **Paginated API Read** activity. Both require explicit per-run network permission, use the restricted HTTP client, reject non-public DNS destinations, allow only standard HTTP(S) ports, and do not follow redirects.

## Reusable API connections

Open **API Connections** from the Studio toolbar to create a named HTTPS profile. A profile can define shared non-secret headers, a minimum interval between requests, and authentication modes: none, bearer token, API key in a configurable header, or OAuth 2.0 client credentials. Credential values are sent directly to the native bridge and stored in the operating-system credential vault. OAuth uses the HTTPS token endpoint, client ID, scope and optional audience, with HTTP Basic or form-body client authentication. Client secrets remain in the vault and issued access tokens are cached only in memory during one workflow run, then refreshed before expiry. OAuth requests use the restricted public egress client, do not follow redirects, and never log token or secret fields. The local JSON profile file contains only endpoint and configuration metadata. MCP clients can list profiles without receiving secrets; workflows refer to a profile by its opaque ID.

Add **API Request** from the API Connectors activity category. Choose a saved connection, then configure a relative path, GET/POST/PUT/PATCH method, query parameters, per-request headers, an optional text body, request timeout, response-size bound, and result variable. Paths cannot switch hosts, use protocol-relative URLs, or contain `..` traversal segments. Shared and request headers cannot override the profile-managed authentication header. The raw result contains HTTP status, response headers, response body, and redirect metadata. Optionally add a JSON response mapping to select a JSON array by RFC 6901 JSON Pointer and map up to 50 scalar fields from each object into a bounded list of records. The raw response remains available alongside mapped records. Mapping requires a successful 2xx response, valid JSON, an array of objects, and a configured row limit (up to 10,000).

### Import an OpenAPI operation

Select an **API Request** activity and choose **Import OpenAPI**. Pick a local OpenAPI 3.0 or 3.1 JSON/YAML file (up to 2 MB), select an operation, review its parameters and response mapping, and choose **Apply operation to activity**. Studio lists GET, POST, PUT, and PATCH operations; applying one fills the method, relative path, required query/header parameters, JSON request-body example, Content-Type, and any unambiguous successful JSON object-array mapping in the regular editable activity. The response mapper chooses a 2xx JSON response (preferring 200), supports a unique root or nested object array, and maps declared scalar properties, including nested scalar leaves. It does not guess when multiple candidate arrays exist. It creates string variables for required parameters and inserts expressions into the request. Optional parameters are omitted by default. Fill required parameter variables before running. The server URL from the document is shown as a reference; select a saved API connection whose base URL matches it.

Import parses the selected local file only; it makes no network requests and does not execute code from the specification. Only local `#/...` references are resolved. External references are reported and skipped without fetching them. Security schemes are not imported; set credentials on the saved API connection. Non-JSON request bodies are left blank with a warning, large examples and excess parameters are skipped with warnings. Automatic response mapping requires an explicit array-of-objects schema and scalar fields; ambiguous arrays, unsupported schema compositions and missing response schemas are left unmapped. Review the generated JSON pointers and fields against the provider's real response contract. Importing a spec never grants network permission.

The connection test performs a bounded GET and displays only status and content type; it never returns the response body in the UI. Authorization Code and PKCE flows, refresh-token grants, cookie sessions, DELETE requests, automatic retries, cursor/next-link pagination, and richer arbitrary JSON transformations remain future work. OAuth client credentials has been unit-tested with mocked token responses but has not been acceptance-tested against a real provider account. The browser preview cannot access the native vault or make API requests; execute in the desktop app after enabling network permission.

Open RPA Studio has a native **Paginated API Read** activity for read-only, page-numbered JSON APIs. It is intended for common REST endpoints that accept a page number and page-size query parameter. The activity uses the same restricted HTTP client as HTTP Request: per-run network permission is required, DNS answers must be public, only standard HTTP(S) ports are permitted, and redirects are never followed.

## Configure a paginated read

Add **Paginated API Read** from the API Connectors activity category and configure:

| Property | Purpose | Default and limit |
|---|---|---|
| `url` | API endpoint, optionally using workflow expressions | Required; up to 8,192 characters |
| `headers` | Request headers | Up to 50 bounded text headers; transport headers cannot be overridden |
| `pageParam` | Query parameter for the page number | `page`; blank disables it |
| `pageSizeParam` | Query parameter for page size | `limit`; blank disables it |
| `pageSize` | Requested records per page | 100; maximum 1,000 |
| `itemsPath` | Dotted path to the array in each JSON response | `data.items` |
| `maxPages` | Maximum number of GET requests | 10; maximum 50 |
| `maxItems` | Maximum aggregate records | 10,000; maximum 100,000 |
| `maxTotalBytes` | Maximum response bytes across pages | 5 MB; maximum 20 MB |
| `timeoutSeconds` | Timeout per request | 20 seconds; maximum 60 |
| `result` | Variable receiving the combined records | `items` |
| `metadataResult` | Variable receiving page, count, byte and truncation metadata; blank disables it | `pagination` |

The existing query string is retained, but configured page and size parameters are replaced. Responses must be successful 2xx JSON with an array at `itemsPath`. Reading stops when a page contains fewer records than requested, the array is empty, or a configured bound is reached. The metadata `truncated` flag is true when a bound stops a full page from being read. A request or response error fails the activity with a node-specific diagnostic; partially fetched rows are not assigned to the result variable.

This first connector capability intentionally supports GET and page-number pagination only. It does not yet implement OAuth token exchange, cursor/next-link pagination, retries, adaptive rate limits, connection profiles, or generated mappings. API keys can be supplied through the existing `Credential Get` activity and referenced in headers with a workflow expression, so secret literals need not be saved in the workflow. For example, set a `token` variable from the OS credential vault, then set `Authorization` to `Bearer {{ token }}`. Avoid putting secrets in URLs, logs, or workflow literals.

The activity is available through the local MCP activity catalog. MCP workflow plans mark it as requiring network permission; running it requires the MCP server to be started with the explicit `--allow-run --allow-network` options after reviewing the workflow and destination.
