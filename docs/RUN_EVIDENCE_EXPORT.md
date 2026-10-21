# Run evidence export

The desktop Run History view can export one saved run as a UTF-8 JSON file. The user chooses the destination in the native save dialog after Studio explains that the record may contain sensitive business data.

## Format

The top-level envelope is versioned independently of the project and workflow formats:

```json
{
  "format": "openrpa.run-evidence",
  "formatVersion": 1,
  "run": {
    "runId": "…",
    "projectPath": "…",
    "projectName": "…",
    "workflow": "…",
    "workflowSha256": "…",
    "status": "succeeded",
    "startedAt": "…",
    "endedAt": "…",
    "result": {},
    "error": null,
    "recoveryNote": null,
    "events": []
  }
}
```

The `run` object preserves the durable history record returned by the native bridge. Results and events remain subject to the storage quotas and redaction applied when the run executes. Export does not rerun a workflow or retrieve additional runtime state.

## Integrity and audit

Studio writes the file atomically. The success notice reports the SHA-256 of the exact UTF-8 JSON bytes, including the final newline. The local security audit records `run.export`, the run ID, digest and byte count; it deliberately omits the destination path. The digest detects accidental changes but is not a digital signature and does not prove who created or exported the file.

Treat the output as potentially sensitive. It includes the project path and may include error text, activity results or saved event details. Review the file and remove sensitive fields before sharing it. There is no evidence-import or signature-verification workflow yet.
