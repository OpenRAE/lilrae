# Managed OpenCode participants

OpenCode is an explicit implementation choice for each autonomous participant.
It uses the shared RAES runtime and the same admitted MCP action boundary.
It does not replace the browser workbench agent.

## Install

Install LilRAE with Python 3.14 using the [package installation instructions](../getting-started/installation.md).
Install OpenCode before starting a trial:

```shell
bash tools/install-opencode.sh "$HOME/.local/lib/lilrae-opencode-1.19.5"
"$HOME/.local/lib/lilrae-opencode-1.19.5/opencode" --version
```

The helper above is for a source checkout.
It downloads the official Linux x86_64 baseline archive and verifies both archive and executable SHA-256 digests.
The executor repeats the executable digest check before every invocation.
No trial downloads an executable or updates OpenCode.

A wheel installation does not require the checkout or that helper.
Download `opencode-linux-x64-baseline.tar.gz` from the [official 1.19.5 release](https://github.com/anomalyco/opencode/releases/tag/v1.19.5).
Verify archive SHA-256 `17c200fd4b2289954cc01552559f9b6d03ec157b2ddfb5eb54144f491656333d` before extraction.
Install its `opencode` executable in an operator-owned directory and verify the executable digest below.
Pass that absolute path to `OpenCodeOptions.executable`.

| Identity | Supported value |
| --- | --- |
| Python | 3.14 |
| RAES | At least 10.2.0, below 10.4 |
| OpenCode | 1.19.5, Linux x86_64 baseline build |
| Executable SHA-256 | `7df4e4136301f16589b0f30bf91a61380fca5f8ef22dd36570f5ebe1d4ec802c` |
| Adapter manifest | `lilrae-opencode`, independently versioned by its publisher |
| Gateway | Explicit `https://openrouter.ai/api/v1` |
| Serving route | One operator-approved serving provider; fallbacks disabled |

Alternate builds require an explicit `OpenCodeBuild` and separate qualification.
The installed manifest commits its build version and executable digest.
An endpoint on HTTP loopback is supported for fake-provider transport tests only.
Other gateway destinations are refused.

## Configure and invoke

The project selects a model and a credential source without storing a secret:

```json
{
  "experiment": {
    "participant_models": {"opencode": "openrouter/approved-vendor/approved-model"},
    "participant_credential_sources": {
      "opencode": {"kind": "process-environment", "variable": "APPROVED_MODEL_CREDENTIAL"}
    }
  }
}
```

Replace the example model with an approved selection.
The experiment repository owns model catalogs, prompt assets, and scientific request settings.
Supply the selected credential through the approved environment source.
Never put it in a command argument, prompt, or project JSON file.

The experiment's trusted entry assembly performs these steps for each participant address:

1. Create `opencode_manifest(version=...)` from `aptl.backends.lilrae_participant_configuration`.
2. Realize the seven manifest targets through RAES `realize_participant_configuration()`.
3. Resolve the prompt through the experiment's admitted artifact owner.
4. Enter `managed_opencode_executor()` from `aptl.workbench.opencode_bootstrap`.
5. Bind the executor and its configuration digest through `LilraeParticipantBinding`.
6. Admit the bindings through `ScenarioAdmissionSource.autonomous_bindings`.
7. Execute with `run_participant_workload()` and the existing experiment evaluator.
8. Cancel and drain the runtime before leaving the managed executor context.

| Target | Meaning |
| --- | --- |
| `model` | Full `openrouter/vendor/model` request identity from the admitted model domain |
| `gateway_endpoint` | Explicit approved gateway base URL |
| `serving_provider` | Exclusive OpenRouter serving-provider identifier |
| `prompt_ref` | Admitted prompt artifact reference |
| `prompt_sha256` | SHA-256 of the exact UTF-8 prompt supplied on stdin |
| `timeout_seconds` | Integer invocation deadline, from 1 through 3600 seconds |
| `max_output_tokens` | Integer request output limit, from 1 through 32768 tokens |

The factory requires `options`, `configuration`, `manifest`, `prompt`, `prompt_ref`, and `supported_models`.
It also requires `run_id`, `credential_source`, and the explicitly supplied `source_environment` mapping.
`OpenCodeOptions` declares the absolute executable, private work root, pinned build, route, and optional verified tool profile.
Its `environment` must remain empty when using the managed factory.
The default direct-launch token cap is 128; an admitted trial must declare its cap explicitly.
The fixed session title prevents OpenCode from making an extra model request to generate a title.
The credential source variable may have a different name from OpenRouter's native environment variable.
The factory maps only the selected value to `OPENROUTER_API_KEY`.
It does not search `.env` files or infer a credential source.
No worktree or repository-local `.env` is required.
The project's `aptl.json` contains the model and credential-variable reference, never the key value.
The approved launcher supplies that variable to its process before calling the installed factory.
It can obtain the value from the deployment's existing credential mechanism.
Pass the project configuration's `source_for("opencode")` and `model_for("opencode")` selections to the assembly.
Use an operator-owned work directory outside the checkout for `OpenCodeOptions.work_root`.
The factory obtains the credential through the existing resolver and ephemeral broker.
The context yields `(executor, credential_evidence)` and clears local credential references on exit.
Select each participant independently; role names do not select a model or implementation.

`OpenCodeConfigurationValidator` accepts an operator-supplied model domain.
Unsupported request-control targets are refused, rather than ignored.
The registry is the extension boundary for model/request controls and pinned control-context work.
The prompt commitment proves stdin delivery; it does not describe OpenCode's entire effective model request.

## Evidence and limits

Supply `OpenCodeOptions.evidence_sink` to retain each `OpenCodeInvocationEvidence` in the trial's existing evidence owner.
The executor also retains `last_evidence` for inspection.
Records contain build and requested route identities, prompt commitment, status, partial text commitment, available usage, and cleanup residue.
Records contain no raw prompts, completions, credentials, stderr, or provider error bodies.
The CLI does not attest the served model or serving provider; those fields remain unavailable.
OpenCode 1.19.5 has internal transient-error retries without a supported per-invocation disable control.
The process deadline bounds their lifetime; this adapter does not add retries or paid fallback routes.
Text alone is not completion: a successful terminal event and successful supervised process exit are both required.
Provider errors, malformed events, timeout, and cancellation retain safe partial metadata.
Timeout and cancellation retain a commitment to the captured response bytes, without storing those bytes.
Evidence persistence or private-directory cleanup failure cannot produce a successful invocation record.
Tool-transport teardown is also inside this outcome boundary.
Its cleanup field distinguishes successful closure from uncertainty after a transport failure.

Fresh HOME, XDG directories, and working directories prevent session reuse.
The adapter rejects system-managed OpenCode configuration under `/etc/opencode`.
Built-in tools are denied; only the exact verified MCP inventory is admitted.
MCP children receive invocation-scoped authority and no usable model credential.
Process groups supervise local cleanup; they are not an operating-system sandbox.
They do not prove termination of escaped descendants or remote work.
The existing process and credential protection work retains responsibility for stronger containment.

The candidate is covered by targeted tests, real launcher/fake-provider tests, and installed-wheel success and failure tests.
Installed qualification also exercises both roles through RAES and real MCP action transport.
It verifies admitted dispatch, refused arguments, built-in shell denial, and isolation from hostile ambient configuration.
Native effects use deterministic local counters; no actual lab or external model is needed for these tests.
Issue #1504 ends at PR merge after testing and review.
Its approved live GCP check is a bounded free-model connectivity and invocation-trigger smoke.
The observed smoke returned usage metadata at a reported cost of zero within the configured invocation bounds.
It did not produce a text completion or qualify the experiment's model route.
Release publication and full scientific control qualification are downstream work.
The [qualification record](../testing/opencode-1504-qualification.md) gives the candidate, project identity, observations, and cleanup evidence.
See the [design](../architecture/managed-opencode.md) and [shared runtime](../architecture/concurrent-participant-execution.md).
