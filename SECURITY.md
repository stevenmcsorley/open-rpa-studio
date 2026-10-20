# Security policy

This is an early-stage local automation application, not yet suitable for unattended production workloads or sensitive data. Security controls are defense-in-depth measures and have not received an independent audit.

## Reporting

Report suspected vulnerabilities privately to the repository owner. Include the affected version, operating system, reproduction steps, and impact. Do not include real credentials or sensitive automation data in reports.

## Implemented controls

- Workflow expressions use a restricted AST interpreter; arbitrary Python, shell and JavaScript activities are not supported.
- Regex work uses a timeout-capable engine with input/pattern limits, and run-time, activity, loop and log quotas cap execution growth.
- Project and workflow paths are confined to the project root after canonical path resolution. Imported project files are bounded and schema-validated.
- `.orpa` imports reject duplicate entries, traversal (including Windows separators), symlinks, invalid hashes, oversized files, oversized archives, and excessive compression ratios. SHA-256 proves integrity only; packages are unsigned and publisher identity is not authenticated.
- Network and desktop interaction require explicit per-run permission. HTTP is restricted to public DNS results, pinned to a validated address, standard ports, bounded timeouts and response sizes, and does not follow redirects. DNS resolution itself uses the OS resolver and has no independently enforced resolver timeout.
- Browser requests are checked against public-address policy including redirects. Chromium performs the actual DNS lookup, so a DNS-rebinding time-of-check/time-of-use race remains.
- Credentials are fetched from recognized OS credential stores only. Plaintext/file keyring backends are rejected. Secrets are redacted from normal logs, returned variables, activity states and saved run results. A workflow can still deliberately send a credential to an allowed public endpoint or type it into the focused desktop application.
- Local AI is optional. Generated drafts are bounded, checked against the activity validator, and require user review before insertion. There is no arbitrary custom-code activity.
- Desktop run history is local, write-ahead logged, capped, and stores a workflow digest plus activity/audit events. Interrupted workflows are not resumed or replayed automatically.

## Threat model and residual risks

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md). In particular, this application does not sandbox the Python process or Chromium, does not sign packages, has no plugin system, and does not prevent an authorized workflow from making harmful changes inside its granted capabilities. Coordinate-based desktop automation can affect whichever application has focus. Review workflows and grants before execution.
