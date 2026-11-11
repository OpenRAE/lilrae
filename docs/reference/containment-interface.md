# Containment interface

Reader purpose: Reference.
This page describes version 1 of the shared containment interface.
[ADR-068](../adrs/adr-068-shared-containment-wrapper.md) records the decision.
The [architecture](../architecture/containment-wrapper.md) explains the components and threats.

## Command

```shell
lilrae containment run --state-root DIR < request.json > report.json
```

| Option | Meaning |
| --- | --- |
| `--state-root DIR` | Required. An existing directory that only the current user can write. Each run creates a private subdirectory here. |

The supported host provides Bubblewrap 0.8 or later at `/usr/bin/bwrap`, libseccomp 2.5 or later, Landlock, and `/usr/bin/python3`.

The command reads one request document from standard input.
The request can have at most 16 MiB.
The command writes one report document to standard output and exits with status 0.
An invalid request or option writes a message to standard error and exits with status 2.

The Python interface is `aptl.containment.BubblewrapContainmentAdapter.execute(request, *, cancel_event=None)`.
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
The target environment contains `PATH=/usr/bin:/bin`, `LANG=C.UTF-8`, `HOME=/tmp/home`, and the `env` entries.
The adapter refuses an `env` name that loads code, changes configuration, or sets a proxy.

The target sees the host system directories read-only, public TLS certificates, a private `/tmp`, a fresh `/proc` and `/dev`, the input directory, and its output directory.
The input directory is mounted read-only at `/run/lilrae/input`, outside every writable grant. Its host path is a symbolic link to that mount.
The target cannot create Unix sockets or datagram socket pairs, so a host socket in a granted directory is not reachable.
The datagram deny also covers `SOCK_RAW`, because `AF_UNIX` accepts it as a datagram type. Stream `socketpair` stays available.

## Report

Schema: `lilrae.containment.report/v1`.

| Field | Meaning |
| --- | --- |
| `run_id` | 32 hexadecimal characters. |
| `label` | The request label. |
| `status` | `completed`, `refused`, `timed_out`, `cancelled`, `output_limit_exceeded`, or `supervisor_failed`. |
| `failure_origin` | `none`, `setup`, `target`, or `supervisor`. |
| `reason` | A stable reason code, or null. |
| `detail` | At most 512 characters, or null. It never repeats request values. |
| `contained` | True only when the target started and the run's own status confirmed every required property. |
| `properties` | One entry for each required property: `property`, `state`, and `basis`. |
| `target` | Null when the target did not start. Otherwise the exit code, output, captured byte counts, and truncation flag. The exit code uses shell encoding: 128 + n can mean signal n. After a stop, the output is withheld and only the byte counts remain. |
| `engine` | `implementation` (`lilrae.containment.bubblewrap/v1`), the Bubblewrap version, the Landlock ABI, and the libseccomp version. |
| `host` | The kernel release. |
| `bounds` | The applied deadline, combined output bound, and resource limits, and `peak_memory: not-enforced`. One deadline covers the host checks, the setup, and the target. |
| `cleanup` | The runner's cleanup observation for the Bubblewrap process group, or null. |
| `run_dir` | The private run directory, or null when the run refused before it made one. The `output` subdirectory holds target files. `policy.json` holds the launcher policy. |

If Bubblewrap reports no target exit after the target starts, the status is `supervisor_failed` and the origin is `supervisor`.
Then `target` is null, and `detail` gives the runner's exit status.

The consumer owns `run_dir` after the run and removes it.
Treat a report with `contained: false` as a containment failure.
Treat target output and files as untrusted data.

### Properties

| Property | Meaning | Host check before the run | Evidence after the run |
| --- | --- | --- | --- |
| `namespaces` | User, PID, mount, network, IPC, UTS, and cgroup namespaces with a fresh procfs. | Bubblewrap version and a namespace probe. | Bubblewrap status names the PID, mount, network, IPC, and UTS namespaces. |
| `filesystem_policy` | Landlock filesystem and TCP restriction. | Kernel Landlock ABI. | Launcher `landlock` status. |
| `syscall_socket_filter` | `no_new_privs` and the seccomp filter, with socket family, `AF_UNIX`, and ioctl rules. | libseccomp version. | Launcher `no_new_privs` and `seccomp` status. |
| `descriptor_environment_hygiene` | No inherited descriptors and an explicit environment. | Launcher interpreter and environment names. | Launcher `descriptors` status. |
| `supervision` | New session, PID 1 reaper, `--die-with-parent`, and resource limits. | Bubblewrap namespace probe. | Launcher `limits` status, a Bubblewrap child, and a cleanup with no residue. |

A property state is `delivered`, `refused`, or `unknown`.
A failed host check or a failed launcher layer sets `refused`.
Missing evidence after the run sets `unknown`.

### Reason codes

| Code | Status |
| --- | --- |
| `property_unavailable` | `refused` |
| `environment_name_denied` | `refused` |
| `input_unavailable` | `refused` |
| `engine_setup_failed` | `refused` |
| `deadline_exceeded` | `timed_out` |
| `output_limit_exceeded` | `output_limit_exceeded` |
| `cancelled` | `cancelled` |
| `cleanup_unconfirmed` | `supervisor_failed` |
| `supervisor_failed` | `supervisor_failed` |
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
