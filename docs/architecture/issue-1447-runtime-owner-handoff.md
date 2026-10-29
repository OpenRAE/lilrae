# Issue #1447: Runtime Ownership During Evidence Refresh

> **Superseded (issue #1407).** RAES 9.0.0 uses one runtime for the whole run (OpenRAE/rae#1660). The run's runtime delivers participant turns and evaluates later evidence with `evaluate()`, so this handoff and its module are removed.

The Cortex seed fix exposes a second startup failure. Native evidence refresh
constructs a control plane while the apply outcome retains its runtime manager.
RAES 7 permits only one owner of the target's components. Participant delivery
has the same conflict after each clock advance.

## Ownership Decision

Keep the initialized manager for clock and scheduler state. Give each temporary
control plane exclusive ownership through a scoped handoff:

1. Serialize handoffs and refuse a closed manager.
2. Call the manager's `close()` method. It drains callbacks and stops the
   participant clock driver before releasing the component claim.
3. Read the drained manager's latest snapshot. Evidence refresh clears only
   evaluation state before replaying the admitted evaluation plan.
4. Construct the control plane with that snapshot and the existing information
   state resolver. Its normal constructor acquires the component claim.
5. Run the phase and retain its authoritative snapshot. Close the control plane.
6. Adopt the closed phase's snapshot before acquiring a new manager claim
   through RAES's `RuntimeResourceClaim` constructor. Restart the existing clock
   driver only after reacquisition succeeds.

No two owners act at once. The new claim constructor still refuses an active or
unresolved owner. A failed drain never starts another owner. A construction,
execution, or close exception leaves the manager closed and fails startup.

## Pinned Extension Boundary

The checkout pins `raes==7.0.0`. Its manager has no public handoff method.
`_lilrae_runtime_handoff.py` extends that manager using the existing
`RuntimeResourceClaim` in `raes_runtime.runtime_resource_ownership` and the clock
driver lifecycle in `raes_runtime.participant_execution_control`. These are
version-specific integration points, covered by tests against the pinned release.
An upstream API can replace this extension when available.

The extension never clears the claim registry or changes another owner's claim.
It creates no replacement backend, manager, evaluator, or clock. Retaining the
manager preserves its time declaration, scheduler, activity controls, and clock
progress. Evidence refresh binds records only after the handoff has drained the
old owner.

## Authority And Failure Handling

The existing RAES control plane remains the only writer during each phase.
Native evidence refresh still registers the planner-produced plan, checks its
terminal result, and verifies exact evidence bindings. Its participant crossing
policy remains closed. Participant delivery retains its existing behavior
specifications, crossing policy, and evidence acquisition boundary.

The handoff adds no credential, network listener, external service, or persisted
state format. Exceptions retain the existing bounded lab-start failure behavior.
[ADR-046](../adrs/adr-046-dynamic-raes-scenario-realization.md) remains the
governing decision. This extends the explicit ownership lifecycle used by
[issue #1424](issue-1424-runtime-retry-ownership-design.md) to temporary phases.

## Verification

- `tests/test_raes_native_evidence_truth.py` drives the real apply manager through
  lab-start evidence refresh, including a target with participant capabilities.
  It checks committed truth, retained metadata, snapshot agreement, and exclusive
  ownership after refresh.
- `tests/test_lilrae_runtime_handoff.py` checks repeated handoffs with initialized
  time, ownership exclusion, failed drain, failed execution, failed close, and
  unresolved claims.
- `tests/test_raes_participant_delivery.py` uses real component claims for its
  four-turn delivery sequence. Only clock advancement and the provider transport
  remain simulated.

CI verifies the changed branch. The original Cortex live result used a custom
RAES build and does not prove this ownership repair against a live lab.

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
