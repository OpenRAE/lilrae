# RPT capture boundary assessment

This historical Reference preserves the original source record.
The record below describes its own evidence date and revision, where stated.
It does not establish current behavior, implementation completion, or installed qualification.
The preserved file is available at [source revision `6d35d245f11a`](https://github.com/OpenRAE/lilrae/blob/6d35d245f11a7fffcaac1645cd25ccfafbad4599/docs/architecture/issue-1421-rpt-capture-preflight.md).
Its last recorded file change before this rewrite was `12ddaaf33db1`.
Current interfaces and successor decisions take precedence for present use.


[Issue #1421](https://github.com/OpenRAE/lilrae/issues/1421) defines the backend delivery.
This assessment follows the user's clarified collection scope.
The [capture design](issue-1421-capture-design.md) describes the implementation.

## Repository assessment

The repository already provides the needed capture boundaries:

- `scenario_capture` selects an installed adapter and its source registrations.
- `CollectorRegistry` supplies the manifest projection and admitted bindings.
- `WindowedSource` and `WindowedQueryCollector` adapt native data reads.
- `acquire_evidence` runs collectors, retains artifacts, and returns per-source results.
- `LocalRunStore` and the existing persistence code own storage and redaction.
- The participant runtime owns tool action identities and outcomes.
- The OpenCode launcher owns the private provider context and its cleanup.
- Native backend provenance remains with its existing producers and archives.

Keep these owners. Extend their current interfaces only where collection needs it.
The family adapter selects RPT's native file, API and log sources.
The trial caller supplies participant sources and starts cleanup after collection.
No new experiment engine, export framework or cleanup-hook system is needed.
The backend collection entry point verifies its runtime owner and admitted plan.
RPT adapter release and worker command delivery remain with their existing owners.

## Security and failure behavior

Participant data remains evaluator-only and redacted before durable storage.
Provider capture uses the approved local observer and the existing provider route.
Only the host-owned observer may load; ambient configuration stays disabled.
Never retain granted credential values or raw provider error diagnostics.
Scope native reads to admitted scenario containers.
The coordinator still applies its current byte, time, media and storage checks.
Preserve accepted records when another source fails and report incomplete collection.
A capture result establishes what the collector retained; it does not certify a study.

## Responsibility correction

RAE preserves SDL semantics and refuses unsupported interface requests.
LilRAE collects data and reports its actual collection outcome.
The RPT adapter selects and interprets observations.
The experimentalist governs evidence after handoff.

The earlier wait for RAE #273 to supply a custody verifier was incorrect.
That dependency and escalation have been removed.
Unsupported consumer assurance terms must be reported, not implemented as new trust infrastructure.
No custody service, signing-key system, post-handoff archive guarantee or scientific qualification belongs here.

## Verification scope

Exercise the manifest-to-request-to-artifact path with both participant sources and native logs.
Verify refusal before effects for undeclared sources and changed admitted registrations.
Verify partial records, source errors, limits and credential redaction.
Use the pinned OpenCode executable with the existing local provider fixture to check the shipped observer.
Full suites remain in CI.
