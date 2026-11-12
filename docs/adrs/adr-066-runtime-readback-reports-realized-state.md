# ADR-066: Runtime Readback Reports Realized State

## Status

accepted

## Date

2026-10-31

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [realization Reference](../components/node-realization.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

LilRAE realizes RAES scenarios and reports each realized runtime concern to the RAES runtime gate.
The gate compares each report with the plan-owned authority and records provenance.
The [materialization attestation](https://github.com/OpenRAE/rae/blob/main/specs/sdl/materialization-attestation.md) describes the realized world in SDL.
Research results and failover tests depend on the truth of these records.

[Issue #1017](https://github.com/OpenRAE/lilrae/issues/1017) found these faults:

- A temporary bridge changed compiled requirements and authority for one TechVault release.
- The bridge disclosed 13 configuration families from release digest tables, labelled `daemon-observed`.
- The bridge replaced process-global RAES value limits during apply.
- Core readers compared a declared value with Docker state and then disclosed the declared value.
  They disclosed nothing for an unauthored concern, so LilRAE could not report its own open choices.
- Two disclosure builders mapped each concern kind to a source through static tables.
- The manifest declared readback capability from a static list, also for kinds with no reader.

The [design](../architecture/issue-1017-native-runtime-attestation-design.md) gives the components, data flows, and threats.

## Decision

1. LilRAE plans the compiled scenario without change.
   No LilRAE code changes compiled requirements, authority, or RAES limits.
2. A disclosed runtime concern value comes from native state that LilRAE reads after realization.
   A reader can use authored identities to select members.
   Each reported world fact must have native corroboration.
   Logical identifiers and labels remain author-owned metadata.
3. Each reading carries the source that its reader used.
   The disclosure binder uses that source.
4. A reader reports the scenario-significant managed subset of its concern.
   Authored identities select the managed subset.
   When the subset is empty, the reader discloses nothing.
5. The manifest declares readback capability only for a kind that a registered reader reads.
   Capability is a projection of the core reader registry and the admitted adapter declaration.
6. The component that realizes a member reads it.
   Core reads container settings, host kernel state, generic guest inventories, and what core installs.
   The scenario adapter reads the product state that its pack realizes.
   Readings of one concern merge by member identity, with one source for each kind.
7. Core contains no pack, release, or digest branch.
8. Readback does not refuse a member that the authority permits.
   RAES applies exact, closed, and open semantics to the disclosed value.
9. The family capability set drops planning compatibility.
   The family API keeps its version, because adapters now provide a superset of the requirement.

## Alternatives considered

### Fixed image declarations (2026-11-12 amendment)

An installed adapter may report a fixed image preset with the RAE `driver-reported` source.
It must bind that preset to the observed immutable container image identity and the admitted source family.
The report describes the known preset; it does not claim native configuration readback.
Core readers retain their declared sources and cannot be overridden by a weaker adapter report.
Live readiness, experimental measurements, and objective verdicts require their own native observations.
This is distinct from the rejected bridge, which labelled release-table values as daemon observations.

| Alternative | Reason for rejection |
| --- | --- |
| Keep the bridge until RAES has a portable selector | The bridge changes author intent and labels planned values as observations. |
| Key the digest tables by node instead of release | A table still discloses planned values. It also needs a new table for each trial variation. |
| Declare capability for every registered kind | The manifest would claim readback with no reader. |
| Read every native entry, for example every process and package | RAES issue 1078 excludes base-image and incidental native inventory from the closure universe. |
| Keep the planning compatibility seam with empty decisions | An extension point with no permitted effect is dead code and invites a future rewrite. |
| Build readers for concerns that no one realizes | A reader that reads nothing proves nothing. RAES needs a checked no-addition commitment. |

## Consequences

### Positive

- Each disclosed value is evidence of realized state, with an accurate source.
- The attested SDL describes LilRAE's open choices, for example published ports and limits.
- A third-party adapter adds product readers without core changes or release tables.
- Capability claims are true for each admitted target, including the `ssh-compose` transport.

### Negative

- Native observation exposes pack declarations that disagree with their exact implementation.
  Required mismatches reject realization until the owner corrects them.
- The adapter maintains readers for the product families that it supports.
- Snapshots grow because they carry each realized concern.

## Relation to other decisions

- ADR-046 and ADR-051: Dynamic and component-level realization keep their owners.
  This record changes how LilRAE reports the result.
- ADR-053: The pack and backend interaction seam keeps its scope.
  The startup provider gains the readback declaration.
- [ADR-064](adr-064-layered-architecture-and-code-conventions.md): New modules follow its layers, module rules, and typing rules.
  The readback values and the adapter Protocol are core code.
