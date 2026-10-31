# Runtime Ownership During Evidence Refresh

RAES 9.2.0 provides one runtime owner for each run.
`RuntimeManager` and `RuntimeControlPlane` name the same class.
LilRAE keeps that owner for apply, time, native evidence, participant delivery, and teardown.
The former private claim handoff is removed.

## Ownership Decision

The constructor binds the target, admitted run scope, protected archive, and participant policy.
The owner retains the initialized clock, scheduler, operation ledger, and authoritative snapshot.
Later native evidence enters the evaluator before the public `evaluate()` call.
Each distinct evidence cut uses a distinct idempotency key.
Replaying the same cut retains that key.
RAES replans evaluation from the original compiled context against current committed state.
It does not provision again or restart workflows.
LilRAE reads the terminal operation before accepting refreshed truth.

Participant delivery uses the same owner and its admitted behavior specifications.
The constructor installs the delivery plan's existing crossing policy.
Execution cannot replace that policy, the run scope, or the materialization archive.
No private snapshot adoption or component claim mutation is required.
A second owner remains excluded while the run is open.
The existing RAES drain and uncertain-effect rules govern closure and reuse.

## Authority And Failure Handling

The RAES runtime remains the only writer during each phase.
It validates backend results and publishes materialization references before accepting them.
The configured target manifest remains the producer identity for every phase.
Participant delivery retains its existing behavior, crossing, and evidence boundaries.
A failed or pending operation never becomes successful merely because a receipt was accepted.
A failed apply ends the start without an automatic backend retry.
Closing that owner does not prove cleanup or permit a new target owner.
The retained operation requires the existing explicit recovery and resolution path.

This migration adds no network listener, credential source, service, or persisted state format.
[ADR-046](../adrs/adr-046-dynamic-raes-scenario-realization.md) remains the governing decision.
The [upstream migration guide](https://github.com/OpenRAE/rae/blob/v9.1.0/docs/migration/runtime-lifetime.md)
defines the supported public lifetime API.

## Verification

Targeted native evidence, participant delivery, runtime ownership, and descendant reporting tests
check state continuity, run identity, protected archives, failed operations, and ownership exclusion.
CI owns full-suite and clean lab qualification.

## Security Gate Repairs

CI also reported CVE-2026-116587 in Caddy's Go JOSE v4 dependency. The build now
uses the upstream fixed release, v4.1.6, with regenerated Go module checksums.
The upstream advisory is
[GHSA-mgcc-cww5-fp2q](https://github.com/go-jose/go-jose/security/advisories/GHSA-mgcc-cww5-fp2q).

The Debian image scans reported CVE-2026-114613 in pip's bundled msgpack 1.1.2.
The hash-verified pip 26.2.2 wheel contains only the Python fallback. The affected
C extension is absent. The
[upstream advisory](https://github.com/msgpack/msgpack-python/security/advisories/GHSA-j586-36cw-2gc2)
states that this fallback does not exhibit the flaw.

The existing Trivy exception mechanism records this false positive for that
exact package version. The Debian substrate build checks the fallback inside
the built image. The regression test checks the locked copy's version, the
absence of the C extension, and the fallback implementation. The normal scan
still records the finding in SARIF; the exception applies only to the gate.
