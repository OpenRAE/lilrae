# ADR-069: Shared Containment Wrapper

## Status

accepted

## Date

2026-11-10

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [interface Reference](../reference/containment-interface.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

Managed provider and MCP processes run with the operator's OS authority ([ADR-057](adr-057-agent-execution-compartments.md)).
Each backend must not discover the same namespace, filesystem, syscall, descriptor, socket, and lifetime bypasses again.
A namespace launcher alone does not give a composed boundary.

[Issue #1467](https://github.com/OpenRAE/lilrae/issues/1467) first selected a maintained fork of the RAPTOR sandbox engine.
On 2026-11-10 the maintainer replaced that direction with an in-house engine.
LilRAE repeatedly mines RAPTOR's advances for things to add to its own engine.
The [architecture](../architecture/containment-wrapper.md) gives the components, data flows, threats, and controls.

## Decision

### Engine

1. LilRAE has no RAPTOR submodule, fork, or runtime import.
2. Bubblewrap supplies the user, PID, mount, network, IPC, UTS, and cgroup namespaces, the fresh procfs, and the mount view.
3. Bubblewrap also supplies the new session, the PID 1 reaper, `--die-with-parent`, `--disable-userns`, and the JSON status channel.
4. A LilRAE launcher runs inside the sandbox before the target. It closes inherited descriptors and sets `no_new_privs` and resource limits.
5. The launcher then applies Landlock and a seccomp filter through libseccomp. Then it executes the target.
6. The seccomp filter denies `AF_UNIX` sockets and datagram socket pairs, including the `SOCK_RAW` type. A read-only bind does not stop a connect to a host socket in a granted directory.
7. The input mounts at `/run/lilrae/input`, outside every writable grant. A Landlock grant on a writable ancestor would also cover the input.
8. The launcher uses only the Python standard library and runs under the host's `/usr/bin/python3`.

### Wrapper

1. The wrapper is the `aptl.containment` adapter. The versioned interface is the `aptl.core.containment` core package.
2. Python consumers use the adapter. Other languages use the `lilrae containment run` command over standard input and output.
3. Each run has its own Bubblewrap process and launcher. No engine state outlives a run or is shared between runs.
4. The existing `BoundedProcessRunner` starts Bubblewrap. Entry code injects it through a core Protocol.
5. The wrapper adds no network service and no second scenario runtime.

### Interface

1. The request and report schemas carry the version names `lilrae.containment.request/v1` and `lilrae.containment.report/v1`.
2. Version 1 has one profile, `linux-full`. It requires five properties.
3. The properties are namespaces with a fresh procfs, filesystem policy, syscall and socket filter, descriptor and environment hygiene, and supervision.
4. The adapter checks each property on the host separately before the run. One check never replaces another.
5. An unknown or failed property refuses the run before the target starts and before payload delivery.
6. After the run, the Bubblewrap status and the launcher status must confirm each property. Otherwise the report does not claim containment.
7. Version 1 has no network access and no credential channel. Issues #1455 and #1458 own those seams.

### Failure reporting and bounds

1. The launcher reports each layer on a status descriptor. The descriptor closes when the target executes, so the target cannot write to it.
2. Bubblewrap reports the namespaces and the target exit on its JSON status descriptor.
3. The report separates setup refusal, target failure, and supervisor failure. A target exit status cannot imitate a setup result.
4. One deadline covers the host checks, the setup, and the target. The runner also enforces the combined output bound and cancellation.
5. The report states that version 1 does not enforce a peak-memory bound. Issue #1457 owns aggregate resource budgets.
6. An address-space limit is reported as an address-space limit, never as a memory bound.

### Concurrent runs

1. Each run gets a new private directory under a backend-owned state root.
2. The target's only writable grants are the output directory of its own run and a private `/tmp`.
3. Each run has its own Bubblewrap process, process group, status descriptors, and cancellation event.

### Ownership and distribution

1. LilRAE owns the engine, the interface, and the conformance proof.
2. Consumers own their admitted authority.
3. Another worker adapter must supply the obligations in the [interface Reference](../reference/containment-interface.md#adapter-obligations).
4. The supported host provides Bubblewrap 0.8 or later, libseccomp 2.5 or later, Landlock, and `/usr/bin/python3`.
5. The report records the Bubblewrap version, the Landlock ABI, and the libseccomp version of each run.
6. Issue #1464 qualifies the installed artifact on the supported host profile.

### Mining RAPTOR

1. Review RAPTOR's sandbox changes for advances that apply to this engine.
2. An idea or a pattern needs no notice.
3. Copied code and tests keep RAPTOR's MIT copyright and permission notice.
4. The [case ledger](../security/containment-case-ledger.md) records the RAPTOR source commit of each mined case.

## Consequences

### Positive

LilRAE owns a small engine that it can review in full.
Bubblewrap is a maintained and widely used launcher, so LilRAE writes less namespace and mount code.

### Costs and risks

LilRAE owns the correctness of the launcher's Landlock, seccomp, and descriptor layers.
The escape probes and the case ledger are the main protection against regressions.
A host without Bubblewrap, user namespaces, Landlock, or libseccomp refuses every run.

### Non-goals

Issue #1454 owns production wiring of provider and MCP launches.
Issue #1464 owns installed-artifact qualification.
This record adds no participant-control semantics and does not bypass the #1216 and #1224 gates.
