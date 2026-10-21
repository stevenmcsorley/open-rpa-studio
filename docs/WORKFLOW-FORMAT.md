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

## PDF text extraction

`pdf_read_text` extracts selectable PDF text within the project file-size quota, respects cancellation between pages, preserves page boundaries with form-feed separators, and reports page count to a separate variable. It supports an optional bounded page limit and approximate layout mode. Encrypted PDFs and image-only OCR are not supported. See [PDF activity limits](PDF-ACTIVITIES.md).

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
