# AI workflow drafting

The optional AI panel can ask a connected provider to draft one of the workflow models that the Studio engine can execute:

- **Sequence** — an ordered activity list.
- **Flowchart** — a start node, action or decision nodes, transitions, and an end node.
- **State machine** — an initial state, state-local activities, guarded transitions, and final states.

For OpenAI, choose either **OpenAI API** (Chat Completions) or **OpenAI API (Responses)**. The Responses adapter uses `/v1/responses`, sends schema-constrained output via `text.format`, disables response storage, and handles refusal/incomplete responses explicitly. This protocol is only for the OpenAI API profile; OpenRouter, LM Studio and compatible endpoints retain their own Chat Completions behavior. API model and feature availability depends on the selected model/account.

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

## Provider credentials

Remote provider keys can be stored from the desktop AI drafting panel. The app sends the value to its local Python bridge over the Tauri command channel, which accepts only an approved OS credential vault backend. The secret is not returned in the RPC response, audit entry, project, or workflow. It is held in the UI only while the form is open and cleared after a successful store or when the panel closes. If the OS vault is unavailable or uses an unsupported plaintext backend, storage fails closed. Local providers such as Ollama and LM Studio do not require credentials by default.

Remote providers require HTTPS and credentials stored through the OS credential-vault flow. Prompts sent to remote providers leave the computer. The core Studio remains usable without an AI provider. The OpenAI Responses adapter follows the [official Responses API reference](https://platform.openai.com/docs/api-reference/responses) and [structured outputs documentation](https://platform.openai.com/docs/guides/structured-outputs).

## Saved provider connections

The desktop AI panel can save and select multiple named connection profiles. The app stores provider ID, endpoint, model choice and OS-vault service/username references in the per-user `ai-connections.json` file alongside local application history. It rejects unknown fields, unsupported providers, unsafe local/remote URLs, duplicate IDs/names, oversized files and more than 100 profiles. API keys are never accepted as profile fields. Deleting a profile removes only that local configuration; it does not delete a credential from the OS vault.


## Repairing a failed workflow

After a failed desktop run, the AI panel can prepare a repair prompt from the exact workflow snapshot used for that run. It includes the structured failure code and workflow/activity identifiers, but omits raw error text, runtime variable values, and argument defaults. Object properties whose names resemble secrets (password, token, API key, authorization, credential, or cookie) are removed recursively.

Configured literals that define behavior—such as file paths, URLs, selectors, and message strings—can remain in the workflow definition sent to the selected provider. Remote provider requests leave the computer. Inspect the prompt in the panel before sending it. A proposed repair must pass the normal workflow validator and remains an uncommitted draft until **Review and replace current workflow** is selected; it is never executed automatically. The in-memory failure snapshot is not persisted and is lost when Studio closes.
