# Workflow format notes

Workflow files are UTF-8 JSON documents with `format: "openrpa.workflow"` and `formatVersion: 1`. A workflow uses one execution model at a time: the default `sequence`, a `flowchart`, or a `state_machine`. The unused execution model's activity array remains empty. Common variables, arguments and activity schemas are described in [ARCHITECTURE.md](ARCHITECTURE.md) and validated by both the desktop engine and browser preview.

The optional AI drafting panel can request each of the three models. Provider-specific structured-output schemas constrain the outer workflow shape; the local workflow validator then checks activity types, identifiers, graph rules, transitions and expression settings. Invalid drafts remain review-only and cannot be applied from the panel. Validation checks structure and supported settings, not whether the model understood the task or whether the automation is safe for a particular environment. Review every activity and permission before execution.

## Reusable workflow arguments

`invoke_workflow` references another name in `project.workflows`. `inputs` maps child input argument names to JSON values or safe expressions; use a full string expression such as `"{{ customerId }}"` when the caller should pass a typed value. `outputs` maps child `out` and `inout` arguments to caller variable names. Output mappings are per invocation. Unmapped outputs use the argument's legacy `target` property, then the argument name.

```json
{"id":"normalize","type":"invoke_workflow","workflow":"NormalizeOrder","inputs":{"order":"{{ currentOrder }}"},"outputs":{"normalized":"normalizedOrder"}}
```

The desktop validator checks the call against the project's declared workflows before save/run. Expression result types can only be confirmed at runtime. Calls cannot be cyclic, and child execution shares the enclosing run's quotas and cancellation.

## Excel workbook activities

The xlsx_read and xlsx_write activities operate on local .xlsx files in the desktop engine. They use the normal project file-root permissions and audit trail. Limits, supported cell values, formula-cache behavior, and workbook-format constraints are documented in [Excel workbook activities](EXCEL-ACTIVITIES.md). The browser preview has no filesystem access and cannot execute them.

## SQLite database query

`sqlite_query` runs one parameter-bound read-only query against a local approved-root `.db`, `.sqlite`, or `.sqlite3` file. It returns row objects, applies result, size and execution-time caps, checks cancellation through SQLite's VM progress hook, and audits attempts/completions without SQL text or parameter values. Write/DDL, `PRAGMA`, `ATTACH`, and multi-statement statements are denied. See [SQLite Query activity](SQLITE-ACTIVITY.md).

## Filtering record collections

`filter_rows` retains input objects in their original order when configured conditions match. `rows` names a variable or expression that returns a list; `result` names the output variable. `match` is `all` (AND) or `any` (OR). Each condition specifies a field, operator and, except for `is_empty` / `is_not_empty`, a JSON comparison value. Operators include equality, string/list membership, string prefixes/suffixes and ordered numeric or string comparisons. `ignoreCase` applies to text comparisons. A value may use a safe expression such as `"{{ minimumAmount }}"` to supply a typed runtime value. User code is never evaluated. Input is limited to 100,000 object records and 100 conditions; the desktop engine checks cancellation while scanning and records only aggregate input/output counts.

```json
{"id":"open-orders","type":"filter_rows","rows":"orders","conditions":[{"field":"status","operator":"equals","value":"open","ignoreCase":true},{"field":"total","operator":"greater_or_equal","value":"{{ minimumTotal }}"}],"match":"all","result":"eligibleOrders"}
```

The visual properties editor provides condition rows and validates JSON values as they are edited. Browser preview implements the same basic operators but remains an isolated, no-filesystem preview.

## Joining record collections

`join_rows` combines two lists of objects using a typed key on each side. `joinType` supports `inner` (matching rows only) and `left` (preserve unmatched rows from the left input). Duplicate keys produce the full one-to-many or many-to-many result. Left-side fields keep their names; right-side fields receive `rightPrefix` (default `right_`) to avoid collisions. Null or missing keys do not match. Keys match only within the same scalar type; finite numbers compare numerically, while booleans and strings remain distinct. Inputs are capped at 100,000 objects each and 2,000 fields per object; `maxRows` bounds the expanded result to 100,000 rows. An over-limit join fails without assigning a partial result. Cancellation is checked while indexing and producing rows.

```json
{"id":"enrich-orders","type":"join_rows","left":"orders","right":"customers","leftKey":"customerId","rightKey":"id","joinType":"left","rightPrefix":"customer_","maxRows":100000,"result":"enrichedOrders"}
```

