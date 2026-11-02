# OpenCode candidate qualification for issue #1504

## Boundary

Issue #1504 ends at PR merge after candidate testing and review.
Release publication and scientific control qualification are downstream work.
The operator approved actual Docker lab tests only on the issue-owned GCP VM.
The operator limited live model use to a frugal connectivity and invocation-trigger smoke.

## Installed candidate and GCP identity

The [retained evidence bundle](evidence/1504/README.md) includes the original smoke output and runner,
the tested wheel's identity, reconstructed route settings, public price recheck, and GCP audit records.
It states the limits of those records explicitly.

| Item | Observed identity |
| --- | --- |
| Date | 2026-11-02 |
| Approved GCP project | `prod-mgau4w` |
| Issue-owned VM | `test-1504` |
| Zone | `us-central1-a` |
| Network and subnet | `test-1504`, created for this issue |
| VM service account | None |
| SSH access | IAP source range only |
| Private-address egress | Denied by the issue-owned firewall rule |
| LilRAE candidate distribution | `lilrae` 8.2.0 wheel, installed outside the checkout |
| Smoke wheel SHA-256 | `fa6a9c61230f26ff6a9dbf825e3fc60ec5669fe9b1e2d9c3a6a9228f9b657847` |
| OpenCode | 1.19.5, Linux x86_64 baseline build |
| OpenCode executable SHA-256 | `7df4e4136301f16589b0f30bf91a61380fca5f8ef22dd36570f5ebe1d4ec802c` |
| RAES | 10.2.0 |
| Python in the VM | 3.14.10 |

The test used its own network and no existing tenant resources.
It did not reuse or modify the BigRAE tenant.

## Docker lifecycle

The installed CLI materialized a fresh lab project.
It started the product-neutral `materialization-envelope` scenario through the public lab-start path.
The result reported `ok: true` and `outcome: ready`.
The generated smoke container was running.
The public lab-stop path removed the deployment and volumes and reported `ok: true`.

The final candidate is also tested through installed-wheel automation.
Later failure-metadata changes are verified by the offline installed tests below.
This lifecycle result is not a scientific experiment result.

## Bounded live trigger smoke

The credential loader selected the approved value opaquely.
It sent only that selected value over SSH stdin to the installed process.
No credential value appeared in command arguments, public evidence, or model prompts.
The runtime used the existing configured-source resolver and ephemeral broker.

| Item | Observation |
| --- | --- |
| Approved process invocations | One |
| Requested model | `openrouter/liquid/lfm-2.5-2.6b:free` |
| Gateway | `https://openrouter.ai/api/v1` |
| Requested serving endpoint | `liquid/fp8` |
| Price checked before invocation | Public catalog and endpoint listed zero prompt and completion prices |
| Fallbacks | Disabled; selected model and serving endpoint only |
| Output cap | 16 tokens |
| Process deadline | 10 seconds |
| Captured stdout | 621 bytes |
| Available input usage | 1981 tokens |
| Available output usage | 0 tokens |
| Reported cost | 0 |
| Completion | No text completion |
| Process result | Supervised failure; exact failure reason was not retained in the smoke summary |
| Cleanup residue | None observed |
| Local credential cleanup | Succeeded |
| Served model/provider attestation | Unavailable; not inferred from the requested route |

This evidence proves bounded provider invocation and available usage reporting.
It does not establish a completed answer, scientific trial, or experiment-model qualification.
The pinned CLI can retry transient failures internally; the live HTTP request count was not observed.
No further live model invocation was made.

## Offline installed verification

`tests/test_opencode_transport.py` installs the candidate wheel outside the checkout.
It reads the model and credential reference from a separate project's configuration.
It uses the real pinned launcher against a local fake provider for success and authentication failure.
The emitted requests enforce the exact model, route, output cap, and fallback denial.
The fixed session title prevents the auxiliary title-generation request.

`tests/test_opencode_installed_actions.py` uses the installed package, real RAES scheduler, pinned launcher, MCP SDK, and common admission carrier.
Deterministic native counters prove authorized effects for both roles.
Negative cases cover unapproved arguments and built-in host-shell attempts.
Hostile parent configuration, plugins, saved credentials, and history use local canaries.
Failure cases cover timeout, in-flight cancellation, malformed provider output, and private-context teardown failure.
Transport teardown faults follow both a successful model response and a supervised timeout.
They retain failed evidence, report uncertain transport cleanup, and retain the process cleanup result.
The runtime retains an indeterminate operation for incomplete cleanup proof.
Timeout and cancellation combined with directory cleanup failure retain captured-output counts, stdout commitments, and process cleanup proof.
An output fault injects a failed terminal event before the real launcher's stop event.
The parser rejects that sequence and retains the failed finish and safe partial evidence.
A fresh subsequent trial verifies clean sessions and successful admitted effects after each failure case.
Available partial session and usage facts are retained without exposing raw provider output.

These tests require no actual Docker lab or external model.
Full suites, all MCP consumers, and coverage remain CI/CD checks.

## Cleanup

The issue-owned VM and its boot disk were deleted after the smoke.
The two issue-owned firewall rules, subnet, and network were deleted.
Subsequent project queries returned no matching VM, disk, network, or firewall rules.
Pre-existing project and tenant resources were not cleanup targets.
