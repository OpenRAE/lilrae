# ADR-014: Scenario Description Language (SDL)

**Status:** Accepted
**Date:** 2026-03-29
**Deciders:** Brad Edwards

> Historical note: ADR-035 supersedes this ADR as current scenario-authoring
> authority. The APTL-local SDL parser and models described here were removed
> after the RAES SDL cutover; this record remains historical context.

## Applicability

The local parser and models in this decision are historical.
[ADR-035](adr-035-raes-sdl-adoption.md) assigns their portable contracts to RAES.
The [SDL guide](../sdl/index.md) links current authoring and runtime owners.

## Context

APTL's scenario format was an ad-hoc YAML schema validated only by Pydantic structural checks. The DSL-001 requirement called for a formal specification language with a documented grammar, parser, and semantic validation. The recorded research covered 12 cybersecurity SDLs, 10 adjacent DSLs, six security standards, and six agent-evaluation frameworks. It selected Open Cyber Range as the closest precedent.

The OCR SDL is a YAML-based language with 14 sections (nodes, infrastructure, features, conditions, vulnerabilities, metrics/evaluations/TLOs/goals, entities, injects/events/scripts/stories) parsed by a Rust library. It separates logical topology from physical deployment and includes a full scoring pipeline and exercise orchestration model.

The comparison identified missing content, accounts, ACLs, OS classes, asset values, service exposure, platform commands, service relationships, agents, and parameters. These were the proposed extensions.

## Decision

Use OCR as the starting surface for `aptl.core.sdl`. Preserve the OCR-derived sections and add seven sections from existing precedents. Keep deployment outside the language.

### Architecture

The SDL is a **specification language**, not a deployment tool. It describes *what a scenario is*. A separate provider binding layer (future work) translates SDL specifications into concrete infrastructure.

### Sections (21 total)

14 OCR-derived base sections + 7 new:
- `content` (from CyRIS)—data placed into systems
- `accounts` (from CyRIS)—user accounts within nodes
- `relationships` (from STIX SRO)—typed edges between elements
- `agents` (from CybORG)—autonomous participants
- `objectives` (from OCR scoring + CACAO workflow context)—declarative experiment semantics
- `workflows` (from CACAO workflow patterns)—branching and parallel objective composition
- `variables` (from CACAO)—parameterization

### Identity Model

Identity is not a separate section. It emerges from the combination of:
- **Accounts**: who exists where (username, groups, SPN, password strength)
- **Features**: what provides authentication (AD, LDAP, RADIUS services)
- **Relationships**: how services connect (`authenticates_with`, `trusts`, `federates_with`)

This is simpler and more composable than a dedicated identity layer.

### Validation

Two-phase validation:
1. **Structural** (Pydantic)—types, ranges, required fields, intra-model constraints
2. **Semantic** (SemanticValidator): 22 passes for references, cycles, IP/CIDR, VM/network types, counts, workflow graphs, and SDL rules

The validator collects all errors rather than failing on the first.

### Contract Guards

`icontract` may be used as a fail-fast guard over already-defined SDL state,
but it is not a third schema layer. Scenario contracts must protect stable
model/query boundaries such as "this returned objective/step belongs to this
scenario" or "a caller requesting a concrete workflow step supplied a declared
workflow and step name." They must not duplicate Pydantic field constraints,
semantic cross-reference passes, YAML normalization, shorthand expansion, or
runtime/deployment readiness checks.

Contract predicates must be pure, inexpensive, and safe to expose. They must not access files, Docker, networks, environments, secrets, or backends. They must not interpolate scenarios or raw YAML. Raw `icontract` violations must not cross CLI, API, logging, or persistence boundaries. Public
scenario loading still reports failures as `ScenarioValidationError`, wrapping
`SDLParseError` or `SDLValidationError` as appropriate.

Use contracts only where they add boundary clarity that the SDL validation
pipeline does not already provide. Keep an invariant in its existing Pydantic validator or collecting `SemanticValidator` pass when possible. This preserves field paths and aggregated errors.

### Parser

The parser handles:
- Case-insensitive field keys (preserving user-defined names)
- Shorthand expansion (source strings, infrastructure counts, role strings, min-score integers, feature lists)
- SDL-only parsing with clean rejection of removed legacy `metadata` scenarios
- Clean error messages for all failure modes

### SCN-001 Reconciliation Guardrail

SCN-001's original vocabulary (`metadata`, `mode`, container requirements,
attack steps, hints, and expected detections) predates the SDL-only boundary.
Any future work that reopens those concepts must reconcile them through the
current SDL surface rather than restoring a second scenario schema.

The historical authoring schema for this ADR was the local SDL model and parser.
After ADR-035, those local parser/model APIs are no longer authoritative. Future scenario fields must use RAES SDL and the catalog/runtime handoff. This includes mode, IDs, versions, difficulty, and estimates. Raw YAML side channels, filenames, and legacy schemas must not supply them.

Backend/runtime concerns stay out of the specification layer. Container
requirements should flow through `nodes`, `infrastructure`, backend capability
validation, and runtime planning. Objective probes belong in conditions, metrics, evaluations, evaluator adapters, or orchestration bindings. Wazuh queries, commands, file observations, and detection probes must not form another SDL validation schema.

### Backward Compatibility

None by design. This branch establishes an SDL-only boundary:
- Legacy APTL scenario YAMLs are archived as reference-only fixtures
- `aptl.core.scenarios` remains only as shared scenario/session exceptions
- The old scenario CLI/API/runtime entrypoints were removed rather than left as partial shims

## Consequences

### Positive

- **19 real-world scenarios validated** from 8 platforms (OCR, CybORG, CALDERA, Atomic Red Team, CyRIS, KYPO, HTB, Locked Shields)
- **1,050+ fuzz test inputs** with zero unhandled crashes
- Every SDL element traces to a published precedent
- Backend-agnostic: no Docker, OpenStack, or cloud provider coupling
- The OCR-derived coverage gaps identified in branch review were closed: entity facts and orchestration time grammar now align with the verified OCR surface
- One clear specification surface for follow-on provisioner/runtime work

### Negative

- 21 source files in `aptl.core.sdl/`—significant surface area
- Variables (`${var}`) are still unresolved at parse time; existence is checked, but backend substitution semantics remain future work
- Existing APTL scenario YAMLs require migration to SDL format
- No module composition system yet (Terraform-style imports)
- No formal verification (VSDL's SMT / CRACK's Datalog)
- Agent action semantics are strings, not typed operations

### Risks

- The SDL was designed and tested by one system (this project). Practitioner feedback may reveal ergonomic issues or missing concepts
- The relationship model uses a flat `properties` dict which could become a maintenance burden as relationship types proliferate
- Variable resolution semantics are undefined—instantiation backends will need to agree on substitution rules
