# API activities

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
