# Containment interface

Reader purpose: Reference.
This page describes version 1 of the shared containment interface.
[ADR-068](../adrs/adr-068-shared-containment-wrapper.md) records the decision.
The [architecture](../architecture/containment-wrapper.md) explains the components and threats.

## Command

```shell
lilrae containment run --state-root DIR [--engine-root DIR] < request.json > report.json
```

| Option | Meaning |
| --- | --- |
| `--state-root DIR` | Required. An existing directory that only the current user can write. It holds the read-only engine snapshot under `engine/` and one private subdirectory for each run. |
| `--engine-root DIR` | Optional. The engine checkout. The default is the `third_party/raptor` submodule of a source checkout. |

The command reads one request document from standard input.
The request can have at most 16 MiB.
The command writes one report document to standard output and exits with status 0.
An invalid request or option writes a message to standard error and exits with status 2.

The Python interface is `aptl.containment.RaptorContainmentAdapter.execute(request, *, cancel_event=None)`.
It returns the same report model.

## Request

Schema: `lilrae.containment.request/v1`. Unknown fields and duplicate keys are refused.

| Field | Type | Constraint |
| --- | --- | --- |
| `schema_version` | string | `lilrae.containment.request/v1` |
| `profile` | string | `linux-full` |
| `label` | string | 1 to 64 characters: lowercase letters, digits, `.`, `_`, and `-`. The first character is a letter or digit. |
| `argv` | list of strings | 1 to 256 items. The first item is an absolute path. Each item has 1 to 4096 characters and no NUL character. |
| `env` | object | At most 64 entries. Names match `[A-Za-z_][A-Za-z0-9_]{0,127}`. Values have at most 8192 characters and no NUL character. |
| `stdin` | string | Base64. At most 8 MiB after decoding. |
| `input_dir` | string or null | An absolute path to an existing directory. The target can read it but not write it. |
| `limits.deadline_seconds` | number | Greater than 0 and at most 3600. |
| `limits.max_output_bytes` | integer | 1 to 16777216. The bound applies to standard output and standard error together. |
| `limits.cpu_seconds` | integer or null | 1 to 86400. The engine sets `RLIMIT_CPU`. |
| `limits.max_file_mb` | integer or null | 1 to 1048576. The engine sets `RLIMIT_FSIZE`. |
| `limits.address_space_mb` | integer or null | 1 to 1048576. The engine sets `RLIMIT_AS`. This is not a memory bound. |
| `network` | string | `none` |

The target starts in the run's output directory.
The target environment contains `PATH=/usr/bin:/bin`, `LANG=C.UTF-8`, and the `env` entries.
The worker refuses an `env` name that the engine classifies as dangerous.
The engine then replaces `HOME` and the XDG home variables with an empty directory in the output directory.

## Report

Schema: `lilrae.containment.report/v1`.

| Field | Meaning |
| --- | --- |
| `run_id` | 32 hexadecimal characters. |
| `label` | The request label. |
| `status` | `completed`, `refused`, `timed_out`, `cancelled`, `output_limit_exceeded`, or `worker_failed`. |
| `failure_origin` | `none`, `setup`, `target`, or `supervisor`. |
| `reason` | A stable reason code, or null. |
| `detail` | At most 512 characters, or null. It never repeats request values. |
| `contained` | True only when the worker delivered every required property. |
| `properties` | One entry for each required property: `property`, `state`, and `basis`. |
| `target` | Null when the target did not start. Otherwise the exit code, signal, output, byte counts, and truncation flag. |
| `engine` | Repository, commit, source digest, and the containment tier that the engine reported. |
| `host` | The kernel release. |
| `bounds` | The applied deadline, output bounds, and resource limits, and `peak_memory: not-enforced`. |
| `cleanup` | The runner's cleanup observation for the worker process group, or null. |
| `run_dir` | The private run directory, or null when the run refused before it made one. The `output` subdirectory holds target files. `engine.log` holds engine diagnostics. |

The consumer owns `run_dir` after the run and removes it.
Treat a report with `contained: false` as a containment failure.
Treat target output and files as untrusted data.

### Properties

| Property | Meaning | Check before the target starts |
| --- | --- | --- |
| `namespaces` | User, PID, IPC, network, and mount namespaces with a fresh procfs. | Engine mount, network, and PID-namespace supervision probes. |
| `filesystem_policy` | Landlock filesystem restriction with a read allowlist. | Engine Landlock probe. |
| `syscall_socket_filter` | The engine seccomp-bpf filter, which includes socket family rules. | Engine seccomp probe. |
| `descriptor_environment_hygiene` | No inherited descriptors and an explicit environment. | Environment names pass the engine classifier. |
| `supervision` | The PID namespace ends every descendant with the run. | Engine spawn-backend and PID-namespace supervision probes. |

A property state is `delivered`, `refused`, or `unknown`.
After the run, the worker compares the engine's posture record with the profile.
A difference sets the state to `unknown` and `contained` to false.
A timeout gives no posture record, so the same downgrade applies.

### Reason codes

| Code | Status |
| --- | --- |
| `engine_unavailable` | `refused` |
| `engine_unverified` | `refused` |
| `input_unavailable` | `refused` |
| `property_unavailable` | `refused` |
| `environment_name_denied` | `refused` |
| `engine_setup_failed` | `refused` |
| `deadline_exceeded` | `timed_out` |
| `output_limit_exceeded` | `output_limit_exceeded` |
| `cancelled` | `cancelled` |
| `worker_report_invalid` | `worker_failed` |
| `worker_process_failed` | `worker_failed` |
| `containment_unconfirmed` | `completed` |

## Escape-probe protocol

A probe tests one denied operation for one property.
The probe payload prints two marker lines on standard output:

```text
LILRAE-PROBE reached <probe-id>
LILRAE-PROBE result <probe-id> <denied|allowed> <detail>
```

The first line proves that the payload reached the operation.
The harness can supply the result from an independent observation instead.

| Control result | Contained run | Verdict |
| --- | --- | --- |
| `allowed` | reached and `denied` | `contained` |
| `allowed` | reached and `allowed` | `escaped` |
| `allowed` | not reached | `not_reached` |
| `allowed` | reached and no result | `inconclusive` |
| `denied` or absent | any | `control_failed` |

The control is the same payload without containment, in the same environment.
Only `contained` passes. A refused run is not a passed probe.

## Adapter obligations

Another local or remote worker adapter must supply these items:

1. Accept the version 1 request and return the version 1 report.
2. Give a setup channel that is separate from target output and exit status.
3. Give native evidence for each required property, or the state `unknown`.
4. Refuse before the target starts, and before payload delivery, when a property is not delivered.
5. Enforce the deadline, cancellation, and the aggregate output bound.
6. State its memory, process, and storage bounds exactly.
7. Clean up every owned process and report what it could not confirm.
8. Run the shared probes with an unsandboxed control in the same environment.
9. Report its pinned engine or native identity.

A simulated adapter can test orchestration only.
Its probe results are not evidence of a native boundary.
