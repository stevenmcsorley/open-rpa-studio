# AI workflow drafting

The optional AI panel can ask a connected provider to draft one of the workflow models that the Studio engine can execute:

- **Sequence** — an ordered activity list.
- **Flowchart** — a start node, action or decision nodes, transitions, and an end node.
- **State machine** — an initial state, state-local activities, guarded transitions, and final states.

For OpenAI, choose either **OpenAI API** (Chat Completions) or **OpenAI API (Responses)**. The Responses adapter uses `/v1/responses`, sends schema-constrained output via `text.format`, disables response storage, and handles refusal/incomplete responses explicitly. This protocol is only for the OpenAI API profile; OpenRouter, LM Studio and compatible endpoints retain their own Chat Completions behavior. API model and feature availability depends on the selected model/account.

Chat Completions adapters accept either a JSON string or text content blocks, including a single complete `json` fenced block. They first request JSON Schema output. If an endpoint explicitly rejects `response_format`/`json_schema` as unsupported with HTTP 400, 404 or 422, Studio retries once with the same schema placed in the system instructions and requires raw JSON. The OpenAI Responses adapter has the same bounded fallback to JSON-object mode, and Ollama retries once from JSON Schema format to JSON mode when the server explicitly rejects schema format. These compatibility paths never retry unrelated errors. Malformed fallback output is rejected. The draft panel shows a compatibility warning and the audit history records the provider/model fallback without storing the prompt or response. A fallback request can incur additional provider latency or cost. Explicit refusals and output-length truncation are surfaced as distinct errors. Tool-only responses, malformed fences, non-object JSON and invalid JSON are rejected; the bridge then applies the workflow validator before a draft can be reviewed.

The model field offers IDs discovered through the provider's model catalogue and also accepts a manually entered ID up to 200 characters. Use this when a compatible endpoint supports generation but filters or omits its model-list route. A successful manual draft is still subject to the provider's own model access rules and normal workflow validation. A failed catalogue check does not prove generation is unavailable; the provider's actual response to the draft request is authoritative.

While a draft is in flight, **Stop waiting** sends a request-ID-scoped cancellation to the native bridge, closes the active HTTP transport, closes the panel, and invalidates the UI request generation so any late result cannot overwrite a reopened panel. Cancellation is checked during TCP connection, TLS handshake, request sending, and response waiting. DNS lookup uses the operating-system resolver and cannot be forcibly interrupted; once a provider has received a request, disconnecting does not guarantee its server stops computing or avoids charging. The UI reports this limitation.

The task description is sent as a JSON-encoded user message, separate from adapter system instructions. This keeps user text out of the system field and gives the model an explicit data boundary, but it does not eliminate prompt injection. Anthropic requests use the Messages API contract (`system`, `messages`, `tools`, and forced tool selection); see the [Anthropic Messages API reference](https://docs.anthropic.com/en/api/messages). Returned content is still untrusted and must pass local workflow validation and human review.

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

## Current live Ollama acceptance

On 21 October 2026, the reproducible acceptance command `uv run --locked python scripts/acceptance_ollama.py` ran against the locally installed Ollama 0.40.6 model `qwen35-4b:latest`. It exercised the native Ollama adapter, local workflow validator, and execution engine. The sequence, flowchart, and state-machine drafts each passed validation and executed as exactly one `hello` log event. Timings were 1.233 s, 3.787 s, and 2.413 s respectively. The server accepted JSON Schema mode, so no compatibility retry was used. The command creates and removes temporary projects, requires no credential or external network, and can be pointed at another installed model using `--model` or `OPENRPA_OLLAMA_TEST_MODEL`. This is a local smoke acceptance, not a model-quality benchmark or evidence for remote provider behavior.

## Provider credentials

Remote provider keys can be stored from the desktop AI drafting panel. The app sends the value to its local Python bridge over the Tauri command channel, which accepts only an approved OS credential vault backend. The secret is not returned in the RPC response, audit entry, project, or workflow. It is held in the UI only while the form is open and cleared after a successful store or when the panel closes. If the OS vault is unavailable or uses an unsupported plaintext backend, storage fails closed. Local providers such as Ollama and LM Studio do not require credentials by default.

Remote providers require HTTPS and credentials stored through the OS credential-vault flow. Prompts sent to remote providers leave the computer. The core Studio remains usable without an AI provider. The OpenAI Responses adapter follows the [official Responses API reference](https://platform.openai.com/docs/api-reference/responses) and [structured outputs documentation](https://platform.openai.com/docs/guides/structured-outputs).

## Saved provider connections

The desktop AI panel can save and select multiple named connection profiles. The app stores provider ID, endpoint, model choice and OS-vault service/username references in the per-user `ai-connections.json` file alongside local application history. It rejects unknown fields, unsupported providers, unsafe local/remote URLs, duplicate IDs/names, oversized files and more than 100 profiles. API keys are never accepted as profile fields. Deleting a profile removes only that local configuration; it does not delete a credential from the OS vault.


## Repairing a failed workflow

After a failed desktop run, the AI panel can prepare a repair prompt from the exact workflow snapshot used for that run. It includes the structured failure code and workflow/activity identifiers, but omits raw error text, runtime variable values, and argument defaults. Object properties whose names resemble secrets (password, token, API key, authorization, credential, or cookie) are removed recursively.

Configured literals that define behavior—such as file paths, URLs, selectors, and message strings—can remain in the workflow definition sent to the selected provider. Remote provider requests leave the computer. Inspect the prompt in the panel before sending it. A proposed repair must pass the normal workflow validator and remains an uncommitted draft until **Review and replace current workflow** is selected; it is never executed automatically. The in-memory failure snapshot is not persisted and is lost when Studio closes.
