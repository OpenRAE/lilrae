# ADR-065: Executable participant action boundaries

## Status

Proposed for the #1418 delivery PR.

## Context

Participant tool calls cross authoring, controller, runtime, native execution, and evidence boundaries.
Local integration can lose authored meaning or claim support for incompatible feature combinations.
Architecture prose alone cannot prevent that drift.
The [assessment](../architecture/participant-tool-admission.md) records existing research and reference patterns.

## Decision

Use an executable component model and finite action model to check LilRAE's integration with existing RAES semantic owners.
Map observed adapter traces to the action model.
Check implementation behavior independently with native-effect counts and accepted runtime histories.
Include negative mutations so missing enforcement is observable.

RAES remains the action-admission and history authority.
LilRAE adds exact installed tool mappings and transport enforcement at common MCP dispatch.
Neither role names nor tool names supply semantic identity.
A human-directed controller and an automated controller use the same admitted session interface.
Unbound operator access retains its distinct authority.

Use local IPC only as the carrier between the current Python runtime and Node MCP handlers.
Keep the in-process session interface independent of that carrier.
Add no universal gateway, scheduler, policy service, or second scenario language.
Keep capture selection independent from operational history.

Refuse unsupported compositions explicitly before effects.
Do not weaken upstream admission or claim a refusal test proves joint feature support.
Do not repeat native effects to recover missing outcomes or history.

## Consequences

Changes to participant action integration must satisfy executable architectural checks.
The checks become part of normal targeted tests and CI.
Model evidence remains bounded by the declared state space and tested implementation paths.
The management process and installed adapters remain trusted; local IPC supplies no host sandbox.

ADR-003 retains common MCP dispatch ownership.
ADR-029 retains secret-handling rules.
ADR-035 retains RAES as the semantic authority.
ADR-050 retains terminal archival ownership.
ADR-064 supplies the transitive layer and convention checks.
Shared tool contracts, action state, errors, and result redaction belong to Core.
The session and carrier belong to the RAES adapter.
The completed modules are enrolled in the repository layer check.
This decision changes none of those owners.

The [enforcement design](../architecture/participant-action-enforcement.md) defines the interfaces, data flows, controls, and verification limits.
