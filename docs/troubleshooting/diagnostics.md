# Recovery Diagnostic Reference

Use [Recover a lab](index.md) for the operating procedure.
These fields describe failures; they do not establish that a running container is ready.

## Host Cleanup Reasons

| Reason | Meaning | Required action |
| --- | --- | --- |
| `provider-reset-authority-unavailable` | No installed adapter supports the recorded pack cleanup | Install an adapter supporting that version and digest |
| `provider-reset-authority-ambiguous` | Multiple adapters claim cleanup | Remove the duplicate installation |
| `provider-hook-failed` | The cleanup handler failed | Inspect the log and retry |
| `host-state-unsafe` | Cleanup found a symlink or non-file | Inspect the exact path before manual repair |
| `cleanup-record-malformed` | The cleanup record cannot be read | Upgrade if needed, or report the record name |
| `cleanup-action-unsupported` | The installed release cannot handle the recorded action | Upgrade to a release supporting that action |

The lifecycle record is an audit trail under `.aptl/lifecycle/`.
Docker teardown failure preserves host state that still describes retained volumes.
Pending host cleanup means teardown completed but a named action remains.

## Wazuh Readiness

| Phase | Diagnostic | Meaning |
| --- | --- | --- |
| `transport` | `tls_handshake`, curl exit 35 | No completed TLS session |
| `transport` | `connection_reset` | Connection closed before an HTTP response |
| `authentication` | `credentials_rejected`, HTTP 401 or 403 | The service rejected configured credentials |
| `manager_status` | Authenticated API without running daemons | Manager workload is not ready |

Published-port transport failures can occur before the container API starts listening.
They do not alone establish a certificate defect.
Realized Wazuh artifact readiness uses a 300-second authenticated budget.
The compatibility service checks can report a 120-second budget.
The diagnostic names the actual endpoint, phase, reason, and safe inspection command.
It excludes credentials, tokens, and response bodies.
