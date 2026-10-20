# Threat model

## Assets and trust boundaries

Assets include local project files, OS-vault credentials, desktop/browser sessions, and run/audit history. The React UI talks to a Tauri process, which starts a Python bridge; the bridge executes activities in the user's account. Projects and AI drafts are untrusted inputs. Optional Python packages, Node packages, Rust crates and browser binaries are supply-chain dependencies.

## Threats and controls

| Threat | Controls implemented | Residual risk |
| --- | --- | --- |
| Malicious workflow | Strict activity types, bounded expressions, project-root path checks, per-run network/desktop grants, bounded loops/logs and egress checks | Python engine is not an OS sandbox; an authorized workflow can still delete or overwrite project files and interact with external sites |
| Untrusted project/package | Version and workflow validation, bounded input sizes, duplicate/path/symlink checks, streaming extraction and SHA-256 verification | Hashes are self-asserted by the package; no signature or publisher trust exists |
| Compromised dependency | `uv.lock`, `package-lock.json`, `Cargo.lock`; execution dependencies are explicit; dependency review still required | Lockfiles do not prove packages are safe; no automated vulnerability gate or signed artifact pipeline is configured |
| Credential theft | OS keyring only; plaintext keyring backends rejected; secrets masked from saved run result/log events | A workflow with network permission may deliberately transmit a secret; the running process has access to the secret in memory |
| Unintended automation | Per-run permission toggles, browser destination checks, accessible selectors, coordinate adapter separately gated | Desktop actions use focus and coordinates; actions may affect the wrong window. No high-impact action confirmation or rollback exists |
| Interrupted execution | Durable WAL history marks active runs interrupted and does not replay them | An external side effect may have occurred immediately before termination; inspect destination systems manually |
| Malicious prompt or model output | Ollama is local/optional; prompt treats embedded instructions as untrusted; drafts are validated and require review | Validation checks workflow structure, not whether a generated automation is safe or correct |

## Verification performed

Automated tests cover project path escape, package traversal including Windows separators, private/loopback network blocking, keyring backend rejection, secret redaction, run-history restart recovery, migration backup, and deterministic package export. Browser DNS is checked before navigation and on routed requests, but the Chromium socket is not pinned; DNS rebinding remains a documented gap. No independent penetration test has been performed.