The join is a native local operation. It preserves left-row order and the source order of duplicate right-side matches. The execution event records counts and join type only, not record contents.

## Grouping and aggregation

`group_rows` collects records by up to 100 scalar fields and returns one output row for each unique key, in first-seen order. Missing and null values form the same group; string, Boolean and number keys remain type-aware. Supported aggregations are `count_rows`, `count_values` (non-null values), `sum`, `average`, `min`, and `max`. Numeric operations accept finite numbers and ignore null or missing fields; text and numeric values may not be mixed in one `min`/`max` result. An all-null sum and average are `null`, while counts are zero. With no grouping fields, an empty input still produces one aggregate row. Inputs are limited to 100,000 object records, 2,000 fields per record, 100 grouping fields and 100 aggregations; output groups are capped at 100,000. The native engine checks cancellation while scanning input.

```json
{"id":"department-summary","type":"group_rows","rows":"orders","groupBy":["department"],"aggregations":[{"field":"amount","operation":"sum","as":"totalAmount"},{"field":"amount","operation":"average","as":"averageAmount"},{"operation":"count_rows","as":"recordCount"}],"maxGroups":100000,"result":"departmentSummary"}
```

The visual editor lets users add and remove grouping fields and aggregation definitions. Browser preview uses exact decimal-string accumulation for ordinary safe numeric inputs; unsafe integer inputs are refused there because JavaScript cannot represent them exactly. The desktop engine retains Python integer precision.

## PDF text extraction

`pdf_read_text` extracts selectable PDF text within the project file-size quota, respects cancellation between pages, preserves page boundaries with form-feed separators, and reports page count to a separate variable. It supports an optional bounded page limit and approximate layout mode. Encrypted PDFs and image-only OCR directly inside PDFs are not supported. The separate [local OCR activity](IMAGE-OCR.md) accepts PNG, JPEG and BMP image files.

## State machine

State-machine workflows store ordered activity lists per state. After the activities finish, guarded transitions are checked in file order. A guard must evaluate to a Boolean. A transition without `condition` is the optional, last fallback. Each non-final state needs at least one outgoing transition; a final state has none. The initial state and every state must be reachable, and at least one state must be final. Repeated visits use the normal project execution quota.

```json
{
  "format": "openrpa.workflow",
  "formatVersion": 1,
  "name": "Approval route",
  "executionModel": "state_machine",
  "variables": [{"name": "approved", "type": "boolean", "value": false}],
  "arguments": [],
  "activities": [],
  "stateMachine": {
    "initial": "review",
    "states": [
      {"id": "review", "label": "Review", "activities": [{"id": "review-log", "type": "log", "message": "Reviewing request"}]},
      {"id": "accepted", "label": "Accepted", "final": true, "activities": []},
      {"id": "declined", "label": "Declined", "final": true, "activities": []}
    ],
    "transitions": [
      {"from": "review", "to": "accepted", "condition": "approved"},
      {"from": "review", "to": "declined"}
    ]
  }
}
```

State machine transitions are not resumable checkpoints. The engine only resumes a workflow by starting a new run, so external effects that happened before a failure may happen again if the user explicitly reruns it. Use idempotent operations or external deduplication for consequential actions.

## Sort Rows

`sort_rows` writes an ordered shallow copy of a list of JSON records to the configured result variable. It accepts 1–50 unique keys, each with a field name, `ascending` or `descending` direction, and `first` or `last` null placement. Missing fields are treated as null. Null placement is independent of sort direction. Equal keys retain input order.

Within each key field, non-null values must be consistently numbers, strings, or Booleans. Numbers are compared numerically; text uses Unicode code-point ordering; Booleans use `false < true`. Mixed non-null types and non-finite numbers fail with an activity-level diagnostic. Inputs are limited to 100,000 records and each record to 2,000 fields; `maxRows` can lower the input limit. Sorting does not mutate the input list.

```json
{
  "id": "sort-orders",
  "type": "sort_rows",
  "rows": "orders",
  "keys": [
    {"field": "department", "direction": "ascending", "nulls": "last"},
    {"field": "priority", "direction": "descending", "nulls": "first"}
  ],
  "maxRows": 25000,
  "result": "sortedOrders"
}
```
