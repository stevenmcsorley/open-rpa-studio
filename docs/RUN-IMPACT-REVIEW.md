# Run impact review

Before a normal or debug run, Studio builds a read-only plan from the selected workflow and its saved child workflows. The plan traverses sequence activities, nested branches, flowchart action nodes and state-machine states. It groups configured activities by workflow and identifies file operations, HTTP destinations, browser interactions, desktop controls and credential reads.

Network and desktop grants start unchecked for each run. Users must enable each grant in the run review when the plan requires it. Delete and move operations are marked destructive and require a separate acknowledgement. The workflow cannot start until required grants and destructive acknowledgement are provided. The general toolbar permissions remain for the browser and desktop inspectors; they do not pre-authorize a workflow run.

## Current activity coverage

- File/text, CSV, XLSX and JSON file reads/writes; file copy, move, delete and list.
- HTTP method and configured URL. Request bodies are not expanded or redacted in the summary because templates can contain runtime data.
- Browser navigation URL and other interactions with the active browser page. Only a browser navigation or HTTP activity requests network permission; browser screenshots are shown as local file writes.
- Desktop accessibility actions and screenshot output path.
- Credential reads by activity type, without displaying credential values.
- Reusable workflow calls are expanded recursively, including separate call sites to the same child. If a child definition cannot be inspected or a recursive call is found, Studio requires both network and desktop grants as a fail-safe.

Pure assignments, logging, control-flow nodes, waits, in-memory JSON parsing, text transforms and regular expressions are omitted. Unknown activity types are shown for review as external-risk actions.

## Limits

This is a static preflight, not a sandbox or a proof of runtime behavior. Expressions and variables can change file paths, URLs, request payloads, selectors and other values after the review. Loop iterations can repeat listed actions. A browser interaction can act on a site reached through prior navigation or page redirects. The review does not currently resolve all variable values, calculate loop counts, infer data sensitivity, inspect dynamic plugin effects, or show every request's headers/body. Continue to use approved project roots, the HTTP egress policy, adapter permissions and activity-level validation.

Reproducible planner logic and tests are in `src/studio/executionPlan.ts` and `src/studio/executionPlan.test.ts`.
