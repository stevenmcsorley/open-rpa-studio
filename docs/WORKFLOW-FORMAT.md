# Workflow format notes

Workflow files are UTF-8 JSON documents with `format: "openrpa.workflow"` and `formatVersion: 1`. A workflow uses one execution model at a time: the default `sequence`, a `flowchart`, or a `state_machine`. The unused execution model's activity array remains empty. Common variables, arguments and activity schemas are described in [ARCHITECTURE.md](ARCHITECTURE.md) and validated by both the desktop engine and browser preview.

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
