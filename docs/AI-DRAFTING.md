# AI workflow drafting

The optional AI panel can ask a connected provider to draft one of the workflow models that the Studio engine can execute:

- **Sequence** — an ordered activity list.
- **Flowchart** — a start node, action or decision nodes, transitions, and an end node.
- **State machine** — an initial state, state-local activities, guarded transitions, and final states.

The selected provider returns structured output. The bridge applies the ordinary workflow validator before the editor enables **Review and replace current workflow**. Drafting never starts execution. The user should inspect each activity, expression, selector, file path, destination, and permission before running it. Structural validation cannot prove that a model understood the task or that the resulting automation is safe for a specific system.

Activity settings belong directly on each activity object. Graph control nodes cannot contain activities; node IDs and activity IDs must not collide. The schema and prompt state these constraints explicitly, and the workflow validator remains the final check.

## Verified local run

The v0.1.4 development build was exercised against the installed local Ollama model `qwen35-4b:latest` with three generic, non-sensitive requests. Each draft was returned through the native provider adapter, checked by `validate_workflow`, saved to a temporary project, and executed by `WorkflowEngine` via `run_project`.

| Model | Validator | Engine status | Observed output |
|---|---|---|---|
| Sequence | Valid | `succeeded` | Log event: `hello` |
| Flowchart | Valid | `succeeded` | Start → log `hello` → end |
| State machine | Valid | `succeeded` | Initial state logs `hello` → final state |

These are smoke tests, not a quality evaluation across tasks or models. A larger local model (`qwen3.5:9b-q4_K_M`) produced a valid sequence but hit the bridge's 180-second provider timeout for graph-shaped requests in this environment. The smaller 4B model completed the tested graph drafts in a few seconds. Model, hardware, prompt complexity, and schema support affect latency and correctness. Invalid output is rejected by the editor; timeouts surface as provider errors.

Remote providers require HTTPS and credentials stored through the OS credential-vault flow. Prompts sent to remote providers leave the computer. The core Studio remains usable without an AI provider.
