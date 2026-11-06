# Managed OpenCode participants

OpenCode is an explicit implementation choice for each autonomous participant.
It uses the shared RAES runtime and the same admitted MCP action boundary.
It does not replace the browser workbench agent.

The [participant request manifest API](participant-request-manifests.md) publishes typed model, request-profile and exact context selections for experiment admission.

## Install

See [Install and configure managed OpenCode](opencode-operations.md#install).

## Configure and invoke

See [Install and configure managed OpenCode](opencode-operations.md#configure-and-invoke).

## Evidence and limits

`OpenCodeOptions.evidence_sink` keeps each `OpenCodeInvocationEvidence` through the trial's given evidence owner.
The executor also keeps `last_evidence` for inspection.
Records contain build and requested route identities, prompt commitment, status, partial text commitment, available usage, and cleanup residue.
Records contain no raw prompts, completions, credentials, stderr, or provider error bodies.

The CLI does not attest the served model or serving provider. Those fields remain unavailable.
OpenCode 1.19.5 has internal transient-error retries without a supported per-invocation disable control.
The process deadline bounds their lifetime. This adapter does not add retries or paid fallback routes.
Text alone is not completion: a successful terminal event and successful supervised process exit are both required.

Provider errors, malformed events, timeout, and cancellation keep safe partial metadata.
Timeout and cancellation keep a commitment to the captured response bytes. They do not store those bytes.
Evidence persistence or private-directory cleanup failure cannot produce a successful invocation record.
Tool-transport teardown is also inside this outcome boundary.

Its cleanup field distinguishes successful closure from uncertainty after a transport failure.

Fresh HOME, XDG directories, and working directories prevent session reuse.
The adapter rejects system-managed OpenCode configuration under `/etc/opencode`.
The adapter denies built-in tools. It admits only the exact verified MCP inventory.
MCP children receive invocation-scoped authority and no usable model credential.

Process groups supervise local cleanup. They are not an operating-system sandbox.
They do not prove termination of escaped descendants or remote work.
Stronger containment remains the responsibility of the existing process and credential protection work.

Targeted tests, real launcher/fake-provider tests, and installed-wheel success and failure tests cover the candidate.
Installed qualification also exercises both roles through RAES and real MCP action transport.
It verifies admitted dispatch, refused arguments, built-in shell denial, and isolation from hostile ambient configuration.
Native effects use deterministic local counters. No actual lab or external model is needed for these tests.

Issue #1504 ends at PR merge after testing and review.
Its approved live GCP check is a bounded free-model connectivity and invocation-trigger smoke.
The observed smoke returned usage metadata at a reported cost of zero within the configured invocation bounds.
It did not produce a text completion or qualify the experiment's model route.

Release publication and full scientific control qualification are downstream work.
The [qualification record](../testing/opencode-1504-qualification.md) gives the candidate, project identity, observations, and cleanup evidence.
See the [design](../architecture/managed-opencode.md) and [shared runtime](../architecture/concurrent-participant-execution.md).

## Supported build and route

| Identity | Supported value |
| --- | --- |
| Python | 3.14 |
| RAES | At least 10.7.0, below 11 |
| OpenCode | 1.19.5, Linux x86_64 baseline build |
| Archive SHA-256 | `17c200fd4b2289954cc01552559f9b6d03ec157b2ddfb5eb54144f491656333d` |
| Executable SHA-256 | `7df4e4136301f16589b0f30bf91a61380fca5f8ef22dd36570f5ebe1d4ec802c` |
| Adapter manifest | `lilrae-opencode`, independently versioned by its publisher |
| Gateway | Explicit `https://openrouter.ai/api/v1` |
| Serving route | The route uses one operator-approved serving provider. Fallbacks are disabled |

Alternate builds must have an explicit `OpenCodeBuild` and separate qualification.
The installed manifest commits its build version and executable digest.
An endpoint on HTTP loopback is supported for fake-provider transport tests only.
The adapter refuses other gateway destinations.

## Configuration targets

| Target | Meaning |
| --- | --- |
| `model` | Full `openrouter/vendor/model` request identity from the admitted model domain |
| `gateway_endpoint` | Explicit approved gateway base URL |
| `serving_provider` | Exclusive OpenRouter serving-provider identifier |
| `prompt_ref` | Admitted prompt artifact reference |
| `prompt_sha256` | SHA-256 of the exact UTF-8 prompt given on stdin |
| `timeout_seconds` | Integer invocation deadline, from 1 through 3600 seconds |
| `max_output_tokens` | Integer request output limit, from 1 through 32768 tokens |

## Factory contract

The factory must have `options`, `configuration`, `manifest`, `prompt`, `prompt_ref`, and `supported_models`.
It must also have `run_id`, `credential_source`, and the explicitly given `source_environment` mapping.
`OpenCodeOptions` declares the absolute executable, private work root, pinned build, route, and optional verified tool profile.
Its `environment` must remain empty for the managed factory.

The default direct-launch token cap is 128. An admitted trial must declare its cap explicitly.
The fixed session title prevents an extra OpenCode model request for title generation.
The credential source variable may have a different name from OpenRouter's native environment variable.
The factory maps only the selected value to `OPENROUTER_API_KEY`.

It does not search `.env` files or infer a credential source.
No worktree or repository-local `.env` is required.
The project's `aptl.json` contains the model and credential-variable reference, never the key value.
The approved launcher gives that variable to its process before it calls the installed factory.

It can get the value from the deployment's existing credential mechanism.
Assembly gives the configured `source_for("opencode")` and `model_for("opencode")` selections.
`OpenCodeOptions.work_root` must be operator-owned and outside the checkout.
The factory gets the credential through the existing resolver and ephemeral broker.

The context yields `(executor, credential_evidence)` and clears local credential references on exit.
Participant selections are independent. Role names do not select a model or implementation.

`OpenCodeConfigurationValidator` accepts an operator-supplied model domain.
The validator refuses unsupported request-control targets. It does not ignore them.
The registry is the extension boundary for model/request controls and pinned control-context work.
The prompt commitment proves stdin delivery. It does not describe OpenCode's entire effective model request.

## Installation verification

The checkout helper downloads the official Linux x86_64 baseline archive.
It verifies both archive and executable SHA-256 digests.
The executor repeats executable verification before every invocation.
Trials do not download or update OpenCode.

A wheel installation can use the verified executable without this checkout helper.
`OpenCodeOptions.executable` requires its absolute path.
The experiment repository owns approved model catalogs, prompt assets, and scientific request settings.
