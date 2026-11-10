# ADR-068: Shared Containment Wrapper

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
Each backend must not rediscover the same namespace, filesystem, syscall, descriptor, socket, and lifetime bypasses.
A namespace launcher alone does not give a composed boundary.
[Issue #1467](https://github.com/OpenRAE/lilrae/issues/1467) selects a maintained fork of the reviewed engine behind one shared wrapper.

The reviewed engine is RAPTOR `core/sandbox` at commit `28c996ca997c0aeaf94080c88733788a3b26c9e5`.
That commit is the `main` branch of the fork [OpenRAE/raptor](https://github.com/OpenRAE/raptor).
The upstream is [gadievron/raptor](https://github.com/gadievron/raptor).
The engine composes namespaces, Landlock, seccomp-bpf, resource limits, and a trusted setup-status channel.
It imports only the Python standard library.
It keeps some state in process-wide singletons, for example its egress proxy allowlist.

The [architecture](../architecture/containment-wrapper.md) gives the components, data flows, threats, and controls.

## Decision

### Engine source and pin

1. LilRAE uses the fork through the git submodule `third_party/raptor`.
2. The submodule gitlink pins the exact fork commit. A branch name is not a release identity.
3. `src/aptl/containment/engine_pin.json` records the repository, upstream, commit, and source digest.
4. The source digest covers every regular file under the engine's `core/` tree, except bytecode caches.
5. The wrapper copies the engine source into a snapshot under the state root and hashes the bytes that it wrote.
6. A digest mismatch refuses every run. A matched snapshot becomes read-only and owner-only.
7. Workers import only the snapshot, with bytecode reads and writes off. A later checkout change cannot reach a worker.
8. The wrapper verifies an existing snapshot in full. A bytecode file or an extra file in it refuses the engine.
9. This change does not edit the fork. The engine code and its regression tests stay intact.

### Wrapper and worker

1. The wrapper is the `aptl.containment` adapter. The versioned interface is the `aptl.core.containment` core package.
2. Python consumers use the adapter. Other languages use the `lilrae containment run` command over standard input and output.
3. Both routes use the same request model, validation, worker, and report model.
4. Each run uses a new worker process. The worker imports the engine from the pinned root.
5. The consumer process never imports the engine. Engine singletons, logging, and configuration stay inside one worker.
6. The existing `BoundedProcessRunner` starts the worker. Entry code injects it through a core Protocol.
7. The wrapper adds no network service and no second scenario runtime.

### Interface

1. The request and report schemas carry the version names `lilrae.containment.request/v1` and `lilrae.containment.report/v1`.
2. Version 1 has one profile, `linux-full`. It requires five properties.
3. The properties are namespaces with a fresh procfs, filesystem policy, syscall and socket filter, descriptor and environment hygiene, and supervision.
4. The worker checks each property separately before it starts the target. One check never replaces another.
5. An unknown or failed property refuses the run before the target starts. The worker then delivers no payload.
6. The worker runs the target through the engine's `run_untrusted` entry point with the `strict` profile.
7. Version 1 has no network access and no credential channel. Issues #1455 and #1458 own those seams.

### Failure reporting and bounds

1. The worker sends its report on its own standard output. The target cannot write to that channel.
2. The report separates setup refusal, target failure, and supervisor failure.
3. The engine's setup-status channel attributes setup failure. A target exit status cannot imitate it.
4. A run without an engine posture record, for example after a timeout, does not claim containment.
5. The engine enforces the target deadline. The runner enforces an outer worker deadline and cancellation.
6. The worker applies the aggregate output bound. The report also states the engine's transient per-stream capture bound.
7. The report states that version 1 does not enforce a peak-memory bound. Issue #1457 owns aggregate resource budgets.
8. An address-space limit is reported as an address-space limit, never as a memory bound.

### Concurrent runs

1. Each run gets a new private directory under a backend-owned state root.
2. The target's only writable grant is the output directory of its own run.
3. Each run has its own worker, process group, cancellation event, and report channel.
4. One run cannot widen the grants, proxy allowlist, evidence channel, or lifecycle of another run.

### Ownership and distribution

1. The fork maintainer owns the enforcement code, upstream review, and retained regressions.
2. The wrapper owner owns the interface, the worker, and the conformance proof.
3. Consumers own their admitted authority and their exact pins.
4. Another worker adapter must supply the obligations in the [interface Reference](../reference/containment-interface.md#adapter-obligations).
5. A source checkout gets the engine through the submodule. No run downloads or updates the engine.
6. Issue #1464 decides how an installed artifact carries the engine and its license notice.

### Updates and extraction

1. Upstream changes enter the fork through ordinary reviewed branches and pull requests.
2. History keeps fixes and conflict resolutions. Do not rewrite them.
3. A pin update changes the gitlink and the pin file in one pull request.
4. CI runs the retained engine regressions and the wrapper proof before a pin update merges.
5. Extract engine components only for a demonstrated required change or a repeated wrapper limitation.
6. An extraction proposal compares maintenance cost with upstream-update cost.

### Adaptations

The wrapper adapts engine input and output in three places:

| Adaptation | Reason |
| --- | --- |
| The worker applies the aggregate output bound after capture. | `run_untrusted` does not accept the engine's per-call capture limit. |
| The worker builds the target environment explicitly and refuses names that the engine classifies as dangerous. | `run_untrusted` passes a caller environment through without its strict filter. |
| The adapter gives the worker a private home and temporary directory. | The engine reads its limit configuration from the home directory. |

## Consequences

### Positive

All backends can use one reviewed enforcement implementation and its regression corpus.
The per-run worker keeps engine singletons away from concurrent runs.

### Costs and risks

The fork needs upstream review and pin updates.
Hosts that restrict unprivileged user namespaces refuse every run.
Ubuntu 24.04 does this by default through AppArmor.

The snapshot copy and its digest add start-up cost once for each adapter.
Snapshot integrity depends on a state root that only the owner can write.
Engine evidence files in the output directory are target-writable. Issue #1460 owns trusted evidence storage.

### Non-goals

Issue #1454 owns production wiring of provider and MCP launches.
Issue #1464 owns installed-artifact qualification.
This record adds no participant-control semantics and does not bypass the #1216 and #1224 gates.
